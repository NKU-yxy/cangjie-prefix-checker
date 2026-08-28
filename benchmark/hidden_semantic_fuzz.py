#!/usr/bin/env python3
"""Deterministic hidden-style semantic generation and differential testing.

The public examples are intentionally small and fixed.  This harness builds
fresh, compiler-checked programs that vary names, layout, literals, nesting,
and mutation sites.  Every complete program is labelled by the vendored
official typechecker before it is compared with both the Python prefix oracle
and the native C++ semantic engine.

The generated corpus concentrates on the highest-risk private-test shapes:

* multiline declarations and calls;
* nested lambdas and higher-order generic calls;
* overload selection and ambiguous member references;
* transitive generic interface inheritance; and
* valid programs, for which every observed prefix must remain accepted.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "third_party" / "cangjie_typechecker"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

from tools.native_build import native_driver_command


@dataclass(frozen=True)
class GeneratedCase:
    name: str
    family: str
    source: str
    expected_valid: bool
    mutation_start: int | None = None
    mutation_commit: int | None = None


@dataclass(frozen=True)
class RunResult:
    accepted: bool
    reject_fragment: int | None
    reject_byte_end: int | None
    stderr: str = ""


def _case(
    *,
    name: str,
    family: str,
    source: str,
    expected_valid: bool,
    mutation: str | None = None,
    commit: str | None = None,
) -> GeneratedCase:
    mutation_start = None
    mutation_commit = None
    if mutation is not None:
        mutation_start = source.index(mutation)
        commit_text = commit if commit is not None else mutation
        mutation_commit = source.index(commit_text, mutation_start) + len(commit_text)
    return GeneratedCase(
        name=name,
        family=family,
        source=source,
        expected_valid=expected_valid,
        mutation_start=mutation_start,
        mutation_commit=mutation_commit,
    )


def _multiline_cases(index: int, rng: random.Random) -> list[GeneratedCase]:
    suffix = f"{index}_{rng.randrange(1_000_000):06d}"
    function = f"combine_{suffix}"
    result = f"result_{suffix}"
    value_type = rng.choice(("Int64", "String", "Bool"))
    if value_type == "Int64":
        left = str(rng.randrange(1, 50))
        right = str(rng.randrange(51, 100))
        merge_expression = "a + b"
        wrong_expression = '"wrong"'
    elif value_type == "String":
        left = f'"left-{index}"'
        right = f'"right-{index}"'
        merge_expression = "a.concat(b)"
        wrong_expression = "314159"
    else:
        left = "true"
        right = "false"
        merge_expression = "a && b"
        wrong_expression = "314159"
    valid = f"""func {function}<T>(
    left: T,
    right: T,
    merge: (T, T) -> T
): T {{
    merge(left, right)
}}

main(): Unit {{
    let {result}: {value_type} =
        {function}<{value_type}>(
            {left},
            {right},
            {{ a: {value_type},
               b: {value_type} =>
               {merge_expression} }}
        )
}}
"""
    invalid = valid.replace(merge_expression, wrong_expression, 1)
    return [
        _case(name=f"multiline-valid-{suffix}", family="multiline", source=valid, expected_valid=True),
        _case(
            name=f"multiline-return-mutation-{suffix}",
            family="multiline",
            source=invalid,
            expected_valid=False,
            mutation=wrong_expression,
            commit=wrong_expression,
        ),
    ]


def _nested_lambda_cases(index: int, rng: random.Random) -> list[GeneratedCase]:
    suffix = f"{index}_{rng.randrange(1_000_000):06d}"
    apply_name = f"apply_{suffix}"
    start = rng.randrange(1, 20)
    delta = rng.randrange(1, 10)
    depth = rng.randint(2, 4)

    def nested_expression(level: int, variable: str, leaf: str) -> str:
        if level == 0:
            return leaf.replace("$value", variable)
        child = f"level_{level}_{suffix}"
        inner = nested_expression(level - 1, child, leaf)
        indentation = " " * (12 + (depth - level) * 4)
        return (
            f"{apply_name}<Int64>(\n"
            f"{indentation}{variable},\n"
            f"{indentation}{{ {child}: Int64 => {inner} }}\n"
            f"{' ' * max(8, len(indentation) - 4)})"
        )

    valid_nested = nested_expression(depth, "outer", f"$value + {delta}")
    invalid_nested = nested_expression(depth, "outer", '"nested-wrong"')
    valid = f"""func {apply_name}<T>(value: T, action: (T) -> T): T {{
    action(value)
}}

