#!/usr/bin/env python3
"""Black-box correctness stress checks for startup and concurrency changes.

This is deliberately not a benchmark.  It records diagnostic timings so hangs
and extreme outliers are visible, but those numbers are not valid inputs to the
official A/B/A performance decision.

All resource-failure checks use explicit temporary context paths or a temporary
copy of a native executable.  Files beside the real solution are never moved,
renamed, overwritten, or corrupted.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path
import shutil
import statistics
import struct
import subprocess
import sys
import tempfile
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


ROOT = Path(__file__).resolve().parents[1]
TABLE_MAGIC = b"CJTK\x01\x00\x00\x00"
MISSING_OFFSET = 0xFFFFFFFF


class CheckFailure(RuntimeError):
    """A validation failed without mutating the solution under test."""


@dataclass(frozen=True)
class ProcessResult:
    elapsed_ms: float
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class FaultResult:
    name: str
    returncode: int
    elapsed_ms: float
    stderr: str


class ByteTokenEncoder:
    """Encode supported bytes as one-byte tokens using the runtime table.

    Canonical BPE segmentation is unnecessary for this correctness stress test:
    the protocol accepts token IDs, and concatenating valid one-byte token
    payloads reconstructs exactly the same source.  The generated runtime table
    intentionally uses isolated-token UTF-8 replacement semantics, so only its
    128 exact ASCII byte entries are guaranteed.  All built-in stress sources are
    therefore ASCII.  Byte fragmentation exercises incremental boundaries more
    aggressively and avoids downloading a tiktoken vocabulary.
    """

    def __init__(self, table_path: Path) -> None:
        data = table_path.read_bytes()
        if len(data) < 16 or data[:8] != TABLE_MAGIC:
            raise CheckFailure(f"invalid token table header: {table_path}")
        count, blob_size = struct.unpack_from("<II", data, 8)
        entries_end = 16 + count * 8
        if entries_end > len(data) or blob_size > len(data) - entries_end:
            raise CheckFailure(f"truncated token table: {table_path}")
        blob = data[entries_end : entries_end + blob_size]
        by_byte: Dict[int, int] = {}
        for token_id in range(count):
            offset, length = struct.unpack_from("<II", data, 16 + token_id * 8)
            if offset == MISSING_OFFSET or length != 1:
                continue
            if offset >= len(blob):
                raise CheckFailure(f"invalid token table entry {token_id}: {table_path}")
            by_byte.setdefault(blob[offset], token_id)
        missing_ascii = [value for value in range(128) if value not in by_byte]
        if missing_ascii:
            raise CheckFailure(
                f"token table lacks {len(missing_ascii)} ASCII byte tokens: {table_path}"
            )
        self._by_byte = by_byte

    def encode(self, source: str) -> List[int]:
        payload = source.encode("utf-8")
        missing = sorted({value for value in payload if value not in self._by_byte})
        if missing:
            raise CheckFailure(
                f"source contains bytes unavailable as exact table tokens: {missing[:8]}"
            )
        return [self._by_byte[value] for value in payload]


class Cl100kEncoder:
    """Use the same canonical cl100k segmentation as the official harness."""

    def __init__(self) -> None:
        try:
            import tiktoken
        except ImportError as error:
            raise CheckFailure(
                "tiktoken is required for canonical long-input stress"
            ) from error
        self._encoding = tiktoken.get_encoding("cl100k_base")

    def encode(self, source: str) -> List[int]:
        return self._encoding.encode(source)


def _protocol_input(token_ids: Sequence[int]) -> str:
    return "".join(f"{token_id}\n" for token_id in token_ids)


def _command(solution: Path, competition_output: bool) -> List[str]:
    command = [str(solution)]
    if competition_output:
        command.append("--competition-output")
    return command


def _run_process(
    command: Sequence[str],
    *,
    cwd: Path,
    stdin: str,
    timeout: float,
) -> ProcessResult:
    started = time.perf_counter_ns()
    try:
        proc = subprocess.run(
            list(command),
            cwd=str(cwd),
            input=stdin,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise CheckFailure(
            f"process timed out after {timeout:.3f}s: {command[0]}"
        ) from error
    except OSError as error:
        raise CheckFailure(f"cannot start {command[0]}: {error}") from error
    elapsed_ms = (time.perf_counter_ns() - started) / 1_000_000.0
    return ProcessResult(
        elapsed_ms=elapsed_ms,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def _verify_accept(
    result: ProcessResult,
    token_count: int,
    *,
    competition_output: bool,
    allow_stderr: bool,
    label: str,
) -> None:
    if result.returncode != 0:
        raise CheckFailure(
            f"{label}: exit={result.returncode}, stderr={result.stderr.strip()!r}"
        )
    if result.stderr and not allow_stderr:
        raise CheckFailure(f"{label}: unexpected stderr={result.stderr.strip()!r}")
    answers = result.stdout.splitlines()
    expected = "1" if competition_output else "0"
    if len(answers) != token_count:
        raise CheckFailure(
            f"{label}: received {len(answers)}/{token_count} protocol replies"
        )
    invalid = [answer for answer in answers if answer != expected]
    if invalid:
        raise CheckFailure(
            f"{label}: expected only {expected!r}, got {invalid[:3]!r}"
        )


def _run_accept(
    solution: Path,
    token_ids: Sequence[int],
    *,
    competition_output: bool,
    timeout: float,
    allow_stderr: bool,
    label: str,
) -> ProcessResult:
    result = _run_process(
        _command(solution, competition_output),
        cwd=solution.parent,
        stdin=_protocol_input(token_ids),
        timeout=timeout,
    )
    _verify_accept(
        result,
        len(token_ids),
        competition_output=competition_output,
        allow_stderr=allow_stderr,
        label=label,
    )
    return result


def _timing_summary(values: Sequence[float]) -> Dict[str, float]:
    ordered = sorted(values)
    if not ordered:
        return {}
    p95_index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return {
        "min_ms": ordered[0],
        "median_ms": statistics.median(ordered),
        "p95_ms": ordered[p95_index],
        "max_ms": ordered[-1],
    }


def run_cold_starts(
    solution: Path,
    token_ids: Sequence[int],
    *,
    count: int,
    competition_output: bool,
    timeout: float,
    allow_stderr: bool,
) -> Dict[str, object]:
    elapsed: List[float] = []
    for index in range(count):
        result = _run_accept(
            solution,
            token_ids,
            competition_output=competition_output,
            timeout=timeout,
            allow_stderr=allow_stderr,
            label=f"cold-start[{index}]",
        )
        elapsed.append(result.elapsed_ms)
    return {
        "runs": count,
        "token_count_per_run": len(token_ids),
        "diagnostic_only": True,
        **_timing_summary(elapsed),
    }


def make_long_valid_source(statement_count: int) -> str:
    body = "    println(1)\n" * statement_count
    return f"main(): Unit {{\n{body}}}\n"


def run_long_input(
    solution: Path,
    encoder: object,
    *,
    statement_count: int,
    competition_output: bool,
    timeout: float,
    allow_stderr: bool,
) -> Dict[str, object]:
    source = make_long_valid_source(statement_count)
    token_ids = encoder.encode(source)  # type: ignore[attr-defined]
    result = _run_accept(
        solution,
        token_ids,
        competition_output=competition_output,
        timeout=timeout,
        allow_stderr=allow_stderr,
        label="long-valid-input",
    )
    return {
        "statements": statement_count,
        "source_bytes": len(source.encode("utf-8")),
        "token_count": len(token_ids),
        "elapsed_ms": result.elapsed_ms,
        "diagnostic_only": True,
    }


def run_parallel_clients(
    solution: Path,
    token_ids: Sequence[int],
    *,
    clients: int,
    rounds: int,
    competition_output: bool,
    timeout: float,
    allow_stderr: bool,
) -> Dict[str, object]:
    total = clients * rounds
    elapsed: List[float] = []
    with ThreadPoolExecutor(max_workers=clients) as executor:
        futures = {
            executor.submit(
                _run_accept,
                solution,
                token_ids,
                competition_output=competition_output,
                timeout=timeout,
                allow_stderr=allow_stderr,
                label=f"parallel-client[{index}]",
            ): index
            for index in range(total)
        }
        for future in as_completed(futures):
            elapsed.append(future.result().elapsed_ms)
    return {
        "clients": clients,
        "rounds": rounds,
        "processes": total,
        "token_count_per_process": len(token_ids),
        "diagnostic_only": True,
        **_timing_summary(elapsed),
    }


def _expect_startup_failure(
    name: str,
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: float,
    stderr_markers: Iterable[str] = (),
) -> FaultResult:
    result = _run_process(command, cwd=cwd, stdin="", timeout=timeout)
    if result.returncode == 0:
        raise CheckFailure(f"resource fault {name}: unexpectedly exited 0")
    if result.stdout:
        raise CheckFailure(
            f"resource fault {name}: unexpected stdout={result.stdout.strip()!r}"
        )
    if not result.stderr.strip():
        raise CheckFailure(f"resource fault {name}: missing stderr diagnostic")
    markers = tuple(marker.lower() for marker in stderr_markers)
    if markers and not any(marker in result.stderr.lower() for marker in markers):
        raise CheckFailure(
            f"resource fault {name}: stderr lacks one of {markers!r}: "
            f"{result.stderr.strip()!r}"
        )
    return FaultResult(
        name=name,
        returncode=result.returncode,
        elapsed_ms=result.elapsed_ms,
        stderr=result.stderr.strip(),
    )


def _is_native_executable(path: Path) -> bool:
    try:
        magic = path.read_bytes()[:4]
    except OSError:
        return False
    return magic == b"\x7fELF" or magic in {
        b"\xfe\xed\xfa\xce",
        b"\xce\xfa\xed\xfe",
        b"\xfe\xed\xfa\xcf",
        b"\xcf\xfa\xed\xfe",
    }


def _stage_native_layout(
    stage: Path,
    solution: Path,
    resource_root: Path,
    *,
    token_mode: str,
    grammar_mode: str,
) -> Path:
    staged_solution = stage / "solution"
    shutil.copy2(str(solution), str(staged_solution))
    staged_solution.chmod(staged_solution.stat().st_mode | 0o111)

    generated = stage / "generated"
    grammar = stage / "grammar"
    generated.mkdir()
    grammar.mkdir()
    shutil.copy2(
        str(resource_root / "generated" / "context.bin"),
        str(generated / "context.bin"),
    )

    if token_mode == "valid":
        shutil.copy2(
            str(resource_root / "generated" / "cl100k_base.bin"),
            str(generated / "cl100k_base.bin"),
        )
    elif token_mode == "corrupt":
        (generated / "cl100k_base.bin").write_bytes(b"not-a-token-table")
    elif token_mode != "missing":
        raise AssertionError(token_mode)

    if grammar_mode == "valid":
        shutil.copy2(
            str(resource_root / "grammar" / "cangjie.gbnf"),
            str(grammar / "cangjie.gbnf"),
        )
    elif grammar_mode == "corrupt":
        (grammar / "cangjie.gbnf").write_bytes(b"\x00not-a-grammar")
    elif grammar_mode != "missing":
        raise AssertionError(grammar_mode)
    return staged_solution


def run_resource_faults(
    solution: Path,
    resource_root: Path,
    *,
    timeout: float,
) -> Dict[str, object]:
    results: List[FaultResult] = []
    with tempfile.TemporaryDirectory(prefix="cangjie-startup-fault-") as temp_name:
        temp = Path(temp_name)
        missing_context = temp / "missing-context.bin"
        results.append(
            _expect_startup_failure(
                "missing-context",
                [str(solution), "--context", str(missing_context)],
                cwd=solution.parent,
                timeout=timeout,
            )
        )
        corrupt_context = temp / "corrupt-context.bin"
        corrupt_context.write_bytes(b"not-a-context-table")
        results.append(
            _expect_startup_failure(
                "corrupt-context",
                [str(solution), "--context", str(corrupt_context)],
                cwd=solution.parent,
                timeout=timeout,
            )
        )

    native_layout_checked = _is_native_executable(solution)
    if native_layout_checked:
        required = (
            resource_root / "generated" / "context.bin",
            resource_root / "generated" / "cl100k_base.bin",
            resource_root / "grammar" / "cangjie.gbnf",
        )
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            raise CheckFailure(f"cannot stage native resource faults; missing: {missing}")
        native_cases: Tuple[Tuple[str, str, str, Tuple[str, ...]], ...] = (
            ("missing-token-table", "missing", "valid", ("token table", "cl100k")),
            ("corrupt-token-table", "corrupt", "valid", ("token table", "cl100k")),
            ("missing-grammar", "valid", "missing", ("grammar",)),
            ("corrupt-grammar", "valid", "corrupt", ()),
            (
                "token-table-priority",
                "missing",
                "missing",
                ("token table", "cl100k"),
            ),
        )
        for name, token_mode, grammar_mode, markers in native_cases:
            with tempfile.TemporaryDirectory(
                prefix=f"cangjie-{name}-"
            ) as stage_name:
                stage = Path(stage_name)
                staged_solution = _stage_native_layout(
                    stage,
                    solution,
                    resource_root,
                    token_mode=token_mode,
                    grammar_mode=grammar_mode,
                )
                results.append(
                    _expect_startup_failure(
                        name,
                        [str(staged_solution)],
                        cwd=stage,
                        timeout=timeout,
                        stderr_markers=markers,
                    )
                )
    return {
        "passed": len(results),
        "native_layout_checked": native_layout_checked,
        "cases": [asdict(result) for result in results],
    }


def detect_cpu_limit() -> Dict[str, object]:
    affinity_count: Optional[int] = None
    if hasattr(os, "sched_getaffinity"):
        try:
            affinity_count = len(os.sched_getaffinity(0))
        except OSError:
            affinity_count = None

    quota_cores: Optional[float] = None
    cpu_max = Path("/sys/fs/cgroup/cpu.max")
    try:
        parts = cpu_max.read_text(encoding="ascii").split()
        if len(parts) == 2 and parts[0] != "max":
            quota_cores = int(parts[0]) / int(parts[1])
    except (OSError, ValueError, ZeroDivisionError):
        quota_path = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
        period_path = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
        try:
            quota = int(quota_path.read_text(encoding="ascii"))
            period = int(period_path.read_text(encoding="ascii"))
            if quota > 0:
                quota_cores = quota / period
        except (OSError, ValueError, ZeroDivisionError):
            pass

    single_cpu = (
        (quota_cores is not None and quota_cores <= 1.05)
        or (quota_cores is None and affinity_count is not None and affinity_count <= 1)
    )
    return {
        "quota_cores": quota_cores,
        "affinity_cpu_count": affinity_count,
        "single_cpu_detected": single_cpu,
        "affinity_was_not_modified": True,
    }


def _positive_or_zero(parser: argparse.ArgumentParser, name: str, value: int) -> None:
    if value < 0:
        parser.error(f"{name} must be >= 0")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run non-destructive startup/concurrency correctness stress checks."
    )
    parser.add_argument("--solution", type=Path, default=ROOT / "solution")
    parser.add_argument(
        "--resource-root",
        type=Path,
        help="Root containing generated/ and grammar/ (default: solution directory).",
    )
    parser.add_argument(
        "--token-table",
        type=Path,
        help="cl100k table used only to construct test token IDs.",
    )
    parser.add_argument("--cold-starts", type=int, default=1000)
    parser.add_argument("--long-statements", type=int, default=256)
    parser.add_argument("--parallel-clients", type=int, default=0)
    parser.add_argument("--parallel-rounds", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--competition-output", action="store_true")
    parser.add_argument(
        "--byte-fragments",
        action="store_true",
        help=(
            "Use one-byte token fragments for the long-input check; the default "
            "uses official cl100k segmentation."
        ),
    )
    parser.add_argument(
        "--allow-stderr",
        action="store_true",
        help="Allow diagnostic/profile stderr during successful protocol runs.",
    )
    parser.add_argument("--skip-resource-faults", action="store_true")
    parser.add_argument(
        "--require-single-cpu",
        action="store_true",
        help="Fail unless a <=1 CPU cgroup quota (or equivalent) is detected.",
    )
    parser.add_argument("--json", type=Path, help="Optional machine-readable report path.")
    args = parser.parse_args(argv)

    _positive_or_zero(parser, "--cold-starts", args.cold_starts)
    _positive_or_zero(parser, "--long-statements", args.long_statements)
    _positive_or_zero(parser, "--parallel-clients", args.parallel_clients)
    _positive_or_zero(parser, "--parallel-rounds", args.parallel_rounds)
    if args.parallel_clients and args.parallel_rounds == 0:
        parser.error("--parallel-rounds must be > 0 when clients are enabled")
    if args.timeout <= 0:
        parser.error("--timeout must be > 0")

    solution = args.solution.resolve()
    if not solution.is_file() or not os.access(str(solution), os.X_OK):
        parser.error(f"solution is not an executable file: {solution}")
    resource_root = (
        args.resource_root.resolve() if args.resource_root else solution.parent
    )
    token_table = (
        args.token_table.resolve()
        if args.token_table
        else resource_root / "generated" / "cl100k_base.bin"
    )

    report: Dict[str, object] = {
        "schema_version": 1,
        "purpose": "correctness_stress_not_performance_benchmark",
        "solution": str(solution),
        "resource_root": str(resource_root),
        "token_table": str(token_table),
        "competition_output": args.competition_output,
        "cpu": detect_cpu_limit(),
        "status": "PASS",
    }
    try:
        if args.require_single_cpu and not report["cpu"]["single_cpu_detected"]:  # type: ignore[index]
            raise CheckFailure(
                "single CPU limit not detected; launch the official container with --cpus=1"
            )
        byte_encoder = ByteTokenEncoder(token_table)
        long_encoder = byte_encoder if args.byte_fragments else Cl100kEncoder()
        cold_token_ids = byte_encoder.encode(" ")
        if args.cold_starts:
            report["cold_start"] = run_cold_starts(
                solution,
                cold_token_ids,
                count=args.cold_starts,
                competition_output=args.competition_output,
                timeout=args.timeout,
                allow_stderr=args.allow_stderr,
            )
        if args.long_statements:
            report["long_input"] = run_long_input(
                solution,
                long_encoder,
                statement_count=args.long_statements,
                competition_output=args.competition_output,
                timeout=args.timeout,
                allow_stderr=args.allow_stderr,
            )
        if args.parallel_clients:
            report["parallel_stress"] = run_parallel_clients(
                solution,
                cold_token_ids,
                clients=args.parallel_clients,
                rounds=args.parallel_rounds,
                competition_output=args.competition_output,
                timeout=args.timeout,
                allow_stderr=args.allow_stderr,
            )
        if not args.skip_resource_faults:
            report["resource_faults"] = run_resource_faults(
                solution,
                resource_root,
                timeout=args.timeout,
            )
    except (CheckFailure, OSError, ValueError) as error:
        report["status"] = "FAIL"
        report["failure"] = str(error)

    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    print(rendered, end="")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(rendered, encoding="utf-8")
    if report["status"] != "PASS":
        print(f"[FAIL] {report['failure']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
