#!/usr/bin/env python3
"""Run the fixed comprehensive corpus through the oracle and token protocol."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import selectors
import subprocess
import sys
import time
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "test_cases" / "comprehensive" / "manifest.json"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class LoadedCase:
    name: str
    family: str
    expected: str
    complete: bool
    source: str
    safe_prefix_bytes: int | None
    oracle: bool
    stage: str
    expectation_tier: str
    covers: tuple[str, ...]
    path: Path
    source_sha256: str


@dataclass(frozen=True)
class ProtocolResult:
    answers: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    reject_token: int | None
    reject_byte_end: int | None
    exception_kind: str | None = None
    exception_message: str | None = None


SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
CORPUS_DIGEST_FORMAT = "sorted-path-nul-source-bytes-nul-v1"


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _require_mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be an object")
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{label} must be a non-empty string")
    return value


def _resolve_beneath(root: Path, relative: str, label: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise RuntimeError(f"{label} must be relative: {relative!r}")
    resolved_root = root.resolve()
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise RuntimeError(f"{label} escapes its root: {relative!r}") from error
    return resolved


def _corpus_sha256(entries: Sequence[tuple[str, bytes]]) -> str:
    digest = hashlib.sha256()
    for relative, payload in sorted(entries):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def load_cases(manifest_path: Path) -> tuple[dict[str, object], list[LoadedCase]]:
    try:
        manifest = _require_mapping(
            json.loads(manifest_path.read_text(encoding="utf-8")), "manifest"
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(f"cannot read manifest {manifest_path}: {error}") from error
    schema_version = manifest.get("schema_version")
    if schema_version not in {1, 2, 3}:
        raise RuntimeError(f"unsupported manifest schema: {manifest.get('schema_version')}")
    if schema_version == 3:
        if manifest.get("generator") != "tools/generate_comprehensive_cases.py":
            raise RuntimeError("schema 3 manifest has an invalid generator")
        generation = _require_mapping(manifest.get("generation"), "manifest generation")
        for key in ("seed", "generated_cases_per_family"):
            value = generation.get(key)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise RuntimeError(f"manifest generation.{key} must be non-negative integer")
    raw_cases = manifest.get("cases")
    if not isinstance(raw_cases, list):
        raise RuntimeError("manifest cases must be an array")
    case_count = manifest.get("case_count")
    if not isinstance(case_count, int) or isinstance(case_count, bool) or case_count < 0:
        raise RuntimeError("manifest case_count must be a non-negative integer")
    root = manifest_path.parent
    cases: list[LoadedCase] = []
    seen_names: set[str] = set()
    seen_files: set[str] = set()
    corpus_entries: list[tuple[str, bytes]] = []
    for index, raw_item in enumerate(raw_cases):
        item = _require_mapping(raw_item, f"cases[{index}]")
        name = _require_string(item.get("name"), f"cases[{index}].name")
        family = _require_string(item.get("family"), f"cases[{index}].family")
        relative = _require_string(item.get("file"), f"cases[{index}].file")
        if name in seen_names:
            raise RuntimeError(f"duplicate case name: {name!r}")
        if relative in seen_files:
            raise RuntimeError(f"duplicate case file: {relative!r}")
        seen_names.add(name)
        seen_files.add(relative)
        if Path(relative).suffix != ".cj":
            raise RuntimeError(f"case {name}: source file must end in .cj")
        path = _resolve_beneath(root, relative, f"case {name} file")
        try:
            source_bytes = path.read_bytes()
            source = source_bytes.decode("utf-8")
        except (OSError, UnicodeError) as error:
            raise RuntimeError(f"case {name}: cannot read UTF-8 source {path}: {error}") from error
        expected = item.get("expected")
        if expected not in {"accept", "reject"}:
            raise RuntimeError(f"case {name}: expected must be 'accept' or 'reject'")
        complete = item.get("complete")
        oracle = item.get("oracle", True)
        if not isinstance(complete, bool) or not isinstance(oracle, bool):
            raise RuntimeError(f"case {name}: complete and oracle must be booleans")
        stage = item.get(
            "stage",
            "prefix" if not complete else ("accept" if expected == "accept" else "semantic"),
        )
        if stage not in {"accept", "prefix", "semantic", "syntax"}:
            raise RuntimeError(f"case {name}: unsupported stage {stage!r}")
        if not complete and (expected != "accept" or oracle or stage != "prefix"):
            raise RuntimeError(
                f"case {name}: incomplete cases must be prefix accepts with oracle disabled"
            )
        if complete and expected == "accept" and stage != "accept":
            raise RuntimeError(f"case {name}: complete accept case must use stage='accept'")
        if complete and expected == "reject" and stage not in {"semantic", "syntax"}:
            raise RuntimeError(f"case {name}: complete reject case has invalid stage")
        safe_prefix_bytes = item.get("safe_prefix_bytes")
        if expected == "reject":
            if (
                not isinstance(safe_prefix_bytes, int)
                or isinstance(safe_prefix_bytes, bool)
                or safe_prefix_bytes < 0
                or safe_prefix_bytes >= len(source_bytes)
            ):
                raise RuntimeError(
                    f"case {name}: reject case needs safe_prefix_bytes within source"
                )
            try:
                source_bytes[:safe_prefix_bytes].decode("utf-8")
            except UnicodeDecodeError as error:
                raise RuntimeError(
                    f"case {name}: safe_prefix_bytes splits a UTF-8 code point"
                ) from error
        elif safe_prefix_bytes is not None:
            raise RuntimeError(f"case {name}: accept case must not set safe_prefix_bytes")

        actual_source_sha256 = _sha256_bytes(source_bytes)
        declared_source_sha256 = item.get("source_sha256")
        if declared_source_sha256 is not None:
            if not isinstance(declared_source_sha256, str) or not SHA256_RE.fullmatch(
                declared_source_sha256
            ):
                raise RuntimeError(f"case {name}: invalid source_sha256")
            if declared_source_sha256 != actual_source_sha256:
                raise RuntimeError(f"case {name}: source_sha256 mismatch")
        elif schema_version == 3:
            raise RuntimeError(f"case {name}: schema 3 requires source_sha256")
        if schema_version == 3:
            raw_covers = item.get("covers")
            if (
                not isinstance(raw_covers, list)
                or any(not isinstance(target, str) or not target for target in raw_covers)
                or raw_covers != sorted(set(raw_covers))
            ):
                raise RuntimeError(f"case {name}: covers must be sorted unique strings")
            covers = tuple(raw_covers)
            source_bytes_count = item.get("source_bytes")
            if (
                not isinstance(source_bytes_count, int)
                or isinstance(source_bytes_count, bool)
                or source_bytes_count != len(source_bytes)
            ):
                raise RuntimeError(f"case {name}: source_bytes mismatch")
            declared_safe_prefix_sha256 = item.get("safe_prefix_sha256")
            if safe_prefix_bytes is None:
                if declared_safe_prefix_sha256 is not None:
                    raise RuntimeError(
                        f"case {name}: safe_prefix_sha256 must be null without a safe prefix"
                    )
            else:
                if (
                    not isinstance(declared_safe_prefix_sha256, str)
                    or not SHA256_RE.fullmatch(declared_safe_prefix_sha256)
                ):
                    raise RuntimeError(f"case {name}: invalid safe_prefix_sha256")
                if declared_safe_prefix_sha256 != _sha256_bytes(
                    source_bytes[:safe_prefix_bytes]
                ):
                    raise RuntimeError(f"case {name}: safe_prefix_sha256 mismatch")
            reason = item.get("oracle_skip_reason")
            if not oracle and (not isinstance(reason, str) or not reason.strip()):
                raise RuntimeError(
                    f"case {name}: oracle-disabled case needs oracle_skip_reason"
                )
            if oracle and reason is not None:
                raise RuntimeError(
                    f"case {name}: oracle-enabled case must not set oracle_skip_reason"
                )
            expectation_tier = item.get("expectation_tier")
            expected_tier = (
                "diagnostic_scale"
                if family == "scale_stress"
                else "authoritative" if oracle else "diagnostic_spec_pending"
            )
            if expectation_tier != expected_tier:
                raise RuntimeError(
                    f"case {name}: expectation_tier must be {expected_tier!r}"
                )
        else:
            raw_covers = item.get("covers", [])
            covers = tuple(raw_covers) if isinstance(raw_covers, list) else ()
            expectation_tier = (
                "diagnostic_scale"
                if family == "scale_stress"
                else "authoritative" if oracle else "diagnostic_spec_pending"
            )
        corpus_entries.append((relative, source_bytes))
        cases.append(
            LoadedCase(
                name=name,
                family=family,
                expected=expected,
                complete=complete,
                source=source,
                safe_prefix_bytes=safe_prefix_bytes,
                oracle=oracle,
                stage=stage,
                expectation_tier=expectation_tier,
                covers=covers,
                path=path,
                source_sha256=actual_source_sha256,
            )
        )
    if len(cases) != case_count:
        raise RuntimeError(
            f"manifest case_count={manifest.get('case_count')} but loaded {len(cases)}"
        )
    family_counts: dict[str, int] = {}
    expectation_counts = {"accept": 0, "prefix_accept": 0, "reject": 0}
    for case in cases:
        family_counts[case.family] = family_counts.get(case.family, 0) + 1
        if not case.complete:
            expectation_counts["prefix_accept"] += 1
        else:
            expectation_counts[case.expected] += 1
    if "family_counts" in manifest and manifest["family_counts"] != dict(
        sorted(family_counts.items())
    ):
        raise RuntimeError("manifest family_counts does not match cases")
    if "expectation_counts" in manifest and manifest["expectation_counts"] != expectation_counts:
        raise RuntimeError("manifest expectation_counts does not match cases")

    tier_counts: dict[str, int] = {}
    for case in cases:
        tier_counts[case.expectation_tier] = tier_counts.get(case.expectation_tier, 0) + 1
    if schema_version == 3 and manifest.get("expectation_tier_counts") != dict(
        sorted(tier_counts.items())
    ):
        raise RuntimeError("manifest expectation_tier_counts does not match cases")

    if schema_version == 3:
        stage_counts: dict[str, int] = {}
        complete_counts = {"complete": 0, "incomplete": 0}
        oracle_counts = {"checked": 0, "skipped_complete": 0, "skipped_incomplete": 0}
        coverage_counts: dict[str, int] = {}
        for case in cases:
            stage_counts[case.stage] = stage_counts.get(case.stage, 0) + 1
            complete_counts["complete" if case.complete else "incomplete"] += 1
            oracle_key = (
                "checked"
                if case.oracle
                else "skipped_complete" if case.complete else "skipped_incomplete"
            )
            oracle_counts[oracle_key] += 1
            for target in case.covers:
                coverage_counts[target] = coverage_counts.get(target, 0) + 1
        for key, expected_value in (
            ("stage_counts", dict(sorted(stage_counts.items()))),
            ("complete_counts", complete_counts),
            ("oracle_counts", oracle_counts),
        ):
            if manifest.get(key) != expected_value:
                raise RuntimeError(f"manifest {key} does not match cases")
        coverage = _require_mapping(manifest.get("coverage"), "manifest coverage")
        sorted_coverage = dict(sorted(coverage_counts.items()))
        if coverage.get("counts") != sorted_coverage:
            raise RuntimeError("manifest coverage.counts does not match cases")
        required_count = coverage.get("required_target_count")
        if (
            not isinstance(required_count, int)
            or isinstance(required_count, bool)
            or required_count < 0
            or coverage.get("covered_target_count") != required_count
            or coverage.get("missing_targets") != []
            or required_count > len(sorted_coverage)
        ):
            raise RuntimeError("manifest coverage summary is inconsistent")

    if schema_version == 3:
        integrity = _require_mapping(manifest.get("integrity"), "manifest integrity")
        if integrity.get("algorithm") != "sha256":
            raise RuntimeError("manifest integrity.algorithm must be 'sha256'")
        if integrity.get("corpus_digest_format") != CORPUS_DIGEST_FORMAT:
            raise RuntimeError("unsupported corpus digest format")
        declared_corpus_sha256 = integrity.get("corpus_sha256")
        if not isinstance(declared_corpus_sha256, str) or not SHA256_RE.fullmatch(
            declared_corpus_sha256
        ):
            raise RuntimeError("manifest integrity.corpus_sha256 is invalid")
        if declared_corpus_sha256 != _corpus_sha256(corpus_entries):
            raise RuntimeError("manifest integrity.corpus_sha256 mismatch")
        dependencies = _require_mapping(
            integrity.get("dependencies"), "manifest integrity.dependencies"
        )
        for relative, declared_digest in dependencies.items():
            if not isinstance(relative, str) or not relative:
                raise RuntimeError("integrity dependency paths must be non-empty strings")
            if not isinstance(declared_digest, str) or not SHA256_RE.fullmatch(declared_digest):
                raise RuntimeError(f"invalid dependency sha256 for {relative!r}")
            dependency_path = _resolve_beneath(ROOT, relative, "integrity dependency")
            try:
                actual_digest = _sha256_file(dependency_path)
            except OSError as error:
                raise RuntimeError(
                    f"cannot read integrity dependency {relative!r}: {error}"
                ) from error
            if actual_digest != declared_digest:
                raise RuntimeError(f"integrity dependency sha256 mismatch: {relative}")
    return manifest, cases


def _run_protocol(
    solution: Path,
    token_ids: Sequence[int],
    token_chunks: Sequence[bytes],
    *,
    competition_output: bool,
    timeout: float,
) -> ProtocolResult:
    """Drive one checker interactively and require one flushed line per token."""
    command = [str(solution)]
    if competition_output:
        command.append("--competition-output")
    answers: list[str] = []
    stdout_parts: list[str] = []
    stderr = ""
    exception_kind: str | None = None
    exception_message: str | None = None
    returncode: int | None = None
    proc: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    pending_stdout = bytearray()
    deadline = time.monotonic() + timeout
    try:
        proc = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert proc.stdin is not None and proc.stdout is not None and proc.stderr is not None
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        for token_id in token_ids:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                proc.stdin.write(f"{token_id}\n".encode("ascii"))
                proc.stdin.flush()
            except BrokenPipeError:
                break
            while b"\n" not in pending_stdout:
                remaining = deadline - time.monotonic()
                if remaining <= 0 or not selector.select(remaining):
                    raise subprocess.TimeoutExpired(command, timeout)
                chunk = os.read(proc.stdout.fileno(), 4096)
                if not chunk:
                    break
                pending_stdout.extend(chunk)
            if b"\n" not in pending_stdout:
                break
            line_end = pending_stdout.index(b"\n") + 1
            raw_line = bytes(pending_stdout[:line_end])
            del pending_stdout[:line_end]
            line = raw_line.decode("utf-8", errors="replace")
            stdout_parts.append(line)
            answers.append(line[:-1] if line.endswith("\n") else line)
            if pending_stdout:
                exception_kind = "ProtocolViolation"
                exception_message = "checker emitted output before the next token"
                break
            if answers[-1] == ("0" if competition_output else "1"):
                break

        proc.stdin.close()
        proc.stdin = None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(command, timeout)
        trailing_stdout_bytes, stderr_bytes = proc.communicate(timeout=remaining)
        returncode = proc.returncode
        trailing_stdout = (bytes(pending_stdout) + trailing_stdout_bytes).decode(
            "utf-8", errors="replace"
        )
        pending_stdout.clear()
        if trailing_stdout:
            stdout_parts.append(trailing_stdout)
            # Preserve each extra/unterminated record so count/format checks fail.
            answers.extend(trailing_stdout.splitlines())
            if trailing_stdout.endswith("\n") and trailing_stdout == "\n":
                answers.append("")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        exception_kind = "TimeoutExpired"
        exception_message = f"timeout after {timeout:.3f}s"
    except OSError as error:
        exception_kind = type(error).__name__
        exception_message = str(error)
    finally:
        if selector is not None:
            selector.close()
        if proc is not None and proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
        if proc is not None:
            if pending_stdout:
                stdout_parts.append(bytes(pending_stdout).decode("utf-8", errors="replace"))
                pending_stdout.clear()
            if proc.stdout is not None and not proc.stdout.closed:
                rest = proc.stdout.read().decode("utf-8", errors="replace")
                if rest:
                    stdout_parts.append(rest)
            if proc.stderr is not None and not proc.stderr.closed:
                rest = proc.stderr.read().decode("utf-8", errors="replace")
                if rest:
                    stderr += rest
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                if stream is not None and not stream.closed:
                    stream.close()

    stdout = "".join(stdout_parts)
    answer_tuple = tuple(answers)
    reject_value = "0" if competition_output else "1"
    reject_token = None
    reject_byte_end = None
    consumed = 0
    for index, chunk in enumerate(token_chunks):
        consumed += len(chunk)
        if index < len(answer_tuple) and answer_tuple[index] == reject_value:
            reject_token = index
            reject_byte_end = consumed
            break
    return ProtocolResult(
        answers=answer_tuple,
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
        reject_token=reject_token,
        reject_byte_end=reject_byte_end,
        exception_kind=exception_kind,
        exception_message=exception_message,
    )


def _run_raw_protocol(
    solution: Path,
    stdin: str,
    *,
    competition_output: bool,
    timeout: float,
) -> ProtocolResult:
    command = [str(solution)]
    if competition_output:
        command.append("--competition-output")
    try:
        proc = subprocess.run(
            command,
            cwd=ROOT,
            input=stdin,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        return ProtocolResult(
            answers=tuple(proc.stdout.splitlines()),
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            reject_token=None,
            reject_byte_end=None,
        )
    except subprocess.TimeoutExpired as error:
        partial_stdout = error.stdout or ""
        partial_stderr = error.stderr or ""
        if isinstance(partial_stdout, bytes):
            partial_stdout = partial_stdout.decode("utf-8", errors="replace")
        if isinstance(partial_stderr, bytes):
            partial_stderr = partial_stderr.decode("utf-8", errors="replace")
        return ProtocolResult(
            answers=tuple(partial_stdout.splitlines()),
            returncode=None,
            stdout=partial_stdout,
            stderr=partial_stderr,
            reject_token=None,
            reject_byte_end=None,
            exception_kind="TimeoutExpired",
            exception_message=f"timeout after {timeout:.3f}s",
        )
    except OSError as error:
        return ProtocolResult(
            answers=(),
            returncode=None,
            stdout="",
            stderr="",
            reject_token=None,
            reject_byte_end=None,
            exception_kind=type(error).__name__,
            exception_message=str(error),
        )


def _answers_sha256(answers: Sequence[str]) -> str:
    # A length-prefixed encoding makes the digest unambiguous without retaining
    # large transcripts in the JSON report.
    digest = hashlib.sha256()
    for answer in answers:
        payload = answer.encode("utf-8")
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _result_observation(result: ProtocolResult) -> dict[str, object]:
    exception = None
    if result.exception_kind is not None:
        exception = {
            "kind": result.exception_kind,
            "message": result.exception_message,
        }
    return {
        "answer_count": len(result.answers),
        "answers_sha256": _answers_sha256(result.answers),
        "stdout_sha256": _sha256_bytes(result.stdout.encode("utf-8")),
        "stderr_sha256": _sha256_bytes(result.stderr.encode("utf-8")),
        "returncode": result.returncode,
        "exception": exception,
        "reject_token": result.reject_token,
        "reject_byte_end": result.reject_byte_end,
    }


def _strict_output_errors(result: ProtocolResult, label: str) -> list[str]:
    if not result.stdout:
        return []
    records = result.stdout.splitlines(keepends=True)
    invalid = [record for record in records if record not in {"0\n", "1\n"}]
    return (
        [f"{label}: stdout records must be exactly '0\\n' or '1\\n': {invalid[:3]!r}"]
        if invalid
        else []
    )


def _bounded(value: str, limit: int = 240) -> str:
    return value if len(value) <= limit else value[:limit] + "..."


def _differential_errors(
    candidate: ProtocolResult,
    reference: ProtocolResult,
    *,
    label: str,
) -> list[str]:
    errors: list[str] = []
    if candidate.answers != reference.answers:
        first_difference = next(
            (
                index
                for index, (left, right) in enumerate(
                    zip(candidate.answers, reference.answers)
                )
                if left != right
            ),
            min(len(candidate.answers), len(reference.answers)),
        )
        errors.append(
            f"{label}: answer transcript differs at index {first_difference}; "
            f"candidate count/sha={len(candidate.answers)}/{_answers_sha256(candidate.answers)}, "
            f"reference count/sha={len(reference.answers)}/{_answers_sha256(reference.answers)}"
        )
    if candidate.stdout != reference.stdout:
        errors.append(
            f"{label}: raw stdout differs; "
            f"candidate sha={_sha256_bytes(candidate.stdout.encode('utf-8'))}, "
            f"reference sha={_sha256_bytes(reference.stdout.encode('utf-8'))}"
        )
    if candidate.returncode != reference.returncode:
        errors.append(
            f"{label}: exit differs: candidate={candidate.returncode}, "
            f"reference={reference.returncode}"
        )
    candidate_exception = (candidate.exception_kind, candidate.exception_message)
    reference_exception = (reference.exception_kind, reference.exception_message)
    if candidate_exception != reference_exception:
        errors.append(
            f"{label}: exception differs: candidate={candidate_exception!r}, "
            f"reference={reference_exception!r}"
        )
    if candidate.stderr != reference.stderr:
        errors.append(
            f"{label}: stderr differs: candidate={_bounded(candidate.stderr)!r}, "
            f"reference={_bounded(reference.stderr)!r}"
        )
    return errors


def _dual_protocol_errors(
    default: ProtocolResult,
    competition: ProtocolResult,
) -> list[str]:
    errors: list[str] = []
    inverted = tuple("1" if answer == "0" else "0" if answer == "1" else answer
                     for answer in default.answers)
    if competition.answers != inverted:
        errors.append(
            "dual-protocol: competition transcript is not the exact bitwise inversion "
            f"of default (default count/sha={len(default.answers)}/"
            f"{_answers_sha256(default.answers)}, competition count/sha="
            f"{len(competition.answers)}/{_answers_sha256(competition.answers)})"
        )
    if competition.reject_token != default.reject_token:
        errors.append(
            "dual-protocol: first reject token differs: "
            f"default={default.reject_token}, competition={competition.reject_token}"
        )
    if competition.reject_byte_end != default.reject_byte_end:
        errors.append(
            "dual-protocol: first reject byte differs: "
            f"default={default.reject_byte_end}, competition={competition.reject_byte_end}"
        )
    return errors


def _accept_only_errors(
    result: ProtocolResult,
    token_count: int,
    *,
    competition_output: bool,
    label: str,
) -> list[str]:
    mode = "competition" if competition_output else "default"
    accept_value = "1" if competition_output else "0"
    errors: list[str] = []
    errors.extend(_strict_output_errors(result, f"{label}/{mode}"))
    if result.exception_kind is not None:
        errors.append(
            f"{label}/{mode}: {result.exception_kind}: {result.exception_message}"
        )
    elif result.returncode != 0:
        errors.append(f"{label}/{mode}: exit={result.returncode}")
    if result.stderr.strip():
        errors.append(f"{label}/{mode}: unexpected stderr={_bounded(result.stderr)!r}")
    if len(result.answers) != token_count:
        errors.append(
            f"{label}/{mode}: produced {len(result.answers)}/{token_count} answers"
        )
    invalid = [answer for answer in result.answers if answer not in {"0", "1"}]
    if invalid:
        errors.append(f"{label}/{mode}: invalid answers={invalid[:3]!r}")
    if any(answer != accept_value for answer in result.answers):
        errors.append(
            f"{label}/{mode}: expected only {accept_value}, got {result.answers[:12]!r}"
        )
    return errors


def _protocol_errors(
    case: LoadedCase,
    result: ProtocolResult,
    token_count: int,
    *,
    competition_output: bool,
) -> list[str]:
    errors: list[str] = []
    accept_value, reject_value = (("1", "0") if competition_output else ("0", "1"))
    mode = "competition" if competition_output else "default"
    errors.extend(_strict_output_errors(result, mode))
    if result.exception_kind is not None:
        errors.append(
            f"{mode}: {result.exception_kind}: {result.exception_message}; "
            f"stderr={_bounded(result.stderr)!r}"
        )
    elif result.returncode != 0:
        errors.append(
            f"{mode}: exit={result.returncode}, stderr={_bounded(result.stderr)!r}"
        )
    if result.stderr.strip():
        errors.append(f"{mode}: unexpected stderr={_bounded(result.stderr)!r}")
    invalid_answers = [answer for answer in result.answers if answer not in {"0", "1"}]
    if invalid_answers:
        errors.append(f"{mode}: invalid protocol answers={invalid_answers[:3]!r}")

    if case.expected == "accept":
        if len(result.answers) != token_count:
            errors.append(
                f"{mode}: accepted case produced {len(result.answers)}/{token_count} answers"
            )
        if any(answer != accept_value for answer in result.answers):
            errors.append(
                f"{mode}: expected only {accept_value}, got {result.answers[:12]!r}"
            )
    else:
        if result.reject_token is None:
            errors.append(f"{mode}: expected a committed rejection ({reject_value})")
        else:
            if result.answers[-1:] != (reject_value,):
                errors.append(f"{mode}: checker did not stop immediately after rejection")
            if any(answer != accept_value for answer in result.answers[:-1]):
                errors.append(f"{mode}: non-accept answer before first rejection")
            if (
                case.safe_prefix_bytes is not None
                and result.reject_byte_end is not None
                and result.reject_byte_end <= case.safe_prefix_bytes
            ):
                errors.append(
                    f"{mode}: premature rejection at byte {result.reject_byte_end}; "
                    f"known-safe prefix is {case.safe_prefix_bytes} bytes"
                )
    return errors


def _input_edge_errors(
    solution: Path,
    encoding: object,
    *,
    competition_output: bool,
    timeout: float,
    reference_solution: Path | None = None,
) -> tuple[int, list[str], list[dict[str, object]]]:
    accept_value, reject_value = (("1", "0") if competition_output else ("0", "1"))
    mode = "competition" if competition_output else "default"
    valid_tokens = encoding.encode("main")
    if len(valid_tokens) != 1:
        raise RuntimeError("expected 'main' to encode as one cl100k token")
    valid = str(valid_tokens[0])
    specs = (
        ("empty-eof", "", ()),
        ("blank-line", "\n", (reject_value,)),
        ("whitespace-line", " \t\r\n", (reject_value,)),
        ("non-decimal", "not-a-token\n", (reject_value,)),
        ("decimal-point", "1.0\n", (reject_value,)),
        ("numeric-suffix", "1x\n", (reject_value,)),
        ("negative", "-1\n", (reject_value,)),
        ("int64-overflow", "9223372036854775808\n", (reject_value,)),
        ("out-of-vocabulary", "9223372036854775807\n", (reject_value,)),
        ("explicit-positive", f"+{valid}\n", (accept_value,)),
        ("surrounding-whitespace", f" \t{valid}\r\n", (accept_value,)),
        ("stop-after-invalid", f"invalid\n{valid}\n", (reject_value,)),
        ("valid-then-invalid", f"{valid}\ninvalid\n{valid}\n", (accept_value, reject_value)),
    )
    failures: list[str] = []
    observations: list[dict[str, object]] = []
    for name, stdin, expected in specs:
        # Input-edge cases deliberately include malformed lines, so invoke with
        # their raw stdin rather than the token-list protocol used above.
        result = _run_raw_protocol(
            solution,
            stdin,
            competition_output=competition_output,
            timeout=timeout,
        )
        actual = result.answers
        format_errors = _strict_output_errors(result, f"input/{mode}/{name}")
        observation: dict[str, object] = {
            "name": name,
            "mode": mode,
            "candidate": _result_observation(result),
        }
        if (
            result.exception_kind is not None
            or result.returncode != 0
            or result.stderr.strip()
            or actual != expected
        ):
            failures.append(
                f"input/{mode}/{name}: expected answers={expected}, got={actual}, "
                f"exit={result.returncode}, exception={result.exception_kind!r}, "
                f"stderr={_bounded(result.stderr)!r}"
            )
        failures.extend(format_errors)
        if reference_solution is not None:
            reference = _run_raw_protocol(
                reference_solution,
                stdin,
                competition_output=competition_output,
                timeout=timeout,
            )
            observation["reference"] = _result_observation(reference)
            failures.extend(
                _differential_errors(
                    result, reference, label=f"input/{mode}/{name}/differential"
                )
            )
        observations.append(observation)
    return len(specs), failures, observations


def _oracle_errors(cases: Sequence[LoadedCase]) -> dict[str, str]:
    from benchmark.hidden_semantic_fuzz import (
        _configure_official_oracle,
        official_accepts,
    )

    _configure_official_oracle()
    failures: dict[str, str] = {}
    for case in cases:
        if not case.complete or not case.oracle:
            continue
        accepted, message = official_accepts(case.source)
        expected = case.expected == "accept"
        if accepted != expected:
            failures[case.name] = (
                f"oracle expected valid={expected}, got valid={accepted}: {message}"
            )
    return failures


def _grammar_errors(cases: Sequence[LoadedCase]) -> dict[str, str]:
    import xgrammar as xgr

    grammar_text = (ROOT / "grammar" / "cangjie.gbnf").read_text(encoding="utf-8")
    tokenizer = xgr.TokenizerInfo(["x"], vocab_type=xgr.VocabType.RAW)
    compiler = xgr.GrammarCompiler(tokenizer, max_threads=1, cache_enabled=False)
    compiled = compiler.compile_grammar(grammar_text)
    failures: dict[str, str] = {}
    for case in cases:
        # Scale cases are exercised through the production matcher below.  A
        # second character-at-a-time Python match would make routine corpus
        # validation disproportionately slow without adding independent signal.
        if case.family == "scale_stress":
            continue
        matcher = xgr.GrammarMatcher(compiled)
        accepted = matcher.accept_string(case.source)
        completed = accepted and matcher.is_completed()
        if case.stage in {"accept", "semantic"} and not completed:
            failures[case.name] = (
                f"grammar expected a complete program, got accepted={accepted}, "
                f"completed={completed}"
            )
        elif case.stage == "syntax" and accepted:
            failures[case.name] = "grammar expected a committed syntax rejection"
        elif case.stage == "prefix" and not accepted:
            failures[case.name] = "grammar rejected an expected-completable prefix"
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the fixed comprehensive Cangjie prefix corpus."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--solution", type=Path, default=ROOT / "solution")
    parser.add_argument(
        "--reference-solution",
        type=Path,
        help=(
            "Optional control checker. Compare every selected transcript, exit, "
            "stderr, and process exception against --solution."
        ),
    )
    parser.add_argument("--family", action="append", help="Only run this family (repeatable).")
    parser.add_argument(
        "--skip-family",
        action="append",
        help="Exclude this family (repeatable); useful for omitting scale_stress in quick runs.",
    )
    parser.add_argument("--name", help="Only run cases whose name contains this text.")
    parser.add_argument("--skip-oracle", action="store_true")
    parser.add_argument("--skip-grammar", action="store_true")
    parser.add_argument("--skip-input-edge-cases", action="store_true")
    parser.add_argument(
        "--skip-protocol",
        action="store_true",
        help="Only validate complete-program labels with the vendored oracle.",
    )
    parser.add_argument(
        "--check-competition-output",
        action="store_true",
        help="Also rerun every case with the inverted competition protocol.",
    )
    parser.add_argument(
        "--expectation-policy",
        choices=("all", "oracle-backed"),
        default="all",
        help=(
            "Treat all manifest labels as fatal (default), or make only locked "
            "authoritative labels fatal while retaining other disagreements as diagnostics."
        ),
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--list", action="store_true", help="List selected cases and exit.")
    parser.add_argument("--json", type=Path, help="Write a machine-readable result report.")
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("--timeout must be a finite positive number")

    manifest_path = args.manifest.resolve()
    try:
        manifest, cases = load_cases(manifest_path)
    except RuntimeError as error:
        parser.error(str(error))
    if args.family:
        selected = set(args.family)
        cases = [case for case in cases if case.family in selected]
    if args.skip_family:
        excluded = set(args.skip_family)
        cases = [case for case in cases if case.family not in excluded]
    if args.name:
        cases = [case for case in cases if args.name in case.name]
    if not cases:
        parser.error("no corpus cases matched the filters")
    if args.list:
        for case in cases:
            kind = "prefix" if not case.complete else case.expected
            print(f"{case.family:32} {kind:13} {case.name}")
        return 0

    solution = args.solution.resolve()
    if not args.skip_protocol and not solution.is_file():
        parser.error(f"solution does not exist: {solution}")
    reference_solution = (
        args.reference_solution.resolve() if args.reference_solution is not None else None
    )
    if reference_solution is not None and args.skip_protocol:
        parser.error("--reference-solution cannot be used with --skip-protocol")
    if reference_solution is not None and not reference_solution.is_file():
        parser.error(f"reference solution does not exist: {reference_solution}")
    if args.skip_protocol and args.skip_oracle and args.skip_grammar:
        parser.error("all validation layers were disabled")

    try:
        import tiktoken
    except ImportError as error:
        parser.error(f"tiktoken is required: {error}")
    encoding = tiktoken.get_encoding("cl100k_base")
    try:
        tiktoken_version = importlib.metadata.version("tiktoken")
    except importlib.metadata.PackageNotFoundError:
        tiktoken_version = getattr(tiktoken, "__version__", "unknown")

    failures: dict[str, list[str]] = {}
    diagnostic_disagreements: dict[str, list[str]] = {}

    def record_case_errors(case: LoadedCase, messages: Sequence[str]) -> None:
        if not messages:
            return
        if args.expectation_policy == "all" or case.expectation_tier == "authoritative":
            failures.setdefault(case.name, []).extend(messages)
        else:
            diagnostic_disagreements.setdefault(case.name, []).extend(messages)

    def record_reference_errors(
        case: LoadedCase,
        messages: Sequence[str],
        *,
        candidate: ProtocolResult | None = None,
        reference: ProtocolResult | None = None,
    ) -> None:
        if not messages:
            return
        if case.expectation_tier != "diagnostic_scale":
            failures.setdefault(case.name, []).extend(messages)
            return
        if reference is not None and reference.exception_kind == "TimeoutExpired":
            if candidate is not None and candidate.exception_kind != "TimeoutExpired":
                # A scale control timeout is not an equivalence oracle.  A candidate
                # that completes is judged by the scale label diagnostic instead.
                return
            diagnostic_disagreements.setdefault(case.name, []).extend(messages)
        elif reference is not None:
            # Once the scale control completes, exact candidate equivalence is hard.
            failures.setdefault(case.name, []).extend(messages)
        else:
            diagnostic_disagreements.setdefault(case.name, []).extend(messages)
    grammar_checked = 0
    if not args.skip_grammar:
        grammar_checked = sum(case.family != "scale_stress" for case in cases)
        for name, message in _grammar_errors(cases).items():
            case = next(case for case in cases if case.name == name)
            record_case_errors(case, [message])
    oracle_checked = 0
    if not args.skip_oracle:
        oracle_checked = sum(case.complete and case.oracle for case in cases)
        for name, message in _oracle_errors(cases).items():
            case = next(case for case in cases if case.name == name)
            record_case_errors(case, [message])

    modes = ([False, True] if args.check_competition_output else [False]) if not args.skip_protocol else []
    protocol_runs = 0
    reference_protocol_runs = 0
    safe_prefix_runs = 0
    reference_safe_prefix_runs = 0
    observations: list[dict[str, object]] = []
    protocol_cases = [] if args.fail_fast and failures else cases
    for case in protocol_cases:
        token_ids = encoding.encode(case.source)
        token_chunks = [encoding.decode_single_token_bytes(token) for token in token_ids]
        case_observation: dict[str, object] = {
            "name": case.name,
            "family": case.family,
            "source_sha256": case.source_sha256,
            "token_count": len(token_ids),
            "candidate": {},
        }
        candidate_results: dict[bool, ProtocolResult] = {}
        reference_results: dict[bool, ProtocolResult] = {}
        for competition_output in modes:
            mode = "competition" if competition_output else "default"
            protocol_runs += 1
            result = _run_protocol(
                solution,
                token_ids,
                token_chunks,
                competition_output=competition_output,
                timeout=args.timeout,
            )
            candidate_results[competition_output] = result
            candidate_observations = case_observation["candidate"]
            assert isinstance(candidate_observations, dict)
            candidate_observations[mode] = _result_observation(result)
            errors = _protocol_errors(
                case,
                result,
                len(token_ids),
                competition_output=competition_output,
            )
            if errors:
                record_case_errors(case, errors)
            if reference_solution is not None:
                reference_protocol_runs += 1
                reference = _run_protocol(
                    reference_solution,
                    token_ids,
                    token_chunks,
                    competition_output=competition_output,
                    timeout=args.timeout,
                )
                reference_results[competition_output] = reference
                reference_observations = case_observation.setdefault("reference", {})
                assert isinstance(reference_observations, dict)
                reference_observations[mode] = _result_observation(reference)
                if (
                    case.expectation_tier == "diagnostic_scale"
                    and reference.exception_kind == "TimeoutExpired"
                    and result.exception_kind != "TimeoutExpired"
                    and errors
                ):
                    failures.setdefault(case.name, []).extend(
                        "scale candidate completed but violated its label: " + message
                        for message in errors
                    )
                diff_errors = _differential_errors(
                    result, reference, label=f"{mode}/differential"
                )
                if diff_errors:
                    record_reference_errors(
                        case, diff_errors, candidate=result, reference=reference
                    )
            if args.fail_fast and failures:
                break
        if len(modes) == 2 and all(mode in candidate_results for mode in modes):
            dual_errors = _dual_protocol_errors(
                candidate_results[False], candidate_results[True]
            )
            if dual_errors:
                record_case_errors(case, dual_errors)
            if reference_solution is not None and all(
                mode in reference_results for mode in modes
            ):
                reference_dual_errors = [
                    "reference/" + message
                    for message in _dual_protocol_errors(
                        reference_results[False], reference_results[True]
                    )
                ]
                if reference_dual_errors:
                    record_reference_errors(case, reference_dual_errors)

        if (
            not (args.fail_fast and failures)
            and modes
            and case.expected == "reject"
            and case.safe_prefix_bytes is not None
        ):
            source_bytes = case.source.encode("utf-8")
            safe_source_bytes = source_bytes[:case.safe_prefix_bytes]
            # load_cases already proved this byte boundary decodes as UTF-8.
            safe_source = safe_source_bytes.decode("utf-8")
            safe_token_ids = encoding.encode(safe_source)
            safe_token_chunks = [
                encoding.decode_single_token_bytes(token) for token in safe_token_ids
            ]
            safe_observation: dict[str, object] = {
                "byte_count": case.safe_prefix_bytes,
                "source_sha256": _sha256_bytes(safe_source_bytes),
                "token_count": len(safe_token_ids),
                "candidate": {},
            }
            safe_candidate_results: dict[bool, ProtocolResult] = {}
            safe_reference_results: dict[bool, ProtocolResult] = {}
            for competition_output in modes:
                mode = "competition" if competition_output else "default"
                safe_prefix_runs += 1
                safe_result = _run_protocol(
                    solution,
                    safe_token_ids,
                    safe_token_chunks,
                    competition_output=competition_output,
                    timeout=args.timeout,
                )
                safe_candidate_results[competition_output] = safe_result
                safe_candidate_observations = safe_observation["candidate"]
                assert isinstance(safe_candidate_observations, dict)
                safe_candidate_observations[mode] = _result_observation(safe_result)
                safe_errors = _accept_only_errors(
                    safe_result,
                    len(safe_token_ids),
                    competition_output=competition_output,
                    label="safe-prefix",
                )
                if safe_errors:
                    record_case_errors(case, safe_errors)
                if reference_solution is not None:
                    reference_safe_prefix_runs += 1
                    safe_reference = _run_protocol(
                        reference_solution,
                        safe_token_ids,
                        safe_token_chunks,
                        competition_output=competition_output,
                        timeout=args.timeout,
                    )
                    safe_reference_results[competition_output] = safe_reference
                    safe_reference_observations = safe_observation.setdefault(
                        "reference", {}
                    )
                    assert isinstance(safe_reference_observations, dict)
                    safe_reference_observations[mode] = _result_observation(
                        safe_reference
                    )
                    if (
                        case.expectation_tier == "diagnostic_scale"
                        and safe_reference.exception_kind == "TimeoutExpired"
                        and safe_result.exception_kind != "TimeoutExpired"
                        and safe_errors
                    ):
                        failures.setdefault(case.name, []).extend(
                            "scale candidate completed but violated safe prefix: " + message
                            for message in safe_errors
                        )
                    safe_diff_errors = _differential_errors(
                        safe_result,
                        safe_reference,
                        label=f"safe-prefix/{mode}/differential",
                    )
                    if safe_diff_errors:
                        record_reference_errors(
                            case,
                            safe_diff_errors,
                            candidate=safe_result,
                            reference=safe_reference,
                        )
                if args.fail_fast and failures:
                    break
            if len(modes) == 2 and all(
                mode in safe_candidate_results for mode in modes
            ):
                safe_dual_errors = [
                    "safe-prefix/" + message
                    for message in _dual_protocol_errors(
                        safe_candidate_results[False], safe_candidate_results[True]
                    )
                ]
                if safe_dual_errors:
                    record_case_errors(case, safe_dual_errors)
                if reference_solution is not None and all(
                    mode in safe_reference_results for mode in modes
                ):
                    safe_reference_dual_errors = [
                        "safe-prefix/reference/" + message
                        for message in _dual_protocol_errors(
                            safe_reference_results[False], safe_reference_results[True]
                        )
                    ]
                    if safe_reference_dual_errors:
                        record_reference_errors(case, safe_reference_dual_errors)
            case_observation["safe_prefix"] = safe_observation
        observations.append(case_observation)
        if args.fail_fast and failures:
            break

    input_edge_runs = 0
    reference_input_edge_runs = 0
    input_edge_observations: list[dict[str, object]] = []
    if (
        not args.skip_protocol
        and not args.skip_input_edge_cases
        and not (args.fail_fast and failures)
    ):
        for competition_output in modes:
            runs, errors, edge_observations = _input_edge_errors(
                solution,
                encoding,
                competition_output=competition_output,
                timeout=args.timeout,
                reference_solution=reference_solution,
            )
            input_edge_runs += runs
            if reference_solution is not None:
                reference_input_edge_runs += runs
            input_edge_observations.extend(edge_observations)
            if errors:
                failures.setdefault("__protocol_input_edges__", []).extend(errors)

    selected_counts: dict[str, int] = {}
    for case in cases:
        selected_counts[case.family] = selected_counts.get(case.family, 0) + 1
    known_case_names = {case.name for case in cases}
    case_failure_names = {name for name in failures if name in known_case_names}
    executed_names = {str(observation["name"]) for observation in observations}
    if args.skip_protocol and not (args.fail_fast and failures):
        executed_names = set(known_case_names)
    elif args.fail_fast and failures and not executed_names:
        # A fatal grammar/oracle precheck can stop before the protocol loop.
        # Count the offending cases as executed so passed+failed remains
        # internally consistent, while grammar_checked/oracle_checked retain
        # the exact number of static checks that were performed.
        executed_names = set(case_failure_names)
    case_failure_count = len(case_failure_names)
    infrastructure_failure_count = len(failures) - case_failure_count
    authoritative_names = {
        case.name for case in cases if case.expectation_tier == "authoritative"
    }
    diagnostic_names = {case.name for case in cases} - authoritative_names
    executed_authoritative = authoritative_names & executed_names
    executed_diagnostic = diagnostic_names & executed_names
    summary = {
        "manifest": str(manifest_path),
        "manifest_case_count": manifest["case_count"],
        "selected_cases": len(cases),
        "executed_cases": len(executed_names),
        "aborted": bool(args.fail_fast and failures)
        or len(executed_names) < len(cases),
        "families": dict(sorted(selected_counts.items())),
        "grammar_checked": grammar_checked,
        "oracle_checked": oracle_checked,
        "protocol_modes": len(modes),
        "protocol_runs": protocol_runs,
        "reference_protocol_runs": reference_protocol_runs,
        "safe_prefix_runs": safe_prefix_runs,
        "reference_safe_prefix_runs": reference_safe_prefix_runs,
        "input_edge_runs": input_edge_runs,
        "reference_input_edge_runs": reference_input_edge_runs,
        "passed_cases": len(executed_names - case_failure_names),
        "failed_cases": case_failure_count,
        "infrastructure_failures": infrastructure_failure_count,
        "expectation_policy": args.expectation_policy,
        "authoritative_cases": len(authoritative_names),
        "authoritative_executed": len(executed_authoritative),
        "authoritative_passed": len(executed_authoritative - case_failure_names),
        "authoritative_failed": len(executed_authoritative & case_failure_names),
        "diagnostic_cases": len(diagnostic_names),
        "diagnostic_executed": len(executed_diagnostic),
        "diagnostic_disagreements": len(diagnostic_disagreements),
        "scale_cases": sum(case.expectation_tier == "diagnostic_scale" for case in cases),
    }
    report = {
        "provenance": {
            "manifest_sha256": _sha256_file(manifest_path),
            "solution_sha256": (
                _sha256_file(solution) if not args.skip_protocol else None
            ),
            "reference_solution_sha256": (
                _sha256_file(reference_solution)
                if reference_solution is not None
                else None
            ),
            "tiktoken_version": tiktoken_version,
        },
        "summary": summary,
        "observations": observations,
        "input_edge_observations": input_edge_observations,
        "failures": [
            {"name": name, "messages": messages}
            for name, messages in sorted(failures.items())
        ],
        "diagnostic_disagreements": [
            {"name": name, "messages": messages}
            for name, messages in sorted(diagnostic_disagreements.items())
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failures:
        for name, messages in sorted(failures.items()):
            print(f"\n[FAIL] {name}", file=sys.stderr)
            for message in messages:
                print(f"  - {message}", file=sys.stderr)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