main(): Unit {{
    let answer_{suffix}: Int64 = {apply_name}<Int64>(
        {start},
        {{ outer: Int64 => {valid_nested} }}
    )
}}
"""
    invalid = valid.replace(valid_nested, invalid_nested, 1)
    return [
        _case(name=f"nested-lambda-valid-{suffix}", family="nested_lambda", source=valid, expected_valid=True),
        _case(
            name=f"nested-lambda-mutation-{suffix}",
            family="nested_lambda",
            source=invalid,
            expected_valid=False,
            mutation='"nested-wrong"',
            commit='"nested-wrong"',
        ),
    ]


def _overload_cases(index: int, rng: random.Random) -> list[GeneratedCase]:
    suffix = f"{index}_{rng.randrange(1_000_000):06d}"
    cap = rng.randrange(2, 30)
    member_reference = ""
    if index % 2:
        member_reference = f"""
    let clone_{suffix}: () -> ArrayList<Int64> = values_{suffix}.clone
    let copied_{suffix}: ArrayList<Int64> = clone_{suffix}()
"""
    valid = f"""main(): Unit {{
    let values_{suffix}: ArrayList<Int64> = ArrayList<Int64>({cap})
    values_{suffix}.add({rng.randrange(1, 100)})
    values_{suffix}.add(ArrayList<Int64>())
    values_{suffix}.add({rng.randrange(1, 100)}, 0)
{member_reference.rstrip()}
}}
"""
    # `add` has four overloads in context.json.  A bare member reference is
    # ambiguous even when the expected function type resembles one candidate.
    invalid = f"""main(): Unit {{
    let values_{suffix}: ArrayList<Int64> = ArrayList<Int64>({cap})
    let callback_{suffix}: (Int64) -> Unit = values_{suffix}.add
}}
"""
    return [
        _case(name=f"overload-valid-{suffix}", family="overload", source=valid, expected_valid=True),
        _case(
            name=f"overload-ambiguous-{suffix}",
            family="overload",
            source=invalid,
            expected_valid=False,
            mutation=f"values_{suffix}.add",
            commit=f"values_{suffix}.add",
        ),
    ]


def _generic_inheritance_cases(index: int, rng: random.Random) -> list[GeneratedCase]:
    suffix = f"{index}_{rng.randrange(1_000_000):06d}"
    source_i = f"Source_{suffix}"
    middle_i = f"Middle_{suffix}"
    box = f"Box_{suffix}"
    concrete_type = rng.choice(("Int64", "String", "Bool"))
    wrong_type_name = {"Int64": "String", "String": "Bool", "Bool": "Int64"}[concrete_type]
    literal = {
        "Int64": str(rng.randrange(1, 100)),
        "String": f'"value-{index}"',
        "Bool": "true" if index % 2 else "false",
    }[concrete_type]
    if index % 2:
        class_declaration = f"""class {box} <: {middle_i}<{concrete_type}> {{
    let value: {concrete_type}
    public init(initial: {concrete_type}) {{ value = initial }}
    public func get(): {concrete_type} {{ value }}
}}"""
        construction = f"{box}({literal})"
    else:
        class_declaration = f"""class {box}<C> <: {middle_i}<C> {{
    let value: C
    public init(initial: C) {{ value = initial }}
    public func get(): C {{ value }}
}}"""
        construction = f"{box}<{concrete_type}>({literal})"
    valid = f"""interface {source_i}<A> {{
    func get(): A
}}

interface {middle_i}<B> <: {source_i}<B> {{
    func get(): B
}}

{class_declaration}

main(): Unit {{
    let item_{suffix}: {source_i}<{concrete_type}> = {construction}
    let extracted_{suffix}: {concrete_type} = item_{suffix}.get()
}}
"""
    wrong_type = f"{source_i}<{wrong_type_name}>"
    invalid = valid.replace(f"{source_i}<{concrete_type}> =", f"{wrong_type} =", 1)
    return [
        _case(name=f"generic-inheritance-valid-{suffix}", family="generic_inheritance", source=valid, expected_valid=True),
        _case(
            name=f"generic-inheritance-mutation-{suffix}",
            family="generic_inheritance",
            source=invalid,
            expected_valid=False,
            mutation=wrong_type,
            commit=construction,
        ),
    ]


def _valid_mix_cases(index: int, rng: random.Random) -> list[GeneratedCase]:
    suffix = f"{index}_{rng.randrange(1_000_000):06d}"
    limit = rng.randrange(2, 8)
    valid_control = f"""func sum_{suffix}(limit: Int64): Int64 {{
    var total_{suffix}: Int64 = 0
    var current_{suffix}: Int64 = 0
    while (current_{suffix} < limit) {{
        total_{suffix} = total_{suffix} + current_{suffix}
        current_{suffix} = current_{suffix} + 1
    }}
    total_{suffix}
}}

