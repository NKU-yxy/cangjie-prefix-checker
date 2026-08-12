#!/usr/bin/env python3
"""Run the fixed comprehensive corpus through the oracle and token protocol."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Sequence


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
    path: Path


@dataclass(frozen=True)
class ProtocolResult:
    answers: tuple[str, ...]
    returncode: int
    stderr: str
    reject_token: int | None
    reject_byte_end: int | None


def load_cases(manifest_path: Path) -> tuple[dict[str, object], list[LoadedCase]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise RuntimeError(f"unsupported manifest schema: {manifest.get('schema_version')}")
    root = manifest_path.parent
    cases: list[LoadedCase] = []
    for item in manifest["cases"]:
        path = root / item["file"]
        cases.append(
            LoadedCase(
                name=item["name"],
                family=item["family"],
                expected=item["expected"],
                complete=bool(item["complete"]),
                source=path.read_text(encoding="utf-8"),
                safe_prefix_bytes=item.get("safe_prefix_bytes"),
                oracle=bool(item.get("oracle", True)),
                path=path,
            )
        )
    if len(cases) != manifest.get("case_count"):
        raise RuntimeError(
            f"manifest case_count={manifest.get('case_count')} but loaded {len(cases)}"
        )
    return manifest, cases


def _run_protocol(
    solution: Path,
    token_ids: Sequence[int],
    token_chunks: Sequence[bytes],
    *,
    competition_output: bool,
    timeout: float,
) -> ProtocolResult:
    command = [str(solution)]
    if competition_output:
        command.append("--competition-output")
    proc = subprocess.run(
        command,
        cwd=ROOT,
        input="".join(f"{token_id}\n" for token_id in token_ids),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    answers = tuple(line.strip() for line in proc.stdout.splitlines())
    reject_value = "0" if competition_output else "1"
    reject_token = None
    reject_byte_end = None
    consumed = 0
    for index, chunk in enumerate(token_chunks):
        consumed += len(chunk)
        if index < len(answers) and answers[index] == reject_value:
            reject_token = index
            reject_byte_end = consumed
            break
    return ProtocolResult(
        answers=answers,
        returncode=proc.returncode,
        stderr=proc.stderr.strip(),
        reject_token=reject_token,
        reject_byte_end=reject_byte_end,
    )


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
    if result.returncode != 0:
        errors.append(f"{mode}: exit={result.returncode}, stderr={result.stderr!r}")
    if result.stderr:
        errors.append(f"{mode}: unexpected stderr={result.stderr!r}")
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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate the fixed comprehensive Cangjie prefix corpus."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--solution", type=Path, default=ROOT / "solution")
    parser.add_argument("--family", action="append", help="Only run this family (repeatable).")
    parser.add_argument("--name", help="Only run cases whose name contains this text.")
    parser.add_argument("--skip-oracle", action="store_true")
    parser.add_argument(
        "--check-competition-output",
        action="store_true",
        help="Also rerun every case with the inverted competition protocol.",
    )
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--list", action="store_true", help="List selected cases and exit.")
    parser.add_argument("--json", type=Path, help="Write a machine-readable result report.")
    args = parser.parse_args()

    manifest_path = args.manifest.resolve()
    manifest, cases = load_cases(manifest_path)
    if args.family:
        selected = set(args.family)
        cases = [case for case in cases if case.family in selected]
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
    if not solution.is_file():
        parser.error(f"solution does not exist: {solution}")

    try:
        import tiktoken
    except ImportError as error:
        parser.error(f"tiktoken is required: {error}")
    encoding = tiktoken.get_encoding("cl100k_base")

    failures: dict[str, list[str]] = {}
    oracle_checked = 0
    if not args.skip_oracle:
        oracle_checked = sum(case.complete and case.oracle for case in cases)
        for name, message in _oracle_errors(cases).items():
            failures.setdefault(name, []).append(message)

    modes = [False, True] if args.check_competition_output else [False]
    protocol_runs = 0
    for case in cases:
        token_ids = encoding.encode(case.source)
        token_chunks = [encoding.decode_single_token_bytes(token) for token in token_ids]
        for competition_output in modes:
            protocol_runs += 1
            result = _run_protocol(
                solution,
                token_ids,
                token_chunks,
                competition_output=competition_output,
                timeout=args.timeout,
            )
            errors = _protocol_errors(
                case,
                result,
                len(token_ids),
                competition_output=competition_output,
            )
            if errors:
                failures.setdefault(case.name, []).extend(errors)
                if args.fail_fast:
                    break
        if args.fail_fast and failures:
            break

    selected_counts: dict[str, int] = {}
    for case in cases:
        selected_counts[case.family] = selected_counts.get(case.family, 0) + 1
    summary = {
        "manifest": str(manifest_path),
        "manifest_case_count": manifest["case_count"],
        "selected_cases": len(cases),
        "families": dict(sorted(selected_counts.items())),
        "oracle_checked": oracle_checked,
        "protocol_modes": len(modes),
        "protocol_runs": protocol_runs,
        "passed_cases": len(cases) - len(failures),
        "failed_cases": len(failures),
    }
    report = {
        "summary": summary,
        "failures": [
            {"name": name, "messages": messages}
            for name, messages in sorted(failures.items())
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
