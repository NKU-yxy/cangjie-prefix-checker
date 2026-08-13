#!/usr/bin/env python3
"""Exercise the test-only old/new XGrammar shadow across fragment layouts."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import tiktoken


LOCAL_COUNTS = (0, 1, 2, 10, 25, 50, 100, 150, 200, 250, 300, 500)
IDENTIFIER_LENGTHS = (1, 2, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192)
LAYOUTS = ("byte", "random", "line", "cl100k", "whole")


@dataclass(frozen=True)
class Case:
    name: str
    source: str
    expected: str
    family: str


@dataclass(frozen=True)
class Run:
    answers: tuple[bool, ...]
    first_reject: int | None
    first_reject_byte_end: int | None
    exit_code: int
    stderr: str
    elapsed_ms: float


def _locals_source(count: int, separator: str, semicolon: bool) -> str:
    terminator = ";" if semicolon else ""
    statements = separator.join(
        f"let local{index}: Int64 = {index}{terminator}" for index in range(count)
    )
    if not statements:
        return "main(): Unit {}"
    if separator in {"\n", "\r\n"}:
        return f"main(): Unit {{{separator}{statements}{separator}}}"
    return f"main(): Unit {{ {statements} }}"


def _identifier_source(length: int, newline: bool, semicolon: bool) -> str:
    identifier = "a" + "x" * (length - 1)
    separator = "\n" if newline else " "
    terminator = ";" if semicolon else ""
    return (
        f"main(): Unit {{{separator}"
        f"let {identifier}: Int64 = 1{terminator}{separator}}}"
    )


def _feature_cases() -> list[Case]:
    valid = "accept"
    prefix = "prefix-accept"
    return [
        Case("whitespace-space", "main(): Unit { let x: Int64 = 1; }", valid, "whitespace"),
        Case("whitespace-tab", "main(): Unit {\tlet x: Int64 = 1;\t}", valid, "whitespace"),
        Case("whitespace-crlf", "main(): Unit {\r\nlet x: Int64 = 1\r\n}\r\n", valid, "whitespace"),
        Case("line-comment-pseudo", "main(): Unit { // let fake = }; ;\nlet x: Int64 = 1 }", valid, "comments"),
        Case("block-comment-pseudo", "main(): Unit { /* if { ; let */ let x: Int64 = 1 }", valid, "comments"),
        Case("nested-block-comment", "main(): Unit { /* outer /* inner ; } */ done */ }", valid, "comments"),
        Case("string-pseudo", 'main(): Unit { let text: String = "if { let x; }" }', valid, "strings"),
        Case("variable-declaration", "main(): Unit { var value: Int64 = 1; }", valid, "statements"),
        Case("assignment", "main(): Unit { var value: Int64 = 1; value = 2 }", valid, "statements"),
        Case("compound-assignment", "main(): Unit { var value: Int64 = 1; value += 2 }", valid, "statements"),
        Case("expression-statement", 'main(): Unit { println("ok") }', valid, "statements"),
        Case("call-member-index-postfix", "main(): Unit { let values: Array<Int64> = [1]; values[0].toString() }", valid, "postfix"),
        Case("nested-block", "main(): Unit { { let nested: Int64 = 1 } }", valid, "blocks"),
        Case("lambda-block", "main(): Unit { let f: (Int64) -> Int64 = { x: Int64 => { return x } } }", valid, "blocks"),
        Case("if-else", "main(): Unit { if true { println(1) } else { println(2) } }", valid, "control"),
        Case("for-loop", "main(): Unit { for (i in 0..3) { println(i) } }", valid, "control"),
        Case("while-loop", "main(): Unit { while true { break } }", valid, "control"),
        Case("do-while", "main(): Unit { do { println(1) } while true }", valid, "control"),
        Case("try-catch-finally", "main(): Unit { try {} catch (error: Error) {} finally {} }", valid, "control"),
        Case("match-case", "main(): Unit { match (1) { case 1 => println(1) } }", valid, "control"),
        Case("function-body", "func identity(value: Int64): Int64 { return value }", valid, "declarations"),
        Case("class-body", "class Box { value: Int64; func get(): Int64 { return value } }", valid, "declarations"),
        Case("incomplete-identifier", "main(): Unit { let value: Int64 = 1\nval", prefix, "incomplete"),
        Case("incomplete-statement", "main(): Unit { let value: Int64 =", prefix, "incomplete"),
        Case("incomplete-block", "main(): Unit { if true { let value: Int64 = 1", prefix, "incomplete"),
        Case("late-error", "main(): Unit {\n" + "\n".join(f"let value{i}: Int64 = {i}" for i in range(40)) + "\n@", "reject", "late-error"),
    ]


def build_cases() -> list[Case]:
    cases = _feature_cases()
    boundary_source = "main(): Unit {\nlet value: Int64 = 1;\nvalue += 2;\n}\n"
    boundary_bytes = boundary_source.encode("utf-8")
    for boundary in range(len(boundary_bytes) + 1):
        mutated = boundary_bytes[:boundary] + b"@" + boundary_bytes[boundary:]
        cases.append(Case(
            f"illegal-token-byte-boundary-{boundary}",
            mutated.decode("utf-8"),
            "reject",
            "illegal-boundary",
        ))

    local_variants = (
        ("semicolon-newline", "\n", True),
        ("no-semicolon-newline", "\n", False),
        ("semicolon-same-line", " ", True),
        ("no-semicolon-same-line", " ", False),
        ("semicolon-tab", "\t", True),
        ("no-semicolon-crlf", "\r\n", False),
    )
    for index, count in enumerate(LOCAL_COUNTS):
        label, separator, semicolon = local_variants[index % len(local_variants)]
        cases.append(Case(
            f"locals-{count}-{label}",
            _locals_source(count, separator, semicolon),
            "accept",
            "local-count",
        ))

    identifier_variants = (
        ("same-line", "no-semicolon", False, False),
        ("same-line", "semicolon", False, True),
        ("newline", "no-semicolon", True, False),
        ("newline", "semicolon", True, True),
    )
    for index, length in enumerate(IDENTIFIER_LENGTHS):
        placement, ending, newline, semicolon = identifier_variants[
            index % len(identifier_variants)
        ]
        cases.append(Case(
            f"identifier-{length}-{placement}-{ending}",
            _identifier_source(length, newline, semicolon),
            "accept",
            "identifier-length",
        ))

    return cases


def _random_chunks(data: bytes, case_name: str) -> list[bytes]:
    seed = int.from_bytes(hashlib.sha256(case_name.encode()).digest()[:8], "big")
    rng = random.Random(seed)
    result: list[bytes] = []
    cursor = 0
    while cursor < len(data):
        size = rng.randint(1, 17)
        result.append(data[cursor:cursor + size])
        cursor += size
    return result


def _line_chunks(data: bytes) -> list[bytes]:
    chunks = data.splitlines(keepends=True)
    consumed = sum(map(len, chunks))
    if consumed < len(data):
        chunks.append(data[consumed:])
    return chunks


def fragment(case: Case, layout: str, encoding: object) -> list[bytes]:
    data = case.source.encode("utf-8")
    if layout == "byte":
        return [data[index:index + 1] for index in range(len(data))]
    if layout == "random":
        return _random_chunks(data, case.name)
    if layout == "line":
        return _line_chunks(data)
    if layout == "cl100k":
        return [encoding.decode_single_token_bytes(token) for token in encoding.encode(case.source)]
    if layout == "whole":
        return [data] if data else []
    raise AssertionError(layout)


def _parse_answers(stdout: str, competition: bool) -> tuple[bool, ...]:
    raw = stdout.splitlines()
    if any(value not in {"0", "1"} for value in raw):
        raise RuntimeError(f"non-protocol stdout: {stdout!r}")
    if competition:
        return tuple(value == "1" for value in raw)
    return tuple(value == "0" for value in raw)


def run_case(
    solution: Path,
    chunks: Sequence[bytes],
    competition: bool,
    timeout: float,
) -> Run:
    command = [str(solution), "--grammar-shadow-fragments"]
    if competition:
        command.append("--competition-output")
    payload = "".join(chunk.hex() + "\n" for chunk in chunks)
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        input=payload,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    answers = _parse_answers(completed.stdout, competition)
    if len(answers) > len(chunks):
        raise RuntimeError("solution emitted more answers than fragments")
    first_reject = next((index for index, accepted in enumerate(answers) if not accepted), None)
    first_reject_byte_end = None
    if first_reject is not None:
        first_reject_byte_end = sum(len(chunk) for chunk in chunks[:first_reject + 1])
    return Run(
        answers=answers,
        first_reject=first_reject,
        first_reject_byte_end=first_reject_byte_end,
        exit_code=completed.returncode,
        stderr=completed.stderr,
        elapsed_ms=elapsed_ms,
    )


def transcript_hash(answers: Iterable[bool]) -> str:
    payload = bytes(1 if answer else 0 for answer in answers)
    return hashlib.sha256(payload).hexdigest()


def run_layout_checked(
    solution: Path,
    case: Case,
    layout: str,
    encoding: object,
    protocols: Sequence[bool],
    timeout: float,
) -> list[dict[str, object]]:
    chunks = fragment(case, layout, encoding)
    runs: dict[bool, Run] = {}
    observations: list[dict[str, object]] = []
    for competition in protocols:
        run = run_case(solution, chunks, competition, timeout)
        runs[competition] = run
        if run.exit_code != 0 or run.stderr:
            raise RuntimeError(f"exit={run.exit_code}, stderr={run.stderr!r}")
        if len(run.answers) != len(chunks) and run.first_reject is None:
            raise RuntimeError("missing answers")
        rejected = run.first_reject is not None
        if case.expected in {"accept", "prefix-accept"} and rejected:
            raise RuntimeError(
                f"expected accept, rejected at fragment {run.first_reject}"
            )
        if case.expected == "reject" and not rejected:
            raise RuntimeError("expected rejection")
        observations.append({
            "case": case.name,
            "family": case.family,
            "layout": layout,
            "protocol": "competition" if competition else "default",
            "source_bytes": len(case.source.encode("utf-8")),
            "fragments": len(chunks),
            "answers": len(run.answers),
            "first_reject": run.first_reject,
            "first_reject_byte_end": run.first_reject_byte_end,
            "transcript_sha256": transcript_hash(run.answers),
            "elapsed_ms": run.elapsed_ms,
        })
    if len(runs) == 2:
        default = runs[False]
        competition = runs[True]
        if (
            default.answers != competition.answers or
            default.first_reject != competition.first_reject or
            default.first_reject_byte_end != competition.first_reject_byte_end or
            default.exit_code != competition.exit_code or
            default.stderr != competition.stderr
        ):
            raise RuntimeError("protocol transcript mismatch")
    return observations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solution", type=Path, default=Path("./solution"))
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--protocol", choices=("default", "competition", "both"), default="default")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--max-local-count", type=int)
    parser.add_argument("--max-identifier-length", type=int)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()

    solution = args.solution.resolve()
    if not solution.is_file():
        parser.error(f"solution does not exist: {solution}")
    if args.jobs < 1:
        parser.error("--jobs must be positive")

    encoding = tiktoken.get_encoding("cl100k_base")
    cases = build_cases()
    if args.max_local_count is not None:
        cases = [
            case for case in cases
            if case.family != "local-count" or
            int(case.name.split("-", 2)[1]) <= args.max_local_count
        ]
    if args.max_identifier_length is not None:
        cases = [
            case for case in cases
            if case.family != "identifier-length" or
            int(case.name.split("-", 2)[1]) <= args.max_identifier_length
        ]
    protocols = (False, True) if args.protocol == "both" else (args.protocol == "competition",)
    observations: list[dict[str, object]] = []
    started = time.perf_counter()

    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        for case_index, case in enumerate(cases, 1):
            futures = {
                executor.submit(
                    run_layout_checked,
                    solution,
                    case,
                    layout,
                    encoding,
                    protocols,
                    args.timeout,
                ): layout
                for layout in LAYOUTS
            }
            for future in as_completed(futures):
                layout = futures[future]
                try:
                    observations.extend(future.result())
                except (RuntimeError, subprocess.TimeoutExpired) as error:
                    print(f"FAIL {case.name}/{layout}: {error}", file=sys.stderr)
                    return 1
            if (
                case.family in {"local-count", "identifier-length"} or
                case_index % 25 == 0 or
                case_index == len(cases)
            ):
                print(
                    f"grammar shadow matrix: {case_index}/{len(cases)} "
                    f"cases ({case.name})",
                    flush=True,
                )

    payload = {
        "schema": 1,
        "solution": str(solution),
        "case_count": len(cases),
        "layout_count": len(LAYOUTS),
        "protocols": ["competition" if value else "default" for value in protocols],
        "run_count": len(observations),
        "local_counts": list(LOCAL_COUNTS),
        "identifier_lengths": list(IDENTIFIER_LENGTHS),
        "layouts": list(LAYOUTS),
        "elapsed_seconds": time.perf_counter() - started,
        "observations": observations,
    }
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"PASS: {len(cases)} cases x {len(LAYOUTS)} layouts x "
        f"{len(protocols)} protocol(s) = {len(observations)} shadow runs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