main(): Unit {{
    let result_{suffix}: Int64 = sum_{suffix}({limit})
    println(result_{suffix})
}}
"""
    valid_comments = f"""interface Value_{suffix} {{
    func value(): Int64
}}

class Counter_{suffix} <: Value_{suffix} {{
    let stored: Int64
    public init(initial: Int64) {{
        // constructor assignment remains valid across a line comment
        stored = initial
    }}
    public func value(): Int64 {{
        stored
    }}
}}

main(): Unit {{
    let counter_{suffix}: Value_{suffix} = Counter_{suffix}({limit})
    let result_{suffix}: Int64 = counter_{suffix}.value()
}}
"""
    return [
        _case(name=f"valid-control-{suffix}", family="valid_zero_false_positive", source=valid_control, expected_valid=True),
        _case(name=f"valid-comment-nominal-{suffix}", family="valid_zero_false_positive", source=valid_comments, expected_valid=True),
    ]


def _scope_isolation_cases(index: int, rng: random.Random) -> list[GeneratedCase]:
    suffix = f"{index}_{rng.randrange(1_000_000):06d}"
    parameter = f"foreign_{suffix}"
    local = f"local_{suffix}"
    result = f"result_{suffix}"
    literal = rng.randrange(1, 100)
    header = f"""func identity_{suffix}({parameter}: Int64): Int64 {{
    {parameter}
}}

