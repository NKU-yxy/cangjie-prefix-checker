#!/usr/bin/env python3
"""Collect raw G4 long-identifier scale observations without issuing a verdict.

The subprocess/RSS execution core is reused from the immutable audit collector
at ``tools/audit_harness.py``.
That source is verified before import against SHA-256
``5c8fe5e6dc44c3aa5048702fdaf33738110bcca8df1776435e21bd82759057a3``.
The reuse keeps timeout cleanup, exact transcript retention, and 5 ms
``/proc/PID/status`` sampling identical to the independently reviewed G1
collector while this file owns a new, immutable G4 trial plan.

This is intentionally a collector only.  Exit status zero means that the
schedule finished and the raw checkpoint exists; it is not an optimization,
correctness, RSS, or acceptance verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import statistics
import struct
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from typing import Any, Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
G1_CORE_RELATIVE_PATH = Path(
    "tools/audit_harness.py"
)
G1_CORE_SHA256 = "5c8fe5e6dc44c3aa5048702fdaf33738110bcca8df1776435e21bd82759057a3"

LOCKED_ACCEPTED_CONTROL_SHA = "f5f2468c343e7ccc18d48cba0eab0a10920ee1c6"
LOCKED_OFFICIAL_SHA = "88336c400e7a4a671424e3e6c46c0866c8c0af93"
LOCKED_OFFICIAL_REGISTRY_SHA256 = (
    "2425e64184d69dd392f6cdec52dc20d42d0977cbe84be744a0ffbd1dfad374f2"
)
LOCKED_IMAGE = "docker.educg.net/compiler_system_challenge/cjchecker:20260522"
LOCKED_IMAGE_DIGEST = (
    "sha256:980dd9f2ede4f0132e9c71c71c1d6553cafd5de7cf1977c2ffe97a5ab34b8c90"
)
LOCKED_INPUT_SHA256 = {
    "build.sh": "2a6a99ad3b89b9977f79ffca75a7f977254c4267542345cc03d0c0a2bd951498",
    "context.json": "8058e383390f444f56ee4ac0008493c44c8e32fa632d18ed48f998dc36623348",
    "grammar/cangjie.gbnf": (
        "eb4a5cd0b705407281860bd2ddf1e20b97ad48aceafd96621d55c1385c06ca90"
    ),
    "grammar/cangjie_token.gbnf": (
        "1cb6503b4ce8c24b6a4f12b7ff0ee1a7e8f4d09273bf4e87d254749209096cc1"
    ),
    "test_cases/comprehensive/manifest.json": (
        "b3ac3ccfc845ac37e61ed2146fefb61b67ae6b78336b8d80338486bd0806768e"
    ),
}

IDENTIFIER_LENGTHS = tuple(2**exponent for exponent in range(15))
PROTOCOLS = ("default", "competition")
ROLES = ("control", "candidate")
REPETITIONS_PER_ROLE = 3
TIMEOUT_SECONDS = 30.0
EXIT_TIMEOUT_SECONDS = 2.0
RSS_SAMPLE_MS = 5.0

MANIFEST_ANCHOR_NAME = "four-kilobyte-identifier"
MANIFEST_ANCHOR_CASE_NAME = "manifest-four-kib-identifier"
MANIFEST_ANCHOR_SOURCE_SHA256 = (
    "57b6ce855e91c132382647485601dfb361f8ffb045695407265d2046cb036306"
)
MANIFEST_ANCHOR_SOURCE_BYTES = 4135
MANIFEST_ANCHOR_IDENTIFIER_BYTES = 4102
MANIFEST_ANCHOR_TOKEN_COUNT = 527
LOCKED_FULL_TRIAL_PLAN_SHA256 = (
    "2de4ed81ada7f2f2993d1db6c7d5df33907c960c833b0ce5aa83739934e736e1"
)


class HarnessError(RuntimeError):
    """A locked precondition or collector invariant failed."""


@dataclass(frozen=True)
class IdentifierCase:
    name: str
    source: str
    source_sha256: str
    source_path: str
    origin: str
    identifier_bytes: int
    sweep_length: int | None
    manifest_item: dict[str, Any] | None = None


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _load_g1_core() -> Any:
    source = PROJECT_ROOT / G1_CORE_RELATIVE_PATH
    if not source.is_file():
        raise RuntimeError(f"locked G1 collector core is missing: {source}")
    observed = _sha256_file(source)
    if observed != G1_CORE_SHA256:
        raise RuntimeError(
            "locked G1 collector core digest mismatch: "
            f"observed {observed}, expected {G1_CORE_SHA256}"
        )
    module_name = "_locked_g1_audit_harness_core_for_g4"
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import locked G1 collector core: {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


G1_CORE = _load_g1_core()


def identifier_source(length: int) -> str:
    """Return the one locked, no-newline/no-semicolon G4 sweep source."""
    if isinstance(length, bool) or not isinstance(length, int) or length < 1:
        raise ValueError("identifier length must be a positive integer")
    identifier = "a" + "x" * (length - 1)
    source = f"main(): Unit {{ let {identifier}: Int64 = 1 }}"
    if len(identifier) != length or len(identifier.encode("ascii")) != length:
        raise AssertionError("generated identifier length invariant failed")
    return source


def build_generated_cases() -> list[IdentifierCase]:
    cases: list[IdentifierCase] = []
    for length in IDENTIFIER_LENGTHS:
        source = identifier_source(length)
        cases.append(
            IdentifierCase(
                name=f"identifier-length-{length:05d}",
                source=source,
                source_sha256=_sha256_bytes(source.encode("utf-8")),
                source_path="<locked-g4-identifier-generator>",
                origin="locked-g4-fixed-source-template-v1",
                identifier_bytes=length,
                sweep_length=length,
            )
        )
    return cases


def _manifest_anchor_expected_source() -> str:
    # This intentionally differs from the L=4096 sweep case: its identifier is
    # ``value_`` plus 4096 x characters (4102 identifier bytes), and it ends in LF.
    return f"main(): Unit {{ let value_{'x' * 4096}: Int64 = 1 }}\n"


def _read_utf8(path: Path, label: str) -> tuple[bytes, str]:
    try:
        raw = path.read_bytes()
        return raw, raw.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise HarnessError(f"cannot read UTF-8 {label} {path}: {error}") from error


def _load_manifest_anchor(root: Path, label: str) -> tuple[IdentifierCase, dict[str, Any]]:
    manifest_path = root / "test_cases/comprehensive/manifest.json"
    raw, text = _read_utf8(manifest_path, f"{label} comprehensive manifest")
    manifest_digest = _sha256_bytes(raw)
    expected_manifest_digest = LOCKED_INPUT_SHA256[
        "test_cases/comprehensive/manifest.json"
    ]
    if manifest_digest != expected_manifest_digest:
        raise HarnessError(
            f"{label} manifest digest is {manifest_digest}, expected {expected_manifest_digest}"
        )
    try:
        manifest = json.loads(text)
    except json.JSONDecodeError as error:
        raise HarnessError(f"invalid {label} manifest JSON: {error}") from error
    items = [
        item
        for item in manifest.get("cases", [])
        if isinstance(item, dict) and item.get("name") == MANIFEST_ANCHOR_NAME
    ]
    if len(items) != 1:
        raise HarnessError(
            f"{label} manifest must contain exactly one {MANIFEST_ANCHOR_NAME!r} case"
        )
    item = items[0]
    required = {
        "family": "scale_stress",
        "expected": "accept",
        "complete": True,
        "source_bytes": MANIFEST_ANCHOR_SOURCE_BYTES,
        "source_sha256": MANIFEST_ANCHOR_SOURCE_SHA256,
        "expectation_tier": "diagnostic_scale",
    }
    mismatches = {
        key: {"observed": item.get(key), "expected": value}
        for key, value in required.items()
        if item.get(key) != value
    }
    if mismatches:
        raise HarnessError(f"{label} manifest anchor metadata mismatch: {mismatches}")
    relative = item.get("file")
    if not isinstance(relative, str) or not relative.endswith(".cj"):
        raise HarnessError(f"{label} manifest anchor has invalid file={relative!r}")
    try:
        source_path = G1_CORE._resolve_beneath(  # pylint: disable=protected-access
            manifest_path.parent, relative, f"{label} manifest anchor file"
        )
    except G1_CORE.HarnessError as error:
        raise HarnessError(str(error)) from error
    source_raw, source = _read_utf8(source_path, f"{label} manifest anchor")
    if len(source_raw) != MANIFEST_ANCHOR_SOURCE_BYTES:
        raise HarnessError(
            f"{label} manifest anchor is {len(source_raw)} bytes, "
            f"expected {MANIFEST_ANCHOR_SOURCE_BYTES}"
        )
    source_digest = _sha256_bytes(source_raw)
    if source_digest != MANIFEST_ANCHOR_SOURCE_SHA256:
        raise HarnessError(
            f"{label} manifest anchor digest is {source_digest}, "
            f"expected {MANIFEST_ANCHOR_SOURCE_SHA256}"
        )
    if source != _manifest_anchor_expected_source():
        raise HarnessError(
            f"{label} manifest anchor is not the locked value_ + 4096*x source template"
        )
    case = IdentifierCase(
        name=MANIFEST_ANCHOR_CASE_NAME,
        source=source,
        source_sha256=source_digest,
        source_path=str(source_path.resolve()),
        origin=f"{label}-locked-comprehensive-manifest",
        identifier_bytes=MANIFEST_ANCHOR_IDENTIFIER_BYTES,
        sweep_length=None,
        manifest_item=dict(item),
    )
    return case, {
        "path": str(manifest_path.resolve()),
        "sha256": manifest_digest,
        "schema_version": manifest.get("schema_version"),
        "case_count": manifest.get("case_count"),
        "anchor_item": dict(item),
        "anchor_path": str(source_path.resolve()),
        "anchor_source_sha256": source_digest,
        "anchor_source_bytes": len(source_raw),
        "anchor_identifier_bytes": MANIFEST_ANCHOR_IDENTIFIER_BYTES,
    }


def build_trial_plan(cases: Sequence[IdentifierCase]) -> list[dict[str, Any]]:
    """Build stable logical trial IDs before any subprocess is started."""
    names = [case.name for case in cases]
    if len(names) != len(set(names)):
        raise ValueError("identifier case names must be unique")
    plan: list[dict[str, Any]] = []
    ordinal = 0
    for case_index, case in enumerate(cases):
        for protocol_index, protocol in enumerate(PROTOCOLS):
            first_role = ROLES[(case_index + protocol_index) % len(ROLES)]
            second_role = ROLES[1 - ROLES.index(first_role)]
            role_repetitions = {role: 0 for role in ROLES}
            for role in (first_role, second_role) * REPETITIONS_PER_ROLE:
                role_repetitions[role] += 1
                ordinal += 1
                repetition = role_repetitions[role]
                trial_id = (
                    f"g4-identifier-scale-v1/{case.name}/{protocol}/"
                    f"{role}/r{repetition}"
                )
                plan.append(
                    {
                        "ordinal": ordinal,
                        "trial_id": trial_id,
                        "case_name": case.name,
                        "case_source_sha256": case.source_sha256,
                        "identifier_bytes": case.identifier_bytes,
                        "sweep_length": case.sweep_length,
                        "protocol": protocol,
                        "role": role,
                        "role_repetition": repetition,
                        "timeout_seconds": TIMEOUT_SECONDS,
                        "exit_timeout_seconds": EXIT_TIMEOUT_SECONDS,
                        "rss_sample_ms": RSS_SAMPLE_MS,
                    }
                )
    trial_ids = [entry["trial_id"] for entry in plan]
    if len(trial_ids) != len(set(trial_ids)):
        raise AssertionError("generated duplicate permanent trial IDs")
    return plan


def _canonical_json_sha256(value: Any) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _sha256_bytes(raw)


def _validate_full_sha(value: str, label: str) -> None:
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise HarnessError(f"{label} must be a full lowercase 40-hex Git SHA")


def validate_cli_shape(args: argparse.Namespace) -> None:
    for attribute in ("control_sha", "candidate_sha", "official_sha"):
        _validate_full_sha(getattr(args, attribute), f"--{attribute.replace('_', '-')}")
    if args.control_sha != LOCKED_ACCEPTED_CONTROL_SHA:
        raise HarnessError(
            f"--control-sha must be accepted G1 control {LOCKED_ACCEPTED_CONTROL_SHA}"
        )
    if args.official_sha != LOCKED_OFFICIAL_SHA:
        raise HarnessError(f"--official-sha must be locked official {LOCKED_OFFICIAL_SHA}")
    if args.candidate_sha == args.control_sha:
        raise HarnessError("candidate and control SHAs must differ")
    resolved_roots = {
        args.control_root.resolve(),
        args.candidate_root.resolve(),
        args.official_root.resolve(),
    }
    if len(resolved_roots) != 3:
        raise HarnessError("control, candidate, and official roots must be distinct")


def _preflight_output(output: Path, protected_roots: Sequence[Path]) -> Path:
    resolved = output.resolve()
    if output.exists() or output.is_symlink() or resolved.exists():
        raise HarnessError(f"output already exists; refusing to overwrite: {resolved}")
    for root in protected_roots:
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            continue
        raise HarnessError(f"output must be outside audited root {root.resolve()}: {resolved}")
    return resolved


def _reserve_output(output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise HarnessError(f"output appeared during preflight: {output}") from error
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _repo_artifact_hashes(root: Path, label: str) -> dict[str, str]:
    observed: dict[str, str] = {}
    for relative, expected in LOCKED_INPUT_SHA256.items():
        path = root / relative
        if not path.is_file():
            raise HarnessError(f"{label} locked input is missing: {path}")
        digest = _sha256_file(path)
        if digest != expected:
            raise HarnessError(
                f"{label} {relative} digest is {digest}, expected locked {expected}"
            )
        observed[relative] = digest
    return observed


def _elf_aarch64_metadata(path: Path, label: str) -> dict[str, Any]:
    header = path.read_bytes()[:64]
    if len(header) < 20 or header[:4] != b"\x7fELF":
        raise HarnessError(f"{label} solution is not an ELF binary: {path}")
    if header[4] != 2 or header[5] != 1:
        raise HarnessError(
            f"{label} solution must be 64-bit little-endian ELF, "
            f"observed class={header[4]} data={header[5]}"
        )
    machine = struct.unpack_from("<H", header, 18)[0]
    if machine != 183:
        raise HarnessError(
            f"{label} solution ELF machine is {machine}, expected AArch64 (183)"
        )
    return {
        "elf_class": 64,
        "elf_endianness": "little",
        "elf_machine": machine,
        "elf_machine_name": "AArch64",
    }


def _verify_source_clean(repo: dict[str, Any], label: str) -> None:
    forbidden: list[dict[str, Any]] = []
    for entry in repo["status_porcelain_entries"]:
        path = entry["path"]
        allowed_path = path == "solution" or path.startswith("generated/")
        allowed = allowed_path and not entry["staged"] and entry["original_path"] is None
        if not allowed:
            forbidden.append(entry)
    if forbidden:
        raise HarnessError(
            f"{label} source root is not clean apart from unstaged build outputs: {forbidden}"
        )


def _git_is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", ancestor, descendant],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode not in {0, 1}:
        raise HarnessError(
            "git merge-base --is-ancestor failed: "
            + proc.stderr.decode("utf-8", errors="replace").strip()
        )
    return proc.returncode == 0


def _read_optional_proc(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _locked_artifacts(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Path]]:
    roots = {
        "control": args.control_root.resolve(),
        "candidate": args.candidate_root.resolve(),
        "official": args.official_root.resolve(),
    }
    try:
        repositories = {
            "control": G1_CORE._verify_locked_repo(  # pylint: disable=protected-access
                roots["control"],
                args.control_sha,
                "control",
                allow_build_artifacts=True,
                require_no_alternates=True,
            ),
            "candidate": G1_CORE._verify_locked_repo(  # pylint: disable=protected-access
                roots["candidate"],
                args.candidate_sha,
                "candidate",
                allow_build_artifacts=True,
                require_no_alternates=True,
            ),
            "official": G1_CORE._verify_locked_repo(  # pylint: disable=protected-access
                roots["official"],
                args.official_sha,
                "official",
                allow_build_artifacts=False,
                require_no_alternates=False,
            ),
        }
    except G1_CORE.HarnessError as error:
        raise HarnessError(str(error)) from error
    for role in ROLES:
        _verify_source_clean(repositories[role], role)
    if repositories["official"]["status_entry_count"]:
        raise HarnessError("official root must be completely clean")

    identities = [
        (
            repositories[role]["objects_dir_realpath"],
            repositories[role]["objects_dir_device"],
            repositories[role]["objects_dir_inode"],
        )
        for role in ROLES
    ]
    if identities[0] == identities[1] or identities[0][0] == identities[1][0]:
        raise HarnessError("control and candidate must have distinct clone-local Git objects")
    if not _git_is_ancestor(
        roots["candidate"], LOCKED_ACCEPTED_CONTROL_SHA, args.candidate_sha
    ):
        raise HarnessError("candidate commit is not descended from the accepted G1 control")

    artifact_hashes = {
        role: _repo_artifact_hashes(roots[role], role) for role in ROLES
    }
    if artifact_hashes["control"] != artifact_hashes["candidate"]:
        raise HarnessError("control and candidate locked input digests differ")

    solutions: dict[str, dict[str, Any]] = {}
    solution_paths: dict[str, Path] = {}
    for role in ROLES:
        solution_path = (roots[role] / "solution").resolve()
        try:
            metadata = G1_CORE._verify_solution(  # pylint: disable=protected-access
                solution_path,
                roots[role],
                role,
                allow_profile_override=False,
            )
        except G1_CORE.HarnessError as error:
            raise HarnessError(str(error)) from error
        metadata.update(_elf_aarch64_metadata(solution_path, role))
        solutions[role] = metadata
        solution_paths[role] = solution_path

    registry = roots["official"] / "wrong_error_positions.json"
    if not registry.is_file():
        raise HarnessError(f"official registry is missing: {registry}")
    registry_digest = _sha256_file(registry)
    if registry_digest != LOCKED_OFFICIAL_REGISTRY_SHA256:
        raise HarnessError(
            f"official registry digest is {registry_digest}, "
            f"expected {LOCKED_OFFICIAL_REGISTRY_SHA256}"
        )

    return {
        "repositories": repositories,
        "solutions": solutions,
        "locked_input_sha256": artifact_hashes,
        "official_registry": {
            "path": str(registry.resolve()),
            "sha256": registry_digest,
        },
        "clone_independence": {
            "all_root_realpaths_distinct": True,
            "control_candidate_objects_distinct": True,
            "control_alternates_absent": True,
            "candidate_alternates_absent": True,
            "candidate_descends_from_accepted_control": True,
        },
    }, {
        **roots,
        "control_solution": solution_paths["control"],
        "candidate_solution": solution_paths["candidate"],
    }


def _case_record(
    case: IdentifierCase, token_ids: Sequence[int], token_chunks: Sequence[bytes]
) -> dict[str, Any]:
    return {
        "name": case.name,
        "expected": "accept",
        "origin": case.origin,
        "source_path": case.source_path,
        "source_sha256": case.source_sha256,
        "source_bytes": len(case.source.encode("utf-8")),
        "source_utf8": case.source,
        "source_raw_b64": G1_CORE._b64(case.source.encode("utf-8")),  # pylint: disable=protected-access
        "identifier_bytes": case.identifier_bytes,
        "sweep_length": case.sweep_length,
        "is_manifest_anchor": case.name == MANIFEST_ANCHOR_CASE_NAME,
        "token_count": len(token_ids),
        "token_ids": list(token_ids),
        "token_ids_sha256": _sha256_bytes(
            b"".join(int(token).to_bytes(4, "big", signed=False) for token in token_ids)
        ),
        "token_chunks_raw_b64": [
            G1_CORE._b64(chunk) for chunk in token_chunks  # pylint: disable=protected-access
        ],
        "token_byte_lengths": [len(chunk) for chunk in token_chunks],
        "manifest_item": case.manifest_item,
    }


def _event_timeline(run: dict[str, Any]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [{"elapsed_ns": 0, "kind": "process_start"}]
    for item in run["token_send_events"]:
        common = {"token_index": item["token_index"], "token_id": item["token_id"]}
        events.append(
            {
                "elapsed_ns": item["write_started_elapsed_ns"],
                "kind": "token_write_started",
                **common,
            }
        )
        events.append(
            {
                "elapsed_ns": item["flushed_elapsed_ns"],
                "kind": "token_flushed",
                **common,
            }
        )
    for item in run["response_events"]:
        events.append(
            {
                "elapsed_ns": item["response_elapsed_ns"],
                "kind": "response",
                "token_index": item["token_index"],
                "token_id": item["token_id"],
                "strict_bit": item["strict_bit"],
                "raw_b64": item["raw_b64"],
                "response_source": item["response_source"],
            }
        )
    if run["deadline_elapsed_ns"] is not None:
        events.append(
            {"elapsed_ns": run["deadline_elapsed_ns"], "kind": "deadline_observed"}
        )
    if run["cleanup_started_elapsed_ns"] is not None:
        events.append(
            {
                "elapsed_ns": run["cleanup_started_elapsed_ns"],
                "kind": "cleanup_started",
            }
        )
    events.append(
        {
            "elapsed_ns": run["process_total_ns"],
            "kind": "process_complete",
            "returncode": run["returncode"],
            "termination": run["termination"],
        }
    )
    priority = {
        "process_start": 0,
        "token_write_started": 1,
        "token_flushed": 2,
        "response": 3,
        "deadline_observed": 4,
        "cleanup_started": 5,
        "process_complete": 6,
    }
    return sorted(events, key=lambda item: (item["elapsed_ns"], priority[item["kind"]]))


def _group_summaries(report: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for case in report["cases"]:
        for protocol in PROTOCOLS:
            for role in ROLES:
                runs = [
                    run
                    for run in report["runs"]
                    if run["case_name"] == case["name"]
                    and run["protocol"] == protocol
                    and run["role"] == role
                ]
                completed = [run for run in runs if not run["timed_out"]]
                times = [run["process_total_ns"] for run in completed]
                rss = [
                    run["rss"]["gate_peak_vmhwm_kib"]
                    for run in runs
                    if run["rss"]["gate_peak_vmhwm_kib"] is not None
                ]
                result.append(
                    {
                        "case_name": case["name"],
                        "protocol": protocol,
                        "role": role,
                        "planned_trials": REPETITIONS_PER_ROLE,
                        "observed_trials": len(runs),
                        "completed_trials": len(completed),
                        "timed_out_trials": sum(run["timed_out"] for run in runs),
                        "case_ok_trials": sum(run["case_ok"] for run in runs),
                        "completed_process_total_ns_median": (
                            None if not times else statistics.median(times)
                        ),
                        "gate_peak_vmhwm_kib_median": (
                            None if not rss else statistics.median(rss)
                        ),
                        "collector_only_no_verdict": True,
                    }
                )
    return result


def _atomic_checkpoint(output: Path, report: dict[str, Any]) -> None:
    report["last_checkpoint_unix_ns"] = time.time_ns()
    G1_CORE._atomic_write_json(output, report)  # pylint: disable=protected-access


def collect(args: argparse.Namespace) -> int:
    validate_cli_shape(args)
    protected_roots = (args.control_root, args.candidate_root, args.official_root)
    output = _preflight_output(args.output, protected_roots)

    artifacts, paths = _locked_artifacts(args)
    try:
        environment = G1_CORE._environment_metadata(False)  # pylint: disable=protected-access
    except G1_CORE.HarnessError as error:
        raise HarnessError(str(error)) from error

    control_anchor, control_manifest = _load_manifest_anchor(paths["control"], "control")
    candidate_anchor, candidate_manifest = _load_manifest_anchor(
        paths["candidate"], "candidate"
    )
    if (
        control_anchor.source_sha256 != candidate_anchor.source_sha256
        or control_anchor.source.encode("utf-8") != candidate_anchor.source.encode("utf-8")
    ):
        raise HarnessError("control and candidate manifest anchor sources differ")

    cases = build_generated_cases()
    if args.include_manifest_anchor:
        cases.append(candidate_anchor)

    try:
        encoding = G1_CORE._load_encoding(paths["official"])  # pylint: disable=protected-access
    except G1_CORE.HarnessError as error:
        raise HarnessError(str(error)) from error
    tokenized: dict[str, tuple[list[int], list[bytes]]] = {}
    for case in cases:
        try:
            token_ids = G1_CORE._tokenize(encoding, case.source)  # pylint: disable=protected-access
            token_chunks = G1_CORE._token_chunks(  # pylint: disable=protected-access
                encoding, token_ids, case.source
            )
        except G1_CORE.HarnessError as error:
            raise HarnessError(str(error)) from error
        tokenized[case.name] = (token_ids, token_chunks)
    if args.include_manifest_anchor:
        observed_anchor_tokens = len(tokenized[MANIFEST_ANCHOR_CASE_NAME][0])
        if observed_anchor_tokens != MANIFEST_ANCHOR_TOKEN_COUNT:
            raise HarnessError(
                f"manifest anchor token count is {observed_anchor_tokens}, "
                f"expected locked {MANIFEST_ANCHOR_TOKEN_COUNT}"
            )

    trial_plan = build_trial_plan(cases)
    expected_trials = len(cases) * len(PROTOCOLS) * len(ROLES) * REPETITIONS_PER_ROLE
    if len(trial_plan) != expected_trials:
        raise AssertionError("trial plan cardinality invariant failed")
    trial_plan_sha256 = _canonical_json_sha256(trial_plan)
    if (
        args.include_manifest_anchor
        and trial_plan_sha256 != LOCKED_FULL_TRIAL_PLAN_SHA256
    ):
        raise HarnessError(
            f"full trial plan digest is {trial_plan_sha256}, "
            f"expected permanent {LOCKED_FULL_TRIAL_PLAN_SHA256}"
        )

    _reserve_output(output)
    report: dict[str, Any] = {
        "schema": "g4-identifier-scale-raw-v1",
        "kind": "g4-long-identifier-scale",
        "status": "running",
        "created_unix_ns": time.time_ns(),
        "created_local": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "timer": "time.perf_counter_ns",
        "collector_only_no_verdict": True,
        "collector_contract": {
            "exit_code_zero_meaning": (
                "the permanent schedule was attempted and raw JSON was checkpointed; "
                "no correctness, performance, RSS, or acceptance gate is implied"
            ),
            "separate_validator_required": True,
            "no_trial_discarding": True,
            "output_overwrite_forbidden": True,
            "formal_profile": bool(args.include_manifest_anchor),
            "nonstandard_reasons": (
                []
                if args.include_manifest_anchor
                else ["locked manifest 4KiB anchor explicitly disabled"]
            ),
        },
        "locked_values": {
            "accepted_control_sha": LOCKED_ACCEPTED_CONTROL_SHA,
            "official_sha": LOCKED_OFFICIAL_SHA,
            "official_registry_sha256": LOCKED_OFFICIAL_REGISTRY_SHA256,
            "image": LOCKED_IMAGE,
            "image_digest": LOCKED_IMAGE_DIGEST,
            "identifier_lengths": list(IDENTIFIER_LENGTHS),
            "protocols": list(PROTOCOLS),
            "repetitions_per_role": REPETITIONS_PER_ROLE,
            "timeout_seconds": TIMEOUT_SECONDS,
            "exit_timeout_seconds": EXIT_TIMEOUT_SECONDS,
            "rss_sample_ms": RSS_SAMPLE_MS,
            "fixed_source_template": "main(): Unit { let <identifier>: Int64 = 1 }",
            "identifier_template": "a + x*(length-1)",
            "manifest_anchor_default_included": True,
            "manifest_anchor_included_this_run": bool(args.include_manifest_anchor),
            "manifest_anchor_identifier_bytes": MANIFEST_ANCHOR_IDENTIFIER_BYTES,
            "manifest_anchor_token_count": MANIFEST_ANCHOR_TOKEN_COUNT,
            "full_trial_plan_sha256": LOCKED_FULL_TRIAL_PLAN_SHA256,
        },
        "provenance": {
            "collector_path": str(Path(__file__).resolve()),
            "collector_sha256": _sha256_file(Path(__file__).resolve()),
            "reused_g1_core_path": str((PROJECT_ROOT / G1_CORE_RELATIVE_PATH).resolve()),
            "reused_g1_core_sha256": G1_CORE_SHA256,
        },
        "arguments": {
            key: str(value) if isinstance(value, Path) else value
            for key, value in vars(args).items()
            if key != "handler"
        },
        "environment": {
            **environment,
            "cgroup_cpu_max": _read_optional_proc("/sys/fs/cgroup/cpu.max"),
            "cgroup_memory_max": _read_optional_proc("/sys/fs/cgroup/memory.max"),
        },
        "artifacts": artifacts,
        "manifests": {
            "control": control_manifest,
            "candidate": candidate_manifest,
            "anchor_sources_byte_identical": True,
        },
        "cases": [
            _case_record(case, *tokenized[case.name])
            for case in cases
        ],
        "trial_plan": trial_plan,
        "trial_plan_sha256": trial_plan_sha256,
        "trial_states": {
            entry["trial_id"]: {"status": "pending"} for entry in trial_plan
        },
        "runs": [],
        "trial_exceptions": [],
        "summaries": {},
    }
    _atomic_checkpoint(output, report)

    cases_by_name = {case.name: case for case in cases}
    interrupted = False
    for entry in trial_plan:
        trial_id = entry["trial_id"]
        state = report["trial_states"][trial_id]
        state.update({"status": "running", "started_unix_ns": time.time_ns()})
        _atomic_checkpoint(output, report)
        print(
            f"[{entry['ordinal']:03d}/{len(trial_plan)}] {trial_id}",
            flush=True,
        )
        case = cases_by_name[entry["case_name"]]
        token_ids, token_chunks = tokenized[case.name]
        try:
            run = G1_CORE._run_interactive(  # pylint: disable=protected-access
                role=entry["role"],
                solution=paths[f"{entry['role']}_solution"],
                cwd=paths[entry["role"]],
                protocol=entry["protocol"],
                token_ids=token_ids,
                token_byte_lengths=[len(chunk) for chunk in token_chunks],
                case_expected="accept",
                timeout_seconds=TIMEOUT_SECONDS,
                exit_timeout_seconds=EXIT_TIMEOUT_SECONDS,
                rss_sample_ms=RSS_SAMPLE_MS,
                request_phase_profile=False,
            )
            run.update(
                {
                    "run_index": len(report["runs"]),
                    "trial_id": trial_id,
                    "trial_ordinal": entry["ordinal"],
                    "role_repetition": entry["role_repetition"],
                    "case_name": case.name,
                    "case_source_sha256": case.source_sha256,
                    "identifier_bytes": case.identifier_bytes,
                    "sweep_length": case.sweep_length,
                    "event_timeline": None,
                    "timeline_contract": {
                        "event_timeline": "all token write/flush, paired response, deadline, cleanup, and process completion events",
                        "rss.samples": "all 5 ms /proc/PID/status samples plus explicit lifecycle snapshots",
                        "stdout_raw_b64": "complete exact stdout including cleanup bytes",
                        "stderr_raw_b64": "complete exact stderr including cleanup bytes",
                    },
                }
            )
            run["event_timeline"] = _event_timeline(run)
            run["case_ok"] = G1_CORE._scale_run_case_ok(  # pylint: disable=protected-access
                run, "accept"
            )
            report["runs"].append(run)
            state.update(
                {
                    "status": "completed",
                    "completed_unix_ns": time.time_ns(),
                    "run_index": run["run_index"],
                    "case_ok": run["case_ok"],
                    "timed_out": run["timed_out"],
                }
            )
        except KeyboardInterrupt as error:
            exception = {
                "trial_id": trial_id,
                "kind": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
                "unix_ns": time.time_ns(),
            }
            report["trial_exceptions"].append(exception)
            state.update({"status": "interrupted", "exception_index": len(report["trial_exceptions"]) - 1})
            report["status"] = "interrupted"
            _atomic_checkpoint(output, report)
            interrupted = True
            break
        except Exception as error:  # preserve the missing observation and continue the fixed plan
            exception = {
                "trial_id": trial_id,
                "kind": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
                "unix_ns": time.time_ns(),
            }
            report["trial_exceptions"].append(exception)
            state.update(
                {
                    "status": "exception",
                    "completed_unix_ns": time.time_ns(),
                    "exception_index": len(report["trial_exceptions"]) - 1,
                }
            )
        _atomic_checkpoint(output, report)

    if interrupted:
        print(f"raw checkpoint: {output}", flush=True)
        return 130

    state_counts: dict[str, int] = {}
    for state in report["trial_states"].values():
        state_counts[state["status"]] = state_counts.get(state["status"], 0) + 1
    report["summaries"] = {
        "collector_only_no_verdict": True,
        "planned_trial_count": len(trial_plan),
        "run_count": len(report["runs"]),
        "trial_exception_count": len(report["trial_exceptions"]),
        "trial_state_counts": state_counts,
        "case_ok_run_count": sum(run["case_ok"] for run in report["runs"]),
        "timed_out_run_count": sum(run["timed_out"] for run in report["runs"]),
        "groups": _group_summaries(report),
        "note": (
            "Mechanical views only. A separate validator must use every raw trial, "
            "including timeouts and exceptions, to evaluate predeclared G4 gates."
        ),
    }
    report["status"] = "complete"
    report["completed_unix_ns"] = time.time_ns()
    _atomic_checkpoint(output, report)
    print(f"raw JSON: {output}", flush=True)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Raw G4 long-identifier A/B collector: fixed 15-point sweep, dual protocol, "
            "three alternating fresh-process trials per role, plus the locked manifest anchor"
        ),
        epilog=(
            "Run only inside the locked Linux AArch64 image with separately built clean "
            "control/candidate clones. This collector never issues an acceptance verdict."
        ),
    )
    parser.add_argument("--control-root", type=Path, required=True)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--official-root", type=Path, required=True)
    parser.add_argument("--control-sha", required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--official-sha", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="new raw JSON path outside every audited root; an existing path is fatal",
    )
    parser.add_argument(
        "--include-manifest-anchor",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "include the separately named locked value_+4096*x manifest case "
            "(default and required for formal G4 collection)"
        ),
    )
    parser.set_defaults(handler=collect)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except HarnessError as error:
        print(f"HARNESS ERROR: {error}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
