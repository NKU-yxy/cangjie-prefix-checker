#!/usr/bin/env python3
"""Generate the deterministic, human-readable comprehensive test corpus.

The corpus deliberately mixes complete valid programs, committed errors, and
incomplete-but-still-completable prefixes.  The latter are important for this
project: accepting an unfinished prefix is correct behavior, not a false
negative.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "test_cases" / "comprehensive"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@dataclass(frozen=True)
class CorpusCase:
    name: str
    family: str
    expected: str
    complete: bool
    source: str
    safe_prefix_bytes: int | None = None
    oracle: bool = True


def _case(
    name: str,
    family: str,
    source: str,
    expected: str,
    *,
    marker: str | None = None,
    complete: bool = True,
    oracle: bool = True,
) -> CorpusCase:
    if expected not in {"accept", "reject"}:
        raise ValueError(f"invalid expectation for {name}: {expected}")
    safe_prefix_bytes = None
    if marker is not None:
        safe_prefix_bytes = len(source[: source.index(marker)].encode("utf-8"))
    return CorpusCase(
        name=name,
        family=family,
        expected=expected,
        complete=complete,
        source=source,
        safe_prefix_bytes=safe_prefix_bytes,
        oracle=oracle,
    )


def _manual_cases() -> list[CorpusCase]:
    cases: list[CorpusCase] = []

    def accept(
        name: str,
        family: str,
        source: str,
        *,
        oracle: bool = True,
    ) -> None:
        cases.append(_case(name, family, source, "accept", oracle=oracle))

    def reject(
        name: str,
        family: str,
        source: str,
        marker: str,
        *,
        oracle: bool = True,
    ) -> None:
        cases.append(
            _case(name, family, source, "reject", marker=marker, oracle=oracle)
        )

    def prefix(name: str, family: str, source: str) -> None:
        cases.append(
            _case(
                name,
                family,
                source,
                "accept",
                complete=False,
                oracle=False,
            )
        )

    # Lexing and token-boundary stress, including UTF-8 and nested comments.
    accept(
        "nested-comments-and-utf8",
        "lexical",
        '/* 外层 /* nested */ done */\nmain(): Unit { // 行注释\n println("编译🚀")\n}\n',
        oracle=False,
    )
    accept(
        "escaped-and-multiline-strings",
        "lexical",
        'main(): Unit {\n let escaped: String = "line\\nquote: \\\""\n let block: String = """first\nsecond"""\n println(escaped.concat(block))\n}\n',
    )
    accept(
        "raw-identifier",
        "lexical",
        "main(): Unit { let `class`: Int64 = 7\n println(`class`) }\n",
        oracle=False,
    )
    accept(
        "integer-bases-and-suffixes",
        "lexical",
        "main(): Unit { let a: Int64 = 0x2A\n let b: Int64 = 0o52\n let c: Int64 = 0b101010\n let d: Int32 = 42i32 }\n",
        oracle=False,
    )
    accept(
        "float-literals",
        "lexical",
        "main(): Unit { let a: Float64 = 1.25\n let b: Float64 = 2000.0\n let c: Float64 = 3.5 }\n",
    )
    reject(
        "invalid-string-escape",
        "lexical",
        'main(): Unit { let value: String = "bad\\q"\n println(value) }\n',
        "\\q",
        oracle=False,
    )
    reject(
        "invalid-hex-digit",
        "lexical",
        "main(): Unit { let value: Int64 = 0b102 + @1\n println(value) }\n",
        "2 + @",
    )

    # Primitive types, operators, assignment, and mutability.
    accept(
        "numeric-and-logical-operators",
        "types_operators",
        "main(): Unit { let n: Int64 = (2 + 3) * 4 - 5\n let ok: Bool = n >= 10 && n != 99\n if (ok) { println(n) } }\n",
    )
    accept(
        "mutable-compound-assignment",
        "types_operators",
        "main(): Unit { var total: Int64 = 1\n total += 2\n total *= 3\n println(total) }\n",
        oracle=False,
    )
    accept(
        "string-concatenation-method",
        "types_operators",
        'main(): Unit { let left: String = "a"\n let right: String = left.concat("b")\n println(right) }\n',
    )
    reject(
        "typed-integer-suffix-mismatch",
        "types_operators",
        "main(): Unit { let value: Int32 = 1i64\n println(0) }\n",
        "1i64",
    )
    reject(
        "boolean-arithmetic",
        "types_operators",
        "main(): Unit { let value: Int64 = true + 1\n println(value) }\n",
        "true + 1",
    )
    reject(
        "logical-operator-on-integer",
        "types_operators",
        "main(): Unit { let value: Bool = 1 && true\n println(0) }\n",
        "1 && true",
    )
    reject(
        "assign-to-let",
        "types_operators",
        "main(): Unit { let value: Int64 = 1\n value = 2\n println(value) }\n",
        "value = 2",
        oracle=False,
    )
    reject(
        "assignment-type-mismatch",
        "types_operators",
        'main(): Unit { var value: Int64 = 1\n value = "bad"\n println(value) }\n',
        '"bad"',
    )

    # Name resolution and scope lifetime.
    accept(
        "nested-scope-shadowing",
        "scope",
        "main(): Unit { let value: Int64 = 1\n { let value: String = \"inner\"\n println(value) }\n println(value) }\n",
    )
    accept(
        "lambda-captures-outer-local",
        "scope",
        "main(): Unit { let base: Int64 = 10\n let add: (Int64) -> Int64 = { x: Int64 => x + base }\n println(add(2)) }\n",
    )
    reject(
        "undefined-identifier",
        "scope",
        "main(): Unit { let value: Int64 = missing + 1\n println(value) }\n",
        "missing",
    )
    reject(
        "lambda-parameter-escapes",
        "scope",
        "main(): Unit { let identity: (Int64) -> Int64 = { inside: Int64 => inside }\n println(inside) }\n",
        "inside)",
    )
    reject(
        "function-parameter-leaks",
        "scope",
        "func identity(foreign: Int64): Int64 { foreign }\nmain(): Unit { let value: Int64 = foreign\n println(value) }\n",
        "foreign\n",
    )
    reject(
        "use-before-declaration",
        "scope",
        "main(): Unit { let first: Int64 = later\n let later: Int64 = 1\n println(first) }\n",
        "later\n",
    )

    # Control-flow context and condition types.
    accept(
        "if-else-bool-condition",
        "control_flow",
        "func choose(flag: Bool): Int64 { if (flag) { 1 } else { 2 } }\nmain(): Unit { println(choose(true)) }\n",
    )
    accept(
        "while-break-continue",
        "control_flow",
        "main(): Unit { var i: Int64 = 0\n while (i < 10) { i = i + 1\n if (i == 3) { continue }\n if (i == 8) { break } } }\n",
    )
    accept(
        "for-array-and-range",
        "control_flow",
        "main(): Unit { let xs: Array<Int64> = [1, 2, 3]\n for (x in xs) { println(x) }\n for (i in 0..=2) { println(i) } }\n",
    )
    reject(
        "if-condition-not-bool",
        "control_flow",
        "main(): Unit { if (1) { println(1) }\n println(2) }\n",
        "1)",
    )
    reject(
        "while-condition-not-bool",
        "control_flow",
        'main(): Unit { while ("yes") { break }\n println(0) }\n',
        '"yes")',
    )
    reject(
        "for-source-not-iterable",
        "control_flow",
        "main(): Unit { for (x in 42) { println(x) }\n println(0) }\n",
        "42)",
    )
    reject(
        "break-outside-loop",
        "control_flow",
        "main(): Unit { break\n println(0) }\n",
        "break",
    )
    reject(
        "continue-outside-loop",
        "control_flow",
        "main(): Unit { continue\n println(0) }\n",
        "continue",
    )
    reject(
        "return-value-type-mismatch",
        "control_flow",
        'func bad(): Int64 { return "wrong"\n }\nmain(): Unit { println(0) }\n',
        '"wrong"',
    )

    # Functions, calls, defaults, named arguments, and callable values.
    accept(
        "recursive-function",
        "functions",
        "func fact(n: Int64): Int64 { if (n <= 1) { 1 } else { n * fact(n - 1) } }\nmain(): Unit { println(fact(5)) }\n",
    )
    accept(
        "default-parameter",
        "functions",
        "func add(a: Int64, b: Int64 = 2): Int64 { a + b }\nmain(): Unit { println(add(3)) }\n",
        oracle=False,
    )
    accept(
        "named-arguments",
        "functions",
        "func subtract(a: Int64, b: Int64): Int64 { a - b }\nmain(): Unit { println(subtract(b: 2, a: 7)) }\n",
    )
    accept(
        "function-value-call",
        "functions",
        "func twice(value: Int64, op: (Int64) -> Int64): Int64 { op(op(value)) }\nmain(): Unit { let inc: (Int64) -> Int64 = { x: Int64 => x + 1 }\n println(twice(3, inc)) }\n",
    )
    reject(
        "function-argument-count",
        "functions",
        "func add(a: Int64, b: Int64): Int64 { a + b }\nmain(): Unit { let value: Int64 = add(1)\n println(value) }\n",
        "add(1)",
    )
    reject(
        "function-argument-type",
        "functions",
        'func square(x: Int64): Int64 { x * x }\nmain(): Unit { let value: Int64 = square("bad")\n println(value) }\n',
        '"bad"',
    )
    reject(
        "unknown-named-argument",
        "functions",
        "func add(a: Int64, b: Int64): Int64 { a + b }\nmain(): Unit { let value: Int64 = add(a: 1, missing: 2)\n println(value) }\n",
        "missing:",
    )
    reject(
        "function-result-type-mismatch",
        "functions",
        'func bad(): Int64 { "wrong" }\nmain(): Unit { println(0) }\n',
        '"wrong"',
    )

    # Arrays and standard context objects.
    accept(
        "array-literal-index-and-size",
        "collections",
        "main(): Unit { let xs: Array<Int64> = [10, 20, 30]\n let first: Int64 = xs[0]\n println(xs.size)\n println(first) }\n",
    )
    accept(
        "array-methods",
        "collections",
        "main(): Unit { let xs: Array<Int64> = Array<Int64>(3, 7)\n xs.swap(0, 2)\n xs.fill(9)\n let ys: Array<Int64> = xs.clone()\n println(ys.size) }\n",
    )
    accept(
        "array-list-overloads",
        "collections",
        "main(): Unit { let xs: ArrayList<Int64> = ArrayList<Int64>()\n xs.add(1)\n xs.add(2, 0)\n let ys: Array<Int64> = xs.toArray()\n println(ys.size) }\n",
    )
    accept(
        "hash-map-methods",
        "collections",
        'main(): Unit { let map: HashMap<String, Int64> = HashMap<String, Int64>()\n map.add("one", 1)\n let value: Int64 = map.get("one").getOrThrow()\n println(value) }\n',
    )
    accept(
        "hash-set-iteration",
        "collections",
        "main(): Unit { let set: HashSet<Int64> = HashSet<Int64>()\n set.add(1)\n for (value in set) { println(value) } }\n",
    )
    reject(
        "array-mixed-element-types",
        "collections",
        'main(): Unit { let xs: Array<Int64> = [1, "bad", 3]\n println(xs.size) }\n',
        '"bad"',
    )
    reject(
        "array-index-not-integer",
        "collections",
        'main(): Unit { let xs: Array<Int64> = [1]\n let value: Int64 = xs["zero"]\n println(value) }\n',
        '"zero"',
    )
    reject(
        "array-method-argument-type",
        "collections",
        'main(): Unit { let xs: Array<Int64> = [1]\n xs.fill("bad")\n println(xs.size) }\n',
        '"bad"',
    )
    reject(
        "missing-member",
        "collections",
        "main(): Unit { let xs: Array<Int64> = [1]\n let value: Int64 = xs.unknown()\n println(value) }\n",
        "unknown",
    )
    reject(
        "generic-constructor-type-mismatch",
        "collections",
        'main(): Unit { let xs: ArrayList<Int64> = ArrayList<Int64>("large")\n println(xs.size) }\n',
        '"large"',
    )

    # Nominal types, constructors, methods, and interface conformance.
    accept(
        "class-constructor-field-method",
        "classes_interfaces",
        "class Box { let value: Int64\n public init(initial: Int64) { value = initial }\n public func get(): Int64 { value } }\nmain(): Unit { let box: Box = Box(7)\n println(box.get()) }\n",
    )
    accept(
        "interface-implementation",
        "classes_interfaces",
        "interface Named { func name(): String }\nclass User <: Named { public init() {}\n public func name(): String { \"Ada\" } }\nmain(): Unit { let item: Named = User()\n println(item.name()) }\n",
    )
    accept(
        "generic-interface-implementation",
        "classes_interfaces",
        "interface Source<T> { func get(): T }\nclass Holder<T> <: Source<T> { let value: T\n public init(v: T) { value = v }\n public func get(): T { value } }\nmain(): Unit { let source: Source<Int64> = Holder<Int64>(9)\n println(source.get()) }\n",
    )
    accept(
        "overloaded-constructors",
        "classes_interfaces",
        "class Point { let x: Int64\n public init() { x = 0 }\n public init(value: Int64) { x = value } }\nmain(): Unit { let a: Point = Point()\n let b: Point = Point(3) }\n",
    )
    reject(
        "constructor-argument-type",
        "classes_interfaces",
        'class Box { public init(value: Int64) {} }\nmain(): Unit { let box: Box = Box("bad")\n println(0) }\n',
        '"bad"',
    )
    reject(
        "unknown-this-field",
        "classes_interfaces",
        "class Box { var value: Int64\n public init() { this.missing = 1 } }\nmain(): Unit { println(0) }\n",
        "missing",
    )
    reject(
        "constructor-return-value",
        "classes_interfaces",
        "class Box { public init() { return 1 } }\nmain(): Unit { println(0) }\n",
        "1 }",
    )
    reject(
        "interface-type-argument-mismatch",
        "classes_interfaces",
        "interface Source<T> { func get(): T }\nclass Holder<T> <: Source<T> { let value: T\n public init(v: T) { value = v }\n public func get(): T { value } }\nmain(): Unit { let source: Source<String> = Holder<Int64>(9)\n println(0) }\n",
        "Source<String>",
    )
    reject(
        "method-return-type-mismatch",
        "classes_interfaces",
        'class Box { public init() {}\n public func get(): Int64 { "bad" } }\nmain(): Unit { println(0) }\n',
        '"bad"',
    )

    # Pure syntax errors.  Each has a valid/completable prefix before marker.
    reject("missing-variable-name", "syntax", "main(): Unit { let value + other = 1\n println(0) }\n", "+")
    reject("extra-right-paren", "syntax", "main(): Unit { let x: Int64 = 1)\n println(x) }\n", ")")
    reject("extra-right-bracket", "syntax", "main(): Unit { let x: Int64 = 1]\n println(x) }\n", "]")
    reject("malformed-generic-close", "syntax", "class Box<T> { public init(value: T) {} }\nmain(): Unit { let box = Box<Int64,>(1) + 0\n println(0) }\n", ",>")
    reject("function-parameter-missing-colon", "syntax", "func bad(value Int64): Int64 { value }\nmain(): Unit { println(0) }\n", "Int64")
    reject("lambda-missing-arrow", "syntax", "main(): Unit { let f: (Int64) -> Int64 = { x: Int64 x + 1 }\n println(0) }\n", "x + 1")
    reject("double-else", "syntax", "main(): Unit { if (true) {} else {} else @ { println(0) } }\n", "else @")
    reject("dangling-binary-operator", "syntax", "main(): Unit { let x: Int64 = 1 + )\n println(x) }\n", ")")
    reject("invalid-at-character", "syntax", "main(): Unit { let x: Int64 = @1\n println(x) }\n", "@")
    reject("comma-after-last-function-argument", "syntax", "func id(x: Int64): Int64 { x }\nmain(): Unit { println(id(1,)) }\n", ",)")

    # Incomplete prefixes must remain accepted because more input can repair them.
    prefix("empty-input", "incomplete_prefix", "")
    prefix("function-keyword-prefix", "incomplete_prefix", "func")
    prefix("open-function-block", "incomplete_prefix", "main(): Unit {")
    prefix("partial-variable-type", "incomplete_prefix", "main(): Unit { let value:")
    prefix("partial-identifier", "incomplete_prefix", "main(): Unit { let longIdentifier: Int64 = 1\n longIdent")
    prefix("open-string", "incomplete_prefix", 'main(): Unit { let text: String = "hello')
    prefix("open-nested-comment", "incomplete_prefix", "/* outer /* inner */ still open")
    prefix("partial-exponent", "incomplete_prefix", "main(): Unit { let value: Float64 = 1e")
    prefix("partial-generic", "incomplete_prefix", "main(): Unit { let values: Array<")
    prefix("partial-lambda-body", "incomplete_prefix", "main(): Unit { let f: (Int64) -> Int64 = { x: Int64 => x +")

    return cases


def build_cases() -> list[CorpusCase]:
    """Return the complete deterministic corpus before materialization."""
    from benchmark.hidden_semantic_fuzz import generate_cases

    cases = _manual_cases()
    for hidden in generate_cases(seed=20260805, cases_per_family=3):
        safe_prefix_bytes = None
        if hidden.mutation_start is not None:
            safe_prefix_bytes = len(hidden.source[: hidden.mutation_start].encode("utf-8"))
        cases.append(
            CorpusCase(
                name=f"generated-{hidden.name}",
                family=f"generated_{hidden.family}",
                expected="accept" if hidden.expected_valid else "reject",
                complete=True,
                source=hidden.source,
                safe_prefix_bytes=safe_prefix_bytes,
                oracle=True,
            )
        )

    names = [case.name for case in cases]
    if len(names) != len(set(names)):
        raise RuntimeError("duplicate corpus case names")
    return sorted(cases, key=lambda case: (case.family, case.expected, case.name))


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _serialized(cases: list[CorpusCase]) -> tuple[dict[str, str], str]:
    files: dict[str, str] = {}
    manifest_cases: list[dict[str, object]] = []
    for case in cases:
        group = "prefix" if not case.complete else ("valid" if case.expected == "accept" else "invalid")
        relative = Path(group) / f"{_slug(case.family)}__{_slug(case.name)}.cj"
        files[relative.as_posix()] = case.source
        metadata = asdict(case)
        metadata.pop("source")
        metadata["file"] = relative.as_posix()
        manifest_cases.append(metadata)

    family_counts: dict[str, int] = {}
    expectation_counts: dict[str, int] = {}
    for case in cases:
        family_counts[case.family] = family_counts.get(case.family, 0) + 1
        label = "prefix_accept" if not case.complete else case.expected
        expectation_counts[label] = expectation_counts.get(label, 0) + 1
    manifest = {
        "schema_version": 1,
        "description": "仓颉流式前缀检查器固定综合回归语料",
        "generator": "tools/generate_comprehensive_cases.py",
        "case_count": len(cases),
        "family_counts": dict(sorted(family_counts.items())),
        "expectation_counts": dict(sorted(expectation_counts.items())),
        "cases": manifest_cases,
    }
    return files, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"


def _check_file(path: Path, expected: str) -> str | None:
    if not path.is_file():
        return f"missing: {path.relative_to(ROOT)}"
    actual = path.read_text(encoding="utf-8")
    if actual != expected:
        return f"out of date: {path.relative_to(ROOT)}"
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; fail if checked-in corpus differs from the generator.",
    )
    args = parser.parse_args()

    cases = build_cases()
    files, manifest = _serialized(cases)
    expected = {**files, "manifest.json": manifest}
    actual_sources = {
        path.relative_to(CORPUS_ROOT).as_posix()
        for path in CORPUS_ROOT.rglob("*.cj")
    } if CORPUS_ROOT.is_dir() else set()
    stale_sources = sorted(actual_sources - set(files))
    if args.check:
        failures = [
            failure
            for relative, content in expected.items()
            if (failure := _check_file(CORPUS_ROOT / relative, content)) is not None
        ]
        failures.extend(f"stale: test_cases/comprehensive/{path}" for path in stale_sources)
        if failures:
            print("\n".join(failures), file=sys.stderr)
            return 1
        print(f"comprehensive corpus is current: {len(cases)} cases")
        return 0

    for relative, content in expected.items():
        destination = CORPUS_ROOT / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    for relative in stale_sources:
        (CORPUS_ROOT / relative).unlink()
    suffix = f"; removed {len(stale_sources)} stale files" if stale_sources else ""
    print(
        f"generated {len(cases)} cases under {CORPUS_ROOT.relative_to(ROOT)}{suffix}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