"""
    valid = header + f"""main(): Unit {{
    let {local}: Int64 = {literal}
    let {result}: Int64 = {local}
}}
"""
    invalid_line = f"let {result}: Int64 = {parameter}"
    invalid = header + f"""main(): Unit {{
    {invalid_line}
}}
"""
    return [
        _case(name=f"scope-isolation-valid-{suffix}", family="scope_isolation", source=valid, expected_valid=True),
        _case(
            name=f"scope-isolation-mutation-{suffix}",
            family="scope_isolation",
            source=invalid,
            expected_valid=False,
            mutation=invalid_line,
            commit=invalid_line,
        ),
    ]


_FAMILY_GENERATORS = (
    _multiline_cases,
    _nested_lambda_cases,
    _overload_cases,
    _generic_inheritance_cases,
    _valid_mix_cases,
    _scope_isolation_cases,
)


def generate_cases(seed: int, cases_per_family: int) -> list[GeneratedCase]:
    rng = random.Random(seed)
    cases: list[GeneratedCase] = []
    for index in range(cases_per_family):
        for generator in _FAMILY_GENERATORS:
            cases.extend(generator(index, rng))
    return cases


def _configure_official_oracle() -> None:
    from typechecker import builtin_context

    builtin_context._CONTEXT_PATH = ROOT / "context.json"
    if hasattr(builtin_context, "_raw_context"):
        builtin_context._raw_context.cache_clear()
    builtin_context._builtin_ctx_singleton = None


def official_accepts(source: str) -> tuple[bool, str]:
    from typechecker.checker import typecheck_tree
    from typechecker.errors import TypeCheckError
    from typechecker.parser import (
        UnexpectedCharacters,
        UnexpectedEOF,
        UnexpectedToken,
        parse,
    )

    try:
        typecheck_tree(parse(source))
        return True, ""
    except TypeCheckError as error:
        return False, str(error)
    except (UnexpectedCharacters, UnexpectedEOF, UnexpectedToken) as error:
        return False, f"syntax: {error}"


def _byte_chunks(payload: bytes) -> list[bytes]:
    return [bytes((value,)) for value in payload]


def _random_chunks(payload: bytes, seed: int) -> list[bytes]:
    rng = random.Random(seed)
    chunks: list[bytes] = []
    cursor = 0
    while cursor < len(payload):
        size = rng.randint(1, 17)
        chunks.append(payload[cursor : cursor + size])
        cursor += size
    return chunks


def _line_chunks(payload: bytes) -> list[bytes]:
    lines = payload.splitlines(keepends=True)
    return lines or [payload]


def _cl100k_chunks(source: str, encoding: object) -> list[bytes]:
    return [encoding.decode_single_token_bytes(token) for token in encoding.encode(source)]


def fragmentations(source: str, encoding: object, seed: int) -> dict[str, list[bytes]]:
    payload = source.encode("utf-8")
    return {
        "byte": _byte_chunks(payload),
        "random": _random_chunks(payload, seed),
        "line": _line_chunks(payload),
        "cl100k": _cl100k_chunks(source, encoding),
        "whole": [payload],
    }


def _first_reject(lines: Sequence[str], chunks: Sequence[bytes]) -> tuple[int | None, int | None]:
    consumed = 0
    for index, chunk in enumerate(chunks):
        consumed += len(chunk)
        if index >= len(lines):
            return index, consumed
        if lines[index].strip() == "1":
            return index, consumed
    return None, None


def run_native(driver: Path, context: Path, chunks: Sequence[bytes]) -> RunResult:
    proc = subprocess.run(
        [str(driver), str(context)],
        input="".join(chunk.hex() + "\n" for chunk in chunks),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    lines = proc.stdout.splitlines()
    reject_fragment, reject_byte_end = _first_reject(lines, chunks)
    protocol_ok = proc.returncode == 0 and (
        reject_fragment is not None or len(lines) == len(chunks)
    )
    return RunResult(
        accepted=protocol_ok and reject_fragment is None,
        reject_fragment=reject_fragment,
        reject_byte_end=reject_byte_end,
        stderr=proc.stderr.strip(),
    )


def run_solution(solution: Path, context: Path, token_ids: Sequence[int], chunks: Sequence[bytes]) -> RunResult:
    proc = subprocess.run(
        [str(solution), "--context", str(context)],
        input="".join(f"{token}\n" for token in token_ids),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    lines = proc.stdout.splitlines()
    reject_fragment, reject_byte_end = _first_reject(lines, chunks)
    protocol_ok = proc.returncode == 0 and (
        reject_fragment is not None or len(lines) == len(chunks)
    )
    return RunResult(
        accepted=protocol_ok and reject_fragment is None,
        reject_fragment=reject_fragment,
        reject_byte_end=reject_byte_end,
        stderr=proc.stderr.strip(),
    )


def run_python_prefix(source: str, chunks: Sequence[bytes], context: dict) -> RunResult:
    from src.prefix_semantic_checker import PrefixSemanticChecker

    checker = PrefixSemanticChecker(context)
    prefix = bytearray()
    consumed = 0
    for index, chunk in enumerate(chunks):
        prefix.extend(chunk)
        consumed += len(chunk)
        try:
            text = prefix.decode("utf-8")
        except UnicodeDecodeError:
            continue
        result = checker.validate(text)
        if not result.ok:
            return RunResult(False, index, consumed, result.message)
    return RunResult(True, None, None, "")


def _compile_driver(target: Path, sanitize: bool) -> None:
    flags = ["-std=c++17", "-O2", "-DNDEBUG"]
    if sanitize:
        flags = [
            "-std=c++17", "-O1", "-g", "-fno-omit-frame-pointer",
            "-fsanitize=address,undefined",
        ]
    subprocess.run(
        native_driver_command(target, compile_flags=flags),
        cwd=ROOT,
        check=True,
    )


def _mutation_window_error(case: GeneratedCase, result: RunResult) -> str | None:
    if case.expected_valid or result.reject_byte_end is None or case.mutation_start is None:
        return None
    # A chunk may cross the mutation boundary.  It must not be rejected while
    # every consumed byte still belongs to the unchanged valid base prefix.
    if result.reject_byte_end <= case.mutation_start:
        return f"premature rejection at byte {result.reject_byte_end}, mutation starts at {case.mutation_start}"
    return None


def _format_failure(case: GeneratedCase, messages: Iterable[str]) -> str:
    details = "\n".join(f"  - {message}" for message in messages)
    return f"[{case.family}] {case.name}\n{details}\n--- source ---\n{case.source}--- end ---"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument("--cases-per-family", type=int, default=12)
    parser.add_argument("--driver", type=Path)
    parser.add_argument("--solution", type=Path, help="Optional full protocol binary for cl100k checks.")
    parser.add_argument("--sanitize", action="store_true")
    parser.add_argument("--failure-json", type=Path)
    parser.add_argument("--max-failures", type=int, default=20)
    parser.add_argument(
        "--strict-prefix-differential",
        action="store_true",
        help="Treat disagreement with the legacy Python prefix checker as a failure.",
    )
    parser.add_argument("--show-prefix-disagreements", action="store_true")
    args = parser.parse_args()

    import tiktoken
    from src.context_loader import load_context

    _configure_official_oracle()
    encoding = tiktoken.get_encoding("cl100k_base")
    context = load_context(str(ROOT / "context.json"))
    context_bin = ROOT / "generated" / "context.bin"
    if not context_bin.is_file():
        subprocess.run(
            [sys.executable, "tools/generate_context_table.py", "context.json", str(context_bin)],
            cwd=ROOT,
            check=True,
        )

    cases = generate_cases(args.seed, args.cases_per_family)
    failures: list[dict[str, object]] = []
    prefix_disagreements: list[dict[str, object]] = []
    counts: dict[str, int] = {}
    with tempfile.TemporaryDirectory(prefix="cangjie-hidden-fuzz-") as temp_name:
        driver = args.driver.resolve() if args.driver else Path(temp_name) / "native_semantic_driver"
        if not args.driver:
            _compile_driver(driver, args.sanitize)
        solution = args.solution.resolve() if args.solution else None

        for case_index, case in enumerate(cases):
            counts[case.family] = counts.get(case.family, 0) + 1
            messages: list[str] = []
            official, official_message = official_accepts(case.source)
            if official != case.expected_valid:
                messages.append(
                    f"generator/oracle disagreement: expected={case.expected_valid}, "
                    f"official={official}: {official_message}"
                )
            layouts = fragmentations(case.source, encoding, args.seed + case_index)
            native_results: dict[str, RunResult] = {}
            python_results: dict[str, RunResult] = {}
            for layout, chunks in layouts.items():
                native = run_native(driver, context_bin, chunks)
                python = run_python_prefix(case.source, chunks, context)
                native_results[layout] = native
                python_results[layout] = python
                if native.accepted != case.expected_valid:
                    messages.append(
                        f"native/{layout}: expected valid={case.expected_valid}, "
                        f"accepted={native.accepted}, reject_byte_end={native.reject_byte_end}, "
                        f"stderr={native.stderr!r}"
                    )
                window_error = _mutation_window_error(case, native)
                if window_error:
                    messages.append(f"native/{layout}: {window_error}")
                if native.accepted != python.accepted:
                    disagreement = (
                        f"native/python {layout} disagreement: native={native.accepted} "
                        f"at {native.reject_byte_end}, python={python.accepted} "
                        f"at {python.reject_byte_end} ({python.stderr})"
                    )
                    prefix_disagreements.append({
                        "name": case.name,
                        "family": case.family,
                        "layout": layout,
                        "message": disagreement,
                    })
                    if args.strict_prefix_differential:
                        messages.append(disagreement)

            # Semantic results must not depend on how the exact same bytes are
            # split.  Rejection byte offsets may differ at chunk boundaries;
            # final acceptance may not.
            if len({result.accepted for result in native_results.values()}) != 1:
                messages.append(f"native fragmentation mismatch: {native_results}")

            if solution is not None:
                token_ids = encoding.encode(case.source)
                protocol = run_solution(solution, context_bin, token_ids, layouts["cl100k"])
                native_cl100k = native_results["cl100k"]
                if protocol.accepted != case.expected_valid:
                    messages.append(
                        f"solution/cl100k: expected valid={case.expected_valid}, "
                        f"accepted={protocol.accepted}, reject_byte_end={protocol.reject_byte_end}, "
                        f"stderr={protocol.stderr!r}"
                    )
                if protocol.accepted != native_cl100k.accepted:
                    messages.append(
                        f"solution/native disagreement: solution={protocol.accepted}, "
                        f"native={native_cl100k.accepted}"
                    )

            if messages:
                failures.append({
                    "name": case.name,
                    "family": case.family,
                    "expected_valid": case.expected_valid,
                    "messages": messages,
                    "source": case.source,
                })
                if len(failures) <= args.max_failures:
                    print(_format_failure(case, messages), file=sys.stderr)

    summary = {
        "seed": args.seed,
        "cases_per_family": args.cases_per_family,
        "generated_cases": len(cases),
        "families": counts,
        "fragmentations": ["byte", "random", "line", "cl100k", "whole"],
        "official_labels_checked": len(cases),
        "solution_checked": args.solution is not None,
        "legacy_prefix_disagreements": len(prefix_disagreements),
        "failures": len(failures),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if args.show_prefix_disagreements and prefix_disagreements:
        print("legacy prefix disagreements:", file=sys.stderr)
        for item in prefix_disagreements[: args.max_failures]:
            print(f"  {item['name']}: {item['message']}", file=sys.stderr)
    if args.failure_json:
        args.failure_json.parent.mkdir(parents=True, exist_ok=True)
        args.failure_json.write_text(
            json.dumps(
                {
                    "summary": summary,
                    "failures": failures,
                    "legacy_prefix_disagreements": prefix_disagreements,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
