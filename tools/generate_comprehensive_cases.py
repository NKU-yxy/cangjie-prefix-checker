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
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = ROOT / "test_cases" / "comprehensive"
OWNERSHIP_MARKER = ".cangjie-comprehensive-corpus"
OWNERSHIP_MARKER_CONTENT = "cangjie-comprehensive-corpus-v1\n"
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
    oracle_skip_reason: str | None = None
    covers: tuple[str, ...] = ()
    stage: str = "accept"


def _expectation_tier(case: CorpusCase) -> str:
    if case.family == "scale_stress":
        return "diagnostic_scale"
    if case.oracle:
        return "authoritative"
    return "diagnostic_spec_pending"


def _case(
    name: str,
    family: str,
    source: str,
    expected: str,
    *,
    marker: str | None = None,
    marker_occurrence: int = 1,
    marker_start: int = 0,
    complete: bool = True,
    oracle: bool = True,
    oracle_skip_reason: str | None = None,
    covers: tuple[str, ...] = (),
) -> CorpusCase:
    if expected not in {"accept", "reject"}:
        raise ValueError(f"invalid expectation for {name}: {expected}")
    safe_prefix_bytes = None
    if marker is not None:
        if not marker:
            raise ValueError(f"marker must be non-empty for {name}")
        if marker_occurrence < 1:
            raise ValueError(f"marker_occurrence must be positive for {name}")
        if not 0 <= marker_start <= len(source):
            raise ValueError(f"marker_start is out of range for {name}")
        marker_index = marker_start
        for _ in range(marker_occurrence):
            marker_index = source.find(marker, marker_index)
            if marker_index < 0:
                raise ValueError(
                    f"marker occurrence {marker_occurrence} not found for {name}: "
                    f"{marker!r}"
                )
            marker_index += len(marker)
        marker_index -= len(marker)
        safe_prefix_bytes = len(source[:marker_index].encode("utf-8"))
    elif marker_occurrence != 1 or marker_start != 0:
        raise ValueError(f"marker options require marker for {name}")
    if not complete:
        stage = "prefix"
    elif expected == "accept":
        stage = "accept"
    elif family in {"lexical", "syntax", "syntax_matrix"}:
        stage = "syntax"
    else:
        stage = "semantic"
    if oracle:
        if oracle_skip_reason is not None:
            raise ValueError(f"oracle-enabled case {name} cannot have a skip reason")
    elif oracle_skip_reason is None:
        if not complete:
            oracle_skip_reason = "incomplete_prefix_not_supported_by_complete_oracle"
        elif expected == "accept":
            oracle_skip_reason = "vendored_oracle_rejects_supported_source"
        else:
            oracle_skip_reason = "vendored_oracle_not_authoritative_for_rejection"
    return CorpusCase(
        name=name,
        family=family,
        expected=expected,
        complete=complete,
        source=source,
        safe_prefix_bytes=safe_prefix_bytes,
        oracle=oracle,
        oracle_skip_reason=oracle_skip_reason,
        covers=tuple(sorted(set(covers))),
        stage=stage,
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
        marker_occurrence: int = 1,
        marker_start: int = 0,
        oracle: bool = True,
    ) -> None:
        cases.append(
            _case(
                name,
                family,
                source,
                "reject",
                marker=marker,
                marker_occurrence=marker_occurrence,
                marker_start=marker_start,
                oracle=oracle,
            )
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
    # Character grammar treats keyword-shaped text conservatively as an
    # identifier here; the semantic layer is responsible for committing it.
    reject("missing-variable-name", "semantic_syntax_guard", "main(): Unit { let value + other = 1\n println(0) }\n", "+")
    reject(
        "extra-right-paren",
        "syntax",
        "main(): Unit { let x: Int64 = 1)\n println(x) }\n",
        ")",
        marker_occurrence=2,
    )
    reject("extra-right-bracket", "syntax", "main(): Unit { let x: Int64 = 1]\n println(x) }\n", "]")
    reject("malformed-generic-close", "syntax", "class Box<T> { public init(value: T) {} }\nmain(): Unit { let box = Box<Int64,>(1) + 0\n println(0) }\n", ",>")
    reject("function-parameter-missing-colon", "syntax", "func bad(value Int64): Int64 { value }\nmain(): Unit { println(0) }\n", "Int64")
    reject("lambda-missing-arrow", "syntax", "main(): Unit { let f: (Int64) -> Int64 = { x: Int64 x + 1 }\n println(0) }\n", "x + 1")
    reject("double-else", "syntax", "main(): Unit { if (true) {} else {} else @ { println(0) } }\n", "else @")
    reject(
        "dangling-binary-operator",
        "syntax",
        "main(): Unit { let x: Int64 = 1 + )\n println(x) }\n",
        ")",
        marker_occurrence=2,
    )
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


def _systematic_cases() -> list[CorpusCase]:
    """Build a broad, isolated matrix over the grammar and built-in context."""
    cases: list[CorpusCase] = []

    def accept(
        name: str,
        family: str,
        source: str,
        *covers: str,
        oracle: bool = False,
    ) -> None:
        cases.append(
            _case(name, family, source, "accept", oracle=oracle, covers=covers)
        )

    def reject(
        name: str,
        family: str,
        source: str,
        marker: str,
        *covers: str,
        oracle: bool = False,
    ) -> None:
        cases.append(
            _case(
                name,
                family,
                source,
                "reject",
                marker=marker,
                oracle=oracle,
                covers=covers,
            )
        )

    def prefix(name: str, source: str, *covers: str) -> None:
        cases.append(
            _case(
                name,
                "prefix_matrix",
                source,
                "accept",
                complete=False,
                oracle=False,
                covers=covers,
            )
        )

    integer_literals = (
        ("Int8", "1i8", "i8"),
        ("Int16", "2i16", "i16"),
        ("Int32", "3i32", "i32"),
        ("Int64", "4i64", "i64"),
        ("UInt8", "5u8", "u8"),
        ("UInt16", "6u16", "u16"),
        ("UInt32", "7u32", "u32"),
        ("UInt64", "8u64", "u64"),
    )
    for type_name, literal, suffix in integer_literals:
        accept(
            f"primitive-{type_name.lower()}-{suffix}",
            "primitive_matrix",
            f"main(): Unit {{ let value: {type_name} = {literal} }}\n",
            f"grammar:primitive:{type_name}",
            f"grammar:integer_suffix:{suffix}",
        )

    for type_name, literal, suffix in (
        ("Float16", "1.5f16", "f16"),
        ("Float32", "2.5f32", "f32"),
        ("Float64", "3.5f64", "f64"),
    ):
        accept(
            f"primitive-{type_name.lower()}-{suffix}",
            "primitive_matrix",
            f"main(): Unit {{ let value: {type_name} = {literal} }}\n",
            f"grammar:primitive:{type_name}",
            f"grammar:float_suffix:{suffix}",
        )

    for type_name, expression in (
        ("IntNative", "1"),
        ("UIntNative", "1u64"),
        ("Bool", "true"),
        ("Rune", "r'界'"),
        ("String", '"text"'),
        ("Unit", "println(1)"),
    ):
        accept(
            f"primitive-{type_name.lower()}",
            "primitive_matrix",
            f"main(): Unit {{ let value: {type_name} = {expression} }}\n",
            f"grammar:primitive:{type_name}",
            oracle=type_name in {"Bool", "String", "Unit"},
        )
    accept(
        "nothing-return-type",
        "primitive_matrix",
        'func abort(): Nothing { throw "stop" }\nmain(): Unit {}\n',
        "grammar:primitive:Nothing",
        "grammar:statement:throw",
    )

    accept(
        "hex-upper-lower-prefix",
        "literal_matrix",
        "main(): Unit { let a: Int64 = 0xCAFE\n let b: Int64 = 0Xbeef }\n",
        "grammar:literal:hex",
    )
    accept(
        "octal-upper-lower-prefix",
        "literal_matrix",
        "main(): Unit { let a: Int64 = 0o755\n let b: Int64 = 0O17 }\n",
        "grammar:literal:octal",
    )
    accept(
        "binary-upper-lower-prefix",
        "literal_matrix",
        "main(): Unit { let a: Int64 = 0b1010\n let b: Int64 = 0B0101 }\n",
        "grammar:literal:binary",
    )
    accept(
        "float-exponent-variants",
        "literal_matrix",
        "main(): Unit { let a: Float64 = 1e3\n let b: Float64 = 2E+4\n let c: Float64 = 3.0e-2 }\n",
        "grammar:literal:float_exponent",
    )
    accept(
        "all-string-escapes",
        "literal_matrix",
        'main(): Unit { let value: String = "\\\\\\\"\\\'\\n\\t\\r\\b\\f\\v\\0\\$\\u{4F60}" }\n',
        "grammar:literal:string_escapes",
        "grammar:literal:unicode_escape",
        oracle=True,
    )
    accept(
        "rune-escaped",
        "literal_matrix",
        "main(): Unit { let newline: Rune = r'\\n'\n let quote: Rune = r'\\\'' }\n",
        "grammar:literal:rune",
    )
    accept(
        "deeply-nested-comments",
        "literal_matrix",
        "/* 1 /* 2 /* 3 /* 4 */ 3 */ 2 */ 1 */\nmain(): Unit {}\n",
        "grammar:comment:nested",
    )
    accept(
        "crlf-tabs-and-comments",
        "literal_matrix",
        "// crlf\r\nmain(): Unit {\r\n\tlet value: Int64 = 1\r\n}\r\n",
        "grammar:whitespace:crlf",
        "grammar:whitespace:tab",
        "grammar:comment:line",
        oracle=True,
    )

    operator_cases = (
        ("power", "2 ** 3", "**"),
        ("shift-left", "8 << 1", "<<"),
        ("shift-right", "8 >> 1", ">>"),
        ("bitwise-and", "7 & 3", "&"),
        ("bitwise-xor", "7 ^ 3", "^"),
        ("bitwise-or", "7 | 3", "|"),
    )
    for name, expression, operator in operator_cases:
        accept(
            f"operator-{name}",
            "operator_matrix",
            f"main(): Unit {{ let value: Int64 = {expression} }}\n",
            f"grammar:operator:{operator}",
        )
    for name, expression, operator in (
        ("less", "1 < 2", "<"),
        ("less-equal", "1 <= 2", "<="),
        ("greater", "2 > 1", ">"),
        ("greater-equal", "2 >= 1", ">="),
        ("equal", "1 == 1", "=="),
        ("not-equal", "1 != 2", "!="),
        ("logical-and", "true && false", "&&"),
        ("logical-or", "true || false", "||"),
    ):
        accept(
            f"operator-{name}",
            "operator_matrix",
            f"main(): Unit {{ let value: Bool = {expression} }}\n",
            f"grammar:operator:{operator}",
            oracle=True,
        )
    for name, expression, operator in (
        ("unary-minus", "-1", "unary-"),
        ("unary-not", "!false", "unary!"),
    ):
        target_type = "Bool" if name == "unary-not" else "Int64"
        accept(
            f"operator-{name}",
            "operator_matrix",
            f"main(): Unit {{ let value: {target_type} = {expression} }}\n",
            f"grammar:operator:{operator}",
            oracle=True,
        )
    accept(
        "operator-increment-decrement",
        "operator_matrix",
        "main(): Unit { var value: Int64 = 1\n ++value\n --value }\n",
        "grammar:operator:++",
        "grammar:operator:--",
    )
    accept(
        "operator-range-exclusive-step",
        "operator_matrix",
        "main(): Unit { for (i in 0..10:2) { println(i) } }\n",
        "grammar:operator:..",
        "grammar:operator:range_step",
        oracle=True,
    )
    accept(
        "operator-range-inclusive",
        "operator_matrix",
        "main(): Unit { for (i in 0..=10) { println(i) } }\n",
        "grammar:operator:..=",
        oracle=True,
    )
    accept(
        "operator-type-check-and-cast",
        "operator_matrix",
        "main(): Unit { let value: Int64 = 1\n let yes: Bool = value is Int64\n let copy: Int64 = value as Int64 }\n",
        "grammar:operator:is",
        "grammar:operator:as",
    )
    accept(
        "operator-coalescing",
        "operator_matrix",
        "main(): Unit { let value: Int64 = 1 ?? 2 }\n",
        "grammar:operator:??",
    )
    accept(
        "operator-pipelines",
        "operator_matrix",
        "func id(x: Int64): Int64 { x }\nmain(): Unit { let a: Int64 = 1 |> id\n let b: Int64 = 2 ~> id }\n",
        "grammar:operator:|>",
        "grammar:operator:~>",
    )

    compound_operators = (
        "+=", "-=", "*=", "/=", "%=", "**=", "<<=", ">>=", "&=", "^=", "|=",
    )
    body = "\n".join(f" value {operator} 1" for operator in compound_operators)
    accept(
        "all-numeric-compound-assignments",
        "operator_matrix",
        f"main(): Unit {{ var value: Int64 = 8\n{body} }}\n",
        *(f"grammar:assignment:{operator}" for operator in compound_operators),
    )
    accept(
        "logical-compound-assignments",
        "operator_matrix",
        "main(): Unit { var value: Bool = true\n value &&= false\n value ||= true }\n",
        "grammar:assignment:&&=",
        "grammar:assignment:||=",
    )

    accept(
        "array-suffix-type",
        "type_matrix",
        "func first(xs: Int64[]): Int64 { xs[0] }\nmain(): Unit {}\n",
        "grammar:type:array_suffix",
    )
    accept(
        "nullable-type-and-postfix-unwrap",
        "type_matrix",
        "func unwrap(value: Int64?): Int64 { value! }\nmain(): Unit {}\n",
        "grammar:type:nullable",
        "grammar:postfix:unwrap",
    )
    accept(
        "tuple-type-and-literal",
        "type_matrix",
        'main(): Unit { let pair: (String, Int64) = ("age", 7) }\n',
        "grammar:type:tuple",
        "grammar:expression:tuple",
        oracle=True,
    )
    accept(
        "zero-argument-function-type",
        "type_matrix",
        "main(): Unit { let get: () -> Int64 = { => 42 }\n println(get()) }\n",
        "grammar:type:function_zero_arg",
        "grammar:expression:lambda_zero_arg",
        oracle=True,
    )
    accept(
        "nested-function-type",
        "type_matrix",
        "func compose(f: (Int64) -> Int64): (Int64) -> Int64 { { x: Int64 => f(f(x)) } }\nmain(): Unit {}\n",
        "grammar:type:function_nested",
        oracle=True,
    )
    accept(
        "nested-generic-type",
        "type_matrix",
        "main(): Unit { let values: Array<Array<Int64>> = [[1], [2]] }\n",
        "grammar:type:generic_nested",
        oracle=True,
    )
    accept(
        "empty-and-trailing-comma-array",
        "expression_matrix",
        "main(): Unit { let empty: Array<Int64> = []\n let one: Array<Int64> = [1,] }\n",
        "grammar:expression:array_empty",
        "grammar:expression:array_trailing_comma",
    )
    accept(
        "lambda-untyped-multiple-parameters",
        "expression_matrix",
        "main(): Unit { let add: (Int64, Int64) -> Int64 = { a, b => a + b }\n println(add(1, 2)) }\n",
        "grammar:expression:lambda_untyped",
        "grammar:expression:lambda_multi_param",
        oracle=True,
    )
    accept(
        "lambda-block-body-and-iife",
        "expression_matrix",
        "main(): Unit { let value: Int64 = { x: Int64 => { x + 1 } }(2)\n println(value) }\n",
        "grammar:expression:lambda_block",
        "grammar:expression:iife",
        oracle=True,
    )
    accept(
        "object-initializer-postfix",
        "expression_matrix",
        "class Point { var x: Int64\n var y: Int64 }\nmain(): Unit { let p: Point = Point { x: 1, y: 2, } }\n",
        "grammar:expression:struct_init",
    )

    accept(
        "if-else-if-chain",
        "statement_matrix",
        "main(): Unit { if (false) {} else if (true) {} else {} }\n",
        "grammar:statement:if_else_if",
        oracle=True,
    )
    accept(
        "do-while",
        "statement_matrix",
        "main(): Unit { var value: Int64 = 0\n do { value = value + 1 } while (value < 2); }\n",
        "grammar:statement:do_while",
    )
    accept(
        "throw-statement",
        "statement_matrix",
        'main(): Unit { throw "failure" }\n',
        "grammar:statement:throw",
    )
    accept(
        "try-catch",
        "statement_matrix",
        'main(): Unit { try { throw "failure" } catch (error: String) { println(error) } }\n',
        "grammar:statement:try",
        "grammar:statement:catch_typed",
    )
    accept(
        "try-finally",
        "statement_matrix",
        "main(): Unit { try { println(1) } finally { println(2) } }\n",
        "grammar:statement:finally",
    )
    accept(
        "try-untyped-catch-finally",
        "statement_matrix",
        'main(): Unit { try { throw "x" } catch (error) { println(1) } finally { println(2) } }\n',
        "grammar:statement:catch_untyped",
    )
    accept(
        "match-literal-identifier-wildcard",
        "statement_matrix",
        'main(): Unit { let value: Int64 = 1\n match (value) { case 0 => "zero", case other => "other", case _ => "fallback", } }\n',
        "grammar:statement:match",
        "grammar:pattern:literal",
        "grammar:pattern:identifier",
        "grammar:pattern:wildcard",
    )

    accept(
        "package-and-import-forms",
        "declaration_matrix",
        "package app.core;\nimport std.io;\nimport std.math as math;\nimport std.collection.*;\nmain(): Unit {}\n",
        "grammar:declaration:package",
        "grammar:declaration:import_single",
        "grammar:declaration:import_alias",
        "grammar:declaration:import_all",
        oracle=True,
    )
    accept(
        "function-visibility-and-static",
        "declaration_matrix",
        "public static func visible(): Int64 { 1 }\nprivate func hidden(): Int64 { 2 }\nmain(): Unit {}\n",
        "grammar:declaration:public_function",
        "grammar:declaration:private_function",
        "grammar:declaration:static_function",
        oracle=True,
    )
    accept(
        "class-field-modifier-matrix",
        "declaration_matrix",
        "public class Flags { public static let one: Int64 = 1\n private static var two: Int64 = 2\n public var three: Int64\n private let four: Int64 = 4\n public init() {} }\nmain(): Unit {}\n",
        "grammar:declaration:public_class",
        "grammar:declaration:field_modifiers",
        oracle=True,
    )
    accept(
        "generic-struct-with-parent",
        "declaration_matrix",
        "interface Marker<T> {}\npublic struct Pair<T> <: Marker<T> { let left: T\n var right: T }\nmain(): Unit {}\n",
        "grammar:declaration:struct",
        "grammar:declaration:generic",
        "grammar:declaration:parents",
    )
    accept(
        "enum-underlying-values-trailing-comma",
        "declaration_matrix",
        "enum Color: Int64 { Red = 1, Green = 2, Blue, }\nmain(): Unit {}\n",
        "grammar:declaration:enum",
        "grammar:declaration:enum_value",
        "grammar:declaration:enum_trailing_comma",
    )
    accept(
        "public-interface-multiple-parents",
        "declaration_matrix",
        "interface Left {}\ninterface Right {}\npublic interface Both<T> <: Left & Right { func id(value: T): T; }\nmain(): Unit {}\n",
        "grammar:declaration:public_interface",
        "grammar:declaration:multiple_parents",
        "grammar:declaration:interface_semicolon",
    )
    accept(
        "public-extension-with-parent",
        "declaration_matrix",
        "interface Marker {}\nclass Item {}\npublic extend Item <: Marker { public func id(): Int64 { 1 } }\nmain(): Unit {}\n",
        "grammar:declaration:extend",
    )
    operator_names = {
        "+": "plus", "-": "minus", "*": "multiply", "/": "divide",
        "%": "modulo", "**": "power", "==": "equal", "!=": "not_equal",
        "<": "less", ">": "greater", "<=": "less_equal", ">=": "greater_equal",
        "[]": "index", "()": "call",
    }
    for operator, slug in operator_names.items():
        accept(
            f"operator-declaration-{slug}",
            "declaration_matrix",
            f"operator ({operator})(left: Int64, right: Int64): Int64 {{ left }}\nmain(): Unit {{}}\n",
            f"grammar:declaration:operator:{operator}",
        )
    accept(
        "top-level-variable-declarations",
        "declaration_matrix",
        "let globalConstant: Int64 = 1\nvar globalMutable: Int64 = 2\nmain(): Unit { println(globalConstant) }\n",
        "grammar:declaration:top_level_let",
        "grammar:declaration:top_level_var",
    )
    accept(
        "main-with-parameter",
        "declaration_matrix",
        "main(args: Array<String>): Unit {}\n",
        "grammar:declaration:main_parameter",
    )

    syntax_rejections = (
        ("package-trailing-dot", "package app.@\nmain(): Unit {}\n", "@", "grammar:negative:package"),
        ("import-alias-missing-name", "import std.io as @\nmain(): Unit {}\n", "@", "grammar:negative:import"),
        ("empty-enum", "enum Empty { @ }\nmain(): Unit {}\n", "@", "grammar:negative:enum"),
        ("struct-missing-name", "struct @ {}\nmain(): Unit {}\n", "@", "grammar:negative:struct"),
        ("extend-missing-type", "extend @ {}\nmain(): Unit {}\n", "@", "grammar:negative:extend"),
        ("operator-unsupported-token", "operator (@)(): Unit {}\nmain(): Unit {}\n", "@", "grammar:negative:operator"),
        ("do-missing-while", "main(): Unit { do {} @ }\n", "@", "grammar:negative:do_while"),
        ("try-malformed-catch", "main(): Unit { try {} catch @ {} }\n", "@", "grammar:negative:try"),
        ("match-missing-arrow", "main(): Unit { match (1) { case 1 @ 2 } }\n", "@", "grammar:negative:match"),
        ("tuple-missing-item", "main(): Unit { let pair = (1, @) }\n", "@", "grammar:negative:tuple"),
        ("array-double-comma", "main(): Unit { let values = [1, @, 2] }\n", "@", "grammar:negative:array"),
        ("nullable-double-question", "func f(x: Int64?@): Unit {}\nmain(): Unit {}\n", "@", "grammar:negative:nullable"),
        ("malformed-rune", "main(): Unit { let value: Rune = r'@ }\n", "@", "grammar:negative:rune"),
        ("string-followed-by-invalid-token", 'main(): Unit { let value: String = "open"\n @ }\n', "@", "grammar:negative:string"),
        ("invalid-binary-digit-committed", "main(): Unit { let value: Int64 = 0b102@ }\n", "@", "grammar:negative:binary"),
        ("invalid-octal-digit-committed", "main(): Unit { let value: Int64 = 0o78@ }\n", "@", "grammar:negative:octal"),
        ("invalid-hex-digit-committed", "main(): Unit { let value: Int64 = 0xG@ }\n", "@", "grammar:negative:hex"),
        ("incomplete-exponent-committed", "main(): Unit { let value: Float64 = 1e+@ }\n", "@", "grammar:negative:float"),
        ("bad-unicode-escape-committed", 'main(): Unit { let value: String = "\\u{XYZ}@" }\n', "X", "grammar:negative:escape"),
        ("field-missing-type", "class Bad { let value @ }\nmain(): Unit {}\n", "@", "grammar:negative:field"),
    )
    for name, source, marker, cover in syntax_rejections:
        reject(
            name,
            "syntax_matrix",
            source,
            marker,
            cover,
            oracle=name in {"field-missing-type", "string-followed-by-invalid-token"},
        )

    prefixes = (
        ("partial-package-name", "package app.", "grammar:prefix:package"),
        ("partial-import-alias", "import std.io as ", "grammar:prefix:import"),
        ("partial-public-class", "public cla", "grammar:prefix:keyword"),
        ("partial-raw-identifier", "main(): Unit { let `reserved", "grammar:prefix:raw_identifier"),
        ("partial-hex", "main(): Unit { let value: Int64 = 0x", "grammar:prefix:hex"),
        ("partial-binary", "main(): Unit { let value: Int64 = 0b", "grammar:prefix:binary"),
        ("partial-octal", "main(): Unit { let value: Int64 = 0o", "grammar:prefix:octal"),
        ("partial-float-suffix", "main(): Unit { let value: Float32 = 1.0f", "grammar:prefix:float_suffix"),
        ("partial-unicode-escape", 'main(): Unit { let value: String = "\\u{4F', "grammar:prefix:unicode_escape"),
        ("partial-rune", "main(): Unit { let value: Rune = r'", "grammar:prefix:rune"),
        ("partial-line-comment", "main(): Unit {} // comment without newline", "grammar:prefix:line_comment"),
        ("partial-shift", "main(): Unit { let value: Int64 = 1 <", "grammar:prefix:operator"),
        ("partial-inclusive-range", "main(): Unit { for (i in 0..", "grammar:prefix:range"),
        ("partial-coalescing", "main(): Unit { let value = 1 ?", "grammar:prefix:coalescing"),
        ("partial-function-arrow", "main(): Unit { let f: (Int64) -", "grammar:prefix:function_type"),
        ("partial-tuple", "main(): Unit { let pair = (1,", "grammar:prefix:tuple"),
        ("partial-array", "main(): Unit { let values = [1,", "grammar:prefix:array"),
        ("partial-call", "main(): Unit { println(", "grammar:prefix:call"),
        ("partial-index", "main(): Unit { let values = [1]\n values[", "grammar:prefix:index"),
        ("partial-member", 'main(): Unit { let text: String = "x"\n text.', "grammar:prefix:member"),
        ("partial-if-else", "main(): Unit { if (true) {} el", "grammar:prefix:if"),
        ("partial-do-while", "main(): Unit { do {} wh", "grammar:prefix:do"),
        ("partial-try-catch", "main(): Unit { try {} cat", "grammar:prefix:try"),
        ("partial-match-case", "main(): Unit { match (1) { case ", "grammar:prefix:match"),
        ("partial-class-parent", "interface I {}\nclass C <:", "grammar:prefix:parent"),
        ("partial-interface-method", "interface I { func value(", "grammar:prefix:interface"),
        ("partial-enum-case", "enum Color { Red, Gre", "grammar:prefix:enum"),
        ("partial-operator-declaration", "operator (", "grammar:prefix:operator_decl"),
        ("utf8-codepoint-boundary-source", 'main(): Unit { println("编译🚀', "grammar:prefix:utf8"),
    )
    for name, source, cover in prefixes:
        prefix(name, source, cover)

    return cases


def _context_api_cases() -> list[CorpusCase]:
    """Exercise every callable/member family exported by context.json."""
    cases: list[CorpusCase] = []

    def accept(name: str, source: str, *covers: str, oracle: bool = True) -> None:
        cases.append(
            _case(
                name,
                "context_api",
                source,
                "accept",
                oracle=oracle,
                covers=covers,
            )
        )

    def reject(name: str, source: str, marker: str, *covers: str) -> None:
        cases.append(
            _case(
                name,
                "context_api_negative",
                source,
                "reject",
                marker=marker,
                oracle=True,
                covers=covers,
            )
        )

    for function_name in ("println", "print", "eprintln", "eprint"):
        overload_count = 4 if function_name in {"print", "eprint"} else 3
        accept(
            f"global-{function_name}-overloads",
            f'main(): Unit {{ {function_name}("text")\n {function_name}(1)\n {function_name}(1.5) }}\n',
            f"context:global:{function_name}",
            *(f"context:global:{function_name}:overload:{index}" for index in range(min(3, overload_count))),
        )
    accept(
        "global-print-flush-overload",
        'main(): Unit { print("text", true)\n eprint("error", false) }\n',
        "context:global:print",
        "context:global:eprint",
        "context:global:print:overload:3",
        "context:global:eprint:overload:3",
    )
    accept(
        "global-output-extended-overloads",
        "main(): Unit { println(true)\n println(r'x')\n print(true)\n print(r'y') }\n",
        "context:global:println:overload:3",
        "context:global:println:overload:4",
        "context:global:print:overload:4",
        "context:global:print:overload:5",
        oracle=False,
    )
    accept(
        "global-numeric-helpers",
        "main(): Unit { let low: Int64 = min<Int64>(1, 2, [3])\n let high: Int64 = max<Int64>(1, 2, [3])\n let integer: Int64 = abs(1)\n let decimal: Float64 = abs(1.5)\n let bounded: Float64 = clamp(1.5, 0.0, 2.0) }\n",
        "context:global:min",
        "context:global:max",
        "context:global:abs",
        "context:global:abs:overload:0",
        "context:global:abs:overload:1",
        "context:global:clamp",
        oracle=False,
    )

    accept(
        "array-constructor-overloads",
        "main(): Unit { let a: Array<Int64> = Array<Int64>(3, 7)\n let b: Array<Int64> = Array<Int64>([1, 2])\n let c: Array<Int64> = Array<Int64>(3) }\n",
        "context:Array:ctor",
        *(f"context:Array:ctor:{index}" for index in range(3)),
    )
    accept(
        "array-complete-api",
        "main(): Unit { let a: Array<Int64> = [1, 2, 3]\n let size: Int64 = a.size\n let gotOption: Optional<Int64> = a.get(0)\n let got: Int64 = gotOption.getOrThrow()\n a.fill(4)\n a.swap(0, 1)\n let part: Array<Int64> = a.slice(0, 2)\n let copy: Array<Int64> = a.clone()\n let joined: Array<Int64> = a.concat(copy)\n a.reverse()\n let firstOption: Optional<Int64> = a.first()\n let first: Int64 = firstOption.getOrThrow()\n let lastOption: Optional<Int64> = a.last()\n let last: Int64 = lastOption.getOrThrow() }\n",
        "context:Array:field:size",
        "context:Array:iterable",
        *(f"context:Array:method:{name}" for name in ("get", "fill", "swap", "slice", "clone", "concat", "reverse", "first", "last")),
        "context:Optional:method:getOrThrow",
        oracle=False,
    )
    accept(
        "array-list-constructor-overloads",
        "main(): Unit { let a: ArrayList<Int64> = ArrayList<Int64>()\n let b: ArrayList<Int64> = ArrayList<Int64>([1, 2])\n let c: ArrayList<Int64> = ArrayList<Int64>(8) }\n",
        "context:ArrayList:ctor",
        *(f"context:ArrayList:ctor:{index}" for index in range(3)),
    )
    accept(
        "array-list-complete-api",
        "main(): Unit { let a: ArrayList<Int64> = ArrayList<Int64>()\n let b: ArrayList<Int64> = ArrayList<Int64>()\n let empty: Bool = a.isEmpty()\n a.add(1)\n a.add(b)\n a.add(2, 0)\n a.add(b, 0)\n a.remove(0)\n a.reserve(8)\n a.reverse()\n let copy: ArrayList<Int64> = a.clone()\n let values: Array<Int64> = copy.toArray()\n let size: Int64 = a.size\n let capacity: Int64 = a.capacity\n a.clear() }\n",
        "context:ArrayList:field:size",
        "context:ArrayList:field:capacity",
        "context:ArrayList:iterable",
        *(f"context:ArrayList:method:{name}" for name in ("isEmpty", "add", "remove", "clear", "clone", "reserve", "reverse", "toArray")),
        *(f"context:ArrayList:method:add:overload:{index}" for index in range(4)),
    )
    accept(
        "array-list-static-of",
        "main(): Unit { let values: ArrayList<Int64> = ArrayList.of([1, 2]) }\n",
        "context:ArrayList:static_method:of",
        oracle=False,
    )

    accept(
        "stack-and-deque-complete-api",
        "main(): Unit { let stack: ArrayStack<Int64> = ArrayStack<Int64>()\n let reservedStack: ArrayStack<Int64> = ArrayStack<Int64>(8)\n stack.add(1)\n let stackTop: Optional<Int64> = stack.peek()\n let stackRemoved: Optional<Int64> = stack.remove()\n let stackEmpty: Bool = stack.isEmpty()\n stack.reserve(16)\n let stackValues: Array<Int64> = stack.toArray()\n let stackSize: Int64 = stack.size\n let stackCapacity: Int64 = stack.capacity\n stack.clear()\n let stackContract: Stack<Int64> = stack\n stackContract.add(2)\n stackContract.peek()\n stackContract.remove()\n let deque: ArrayDeque<Int64> = ArrayDeque<Int64>()\n let reservedDeque: ArrayDeque<Int64> = ArrayDeque<Int64>(8)\n deque.addFirst(1)\n deque.addLast(2)\n let dequeFirst: Optional<Int64> = deque.removeFirst()\n let dequeLast: Optional<Int64> = deque.removeLast()\n let dequeEmpty: Bool = deque.isEmpty()\n deque.reserve(16)\n let dequeValues: Array<Int64> = deque.toArray()\n let dequeSize: Int64 = deque.size\n let dequeCapacity: Int64 = deque.capacity\n deque.clear()\n let dequeContract: Deque<Int64> = deque\n dequeContract.addFirst(3)\n dequeContract.addLast(4)\n dequeContract.removeFirst()\n dequeContract.removeLast() }\n",
        "context:ArrayStack:ctor",
        "context:ArrayStack:ctor:0",
        "context:ArrayStack:ctor:1",
        "context:ArrayStack:field:size",
        "context:ArrayStack:field:capacity",
        *(f"context:ArrayStack:method:{name}" for name in (
            "add", "peek", "remove", "isEmpty", "reserve", "toArray", "clear",
        )),
        "context:ArrayDeque:ctor",
        "context:ArrayDeque:ctor:0",
        "context:ArrayDeque:ctor:1",
        "context:ArrayDeque:field:size",
        "context:ArrayDeque:field:capacity",
        *(f"context:ArrayDeque:method:{name}" for name in (
            "addFirst", "addLast", "removeFirst", "removeLast", "isEmpty",
            "reserve", "toArray", "clear",
        )),
        "context:interface:Stack",
        "context:interface:Stack:method:add",
        "context:interface:Stack:method:peek",
        "context:interface:Stack:method:remove",
        "context:interface:Deque",
        "context:interface:Deque:method:addFirst",
        "context:interface:Deque:method:addLast",
        "context:interface:Deque:method:removeFirst",
        "context:interface:Deque:method:removeLast",
        oracle=False,
    )

    accept(
        "extended-container-and-optional-api",
        'main(): Unit { let array: Array<Int64> = [1, 2]\n let arrayIndex: Optional<Int64> = array.indexOf(2)\n let list: ArrayList<Int64> = ArrayList<Int64>([1, 2])\n let listValue: Optional<Int64> = list.get(0)\n let map: HashMap<String, Int64> = HashMap<String, Int64>()\n let hasKey: Bool = map.contains("key")\n let set: HashSet<Int64> = HashSet<Int64>()\n set.clear()\n let some: Bool = arrayIndex.isSome()\n let none: Bool = arrayIndex.isNone()\n let fallback: Int64 = arrayIndex.orElse(0)\n let textIndex: Optional<Int64> = "alpha".indexOf("ph") }\n',
        "context:Array:method:indexOf",
        "context:ArrayList:method:get",
        "context:HashMap:method:contains",
        "context:HashSet:method:clear",
        "context:Optional:method:isSome",
        "context:Optional:method:isNone",
        "context:Optional:method:orElse",
        "context:String:method:indexOf",
        oracle=False,
    )

    accept(
        "hash-map-constructor-overloads",
        'main(): Unit { let a: HashMap<String, Int64> = HashMap<String, Int64>()\n let b: HashMap<String, Int64> = HashMap<String, Int64>(8)\n let c: HashMap<String, Int64> = HashMap<String, Int64>([("one", 1)])\n let d: HashMap<String, Int64> = HashMap<String, Int64>(a) }\n',
        "context:HashMap:ctor",
        *(f"context:HashMap:ctor:{index}" for index in range(4)),
    )
    accept(
        "hash-map-complete-api",
        'main(): Unit { let map: HashMap<String, Int64> = HashMap<String, Int64>()\n map.add("one", 1)\n map.add([("two", 2)])\n let value: Int64 = map.get("one").getOrThrow()\n map.remove("one")\n map.remove(["two"])\n let inserted: Bool = map.addIfAbsent("three", 3)\n let keys: KeysView<String> = map.keys()\n let values: ValuesView<Int64> = map.values()\n let keySize: Int64 = keys.size()\n let valueSize: Int64 = values.size()\n let fieldSize: Int64 = map.size\n let fieldCapacity: Int64 = map.capacity\n let callSize: Int64 = map.size()\n let callCapacity: Int64 = map.capacity()\n map.replace("three", 4)\n let copy: HashMap<String, Int64> = map.clone()\n map.clear() }\n',
        "context:HashMap:field:size",
        "context:HashMap:field:capacity",
        *(f"context:HashMap:method:{name}" for name in ("size", "capacity", "get", "add", "remove", "addIfAbsent", "keys", "values", "clone", "clear", "replace")),
        *(f"context:HashMap:method:add:overload:{index}" for index in range(2)),
        *(f"context:HashMap:method:remove:overload:{index}" for index in range(2)),
        "context:KeysView:method:size",
        "context:ValuesView:method:size",
        oracle=False,
    )

    accept(
        "hash-set-constructor-overloads",
        "main(): Unit { let a: HashSet<Int64> = HashSet<Int64>()\n let b: HashSet<Int64> = HashSet<Int64>(8)\n let c: HashSet<Int64> = HashSet<Int64>([1, 2])\n let d: HashSet<Int64> = HashSet<Int64>(a) }\n",
        "context:HashSet:ctor",
        *(f"context:HashSet:ctor:{index}" for index in range(4)),
    )
    accept(
        "hash-set-complete-api",
        "main(): Unit { let set: HashSet<Int64> = HashSet<Int64>()\n let added: Bool = set.add(1)\n set.add([2, 3])\n let inserted: Bool = set.addIfAbsent(4)\n let found: Bool = set.contains(1)\n let removed: Bool = set.remove(1)\n set.remove([2, 3])\n set.reserve(8)\n let copy: HashSet<Int64> = set.clone()\n let values: Array<Int64> = copy.toArray()\n let fieldSize: Int64 = set.size\n let fieldCapacity: Int64 = set.capacity\n let callSize: Int64 = set.size()\n let callCapacity: Int64 = set.capacity() }\n",
        "context:HashSet:field:size",
        "context:HashSet:field:capacity",
        "context:HashSet:iterable",
        *(f"context:HashSet:method:{name}" for name in ("size", "capacity", "add", "addIfAbsent", "contains", "remove", "reserve", "clone", "toArray")),
        *(f"context:HashSet:method:add:overload:{index}" for index in range(2)),
        *(f"context:HashSet:method:remove:overload:{index}" for index in range(2)),
        oracle=False,
    )

    accept(
        "string-constructor-overloads",
        "main(): Unit { let empty: String = String()\n let runes: String = String([r'a', r'b']) }\n",
        "context:String:ctor",
        "context:String:ctor:0",
        "context:String:ctor:1",
        oracle=False,
    )
    accept(
        "string-complete-instance-api",
        'main(): Unit { let text: String = "  alpha  "\n let size: Int64 = text.size\n let empty: Bool = text.isEmpty()\n let starts: Bool = text.startsWith("  a")\n let ends: Bool = text.endsWith("a  ")\n let has: Bool = text.contains("ph")\n let joined: String = text.concat("!")\n let copy: String = text.clone()\n let rune: Rune = text.get(0).getOrThrow()\n let changed: String = text.replace("alpha", "beta")\n let trimmed: String = text.trimAscii()\n let hash: Int64 = text.hashCode()\n let order: Int64 = text.compare("other") }\n',
        "context:String:field:size",
        *(f"context:String:method:{name}" for name in ("isEmpty", "startsWith", "endsWith", "contains", "concat", "clone", "get", "replace", "trimAscii", "hashCode", "compare")),
    )
    accept(
        "string-static-api",
        "main(): Unit { let field: String = String.empty\n let method: String = String.empty()\n let decoded: String = String.fromUtf8([65, 66]) }\n",
        "context:String:static_field:empty",
        "context:String:static_method:empty",
        "context:String:static_method:fromUtf8",
    )
    accept(
        "range-and-view-iteration",
        'main(): Unit { let map: HashMap<String, Int64> = HashMap<String, Int64>()\n for (key in map.keys()) { println(key) }\n for (value in map.values()) { println(value) }\n let range = 0..10\n let count: Int64 = range.size() }\n',
        "context:KeysView:iterable",
        "context:ValuesView:iterable",
        "context:Range:method:size",
        "context:Range:iterable",
        oracle=False,
    )
    accept(
        "built-in-interface-methods",
        "class Key <: Hashable & Equatable<Key> { public init() {}\n public func hashCode(): Int64 { 1 }\n public func equals(other: Key): Bool { true } }\nclass Items <: Collection<Int64> & Iterable<Int64> { public init() {}\n public func size(): Int64 { 0 } }\nmain(): Unit { let key: Hashable = Key()\n println(key.hashCode()) }\n",
        "context:interface:Hashable",
        "context:interface:Equatable",
        "context:interface:Collection",
        "context:interface:Iterable",
        "context:interface:Hashable:method:hashCode",
        "context:interface:Equatable:method:equals",
        "context:interface:Collection:method:size",
    )

    negative_specs = (
        ("array-slice-wrong-argument", 'main(): Unit { let a: Array<Int64> = [1]\n let b = a.slice("bad", 1) }\n', '"bad"', "context:Array:negative"),
        ("array-list-add-wrong-type", 'main(): Unit { let a: ArrayList<Int64> = ArrayList<Int64>()\n a.add("bad") }\n', '"bad"', "context:ArrayList:negative"),
        ("hash-map-key-wrong-type", 'main(): Unit { let map: HashMap<String, Int64> = HashMap<String, Int64>()\n map.add(1, 2) }\n', "1, 2", "context:HashMap:negative"),
        ("hash-set-contains-wrong-type", 'main(): Unit { let set: HashSet<Int64> = HashSet<Int64>()\n let found: Bool = set.contains("bad") }\n', '"bad"', "context:HashSet:negative"),
        ("string-method-wrong-type", 'main(): Unit { let text: String = "x"\n let found: Bool = text.contains(1) }\n', "1)", "context:String:negative"),
        ("optional-result-wrong-type", 'main(): Unit { let a: Array<Int64> = [1]\n let text: String = a.get(0).getOrThrow() }\n', "getOrThrow()", "context:Optional:negative"),
    )
    for name, source, marker, cover in negative_specs:
        reject(name, source, marker, cover)

    return cases


def _scale_cases() -> list[CorpusCase]:
    """Large and deeply nested cases for state-growth and late-error paths."""
    cases: list[CorpusCase] = []

    def accept(
        name: str,
        source: str,
        cover: str,
        *,
        oracle: bool = False,
    ) -> None:
        cases.append(
            _case(
                name,
                "scale_stress",
                source,
                "accept",
                oracle=oracle,
                covers=(cover,),
            )
        )

    declarations = "\n".join(
        f" let value_{index}: Int64 = {index}" for index in range(300)
    )
    accept(
        "three-hundred-local-declarations",
        f"main(): Unit {{\n{declarations}\n println(value_299)\n}}\n",
        "stress:many_locals",
        oracle=True,
    )

    valid_prefix = "\n".join(
        f" let before_{index}: Int64 = {index}" for index in range(250)
    )
    late_source = (
        f"main(): Unit {{\n{valid_prefix}\n"
        ' let late_failure: Int64 = "late-error"\n'
        " println(late_failure)\n}\n"
    )
    cases.append(
        _case(
            "late-error-after-250-declarations",
            "scale_stress",
            late_source,
            "reject",
            marker='"late-error"',
            oracle=True,
            covers=("stress:late_error",),
        )
    )

    depth = 96
    accept(
        "ninety-six-nested-blocks",
        "main(): Unit { " + "{ " * depth + "println(1) " + "} " * depth + "}\n",
        "stress:nested_blocks",
        oracle=True,
    )
    accept(
        "sixty-four-nested-comments",
        "/* " * 64 + "deep" + " */" * 64 + "\nmain(): Unit {}\n",
        "stress:nested_comments",
    )
    accept(
        "four-kilobyte-identifier",
        "main(): Unit { let value_"
        + "x" * 4096
        + ": Int64 = 1 }\n",
        "stress:long_identifier",
        oracle=True,
    )
    accept(
        "eight-kilobyte-string",
        'main(): Unit { let text: String = "'
        + "仓颉abc" * 1024
        + '"\n println(text) }\n',
        "stress:long_utf8_string",
        oracle=True,
    )
    accept(
        "three-hundred-element-array",
        "main(): Unit { let values: Array<Int64> = ["
        + ", ".join(str(index) for index in range(300))
        + "]\n println(values.size) }\n",
        "stress:large_array",
        oracle=True,
    )
    functions = "\n".join(
        f"func function_{index}(value: Int64): Int64 {{ value + {index} }}"
        for index in range(80)
    )
    accept(
        "eighty-top-level-functions",
        functions + "\nmain(): Unit { println(function_79(1)) }\n",
        "stress:many_declarations",
        oracle=True,
    )
    crlf_body = "".join(
        f" let crlf_{index}: Int64 = {index}\r\n" for index in range(200)
    )
    accept(
        "two-hundred-crlf-lines",
        "main(): Unit {\r\n" + crlf_body + "}\r\n",
        "stress:crlf_lines",
        oracle=True,
    )
    return cases


def _supplemental_cases() -> list[CorpusCase]:
    """Cover isolated productions and semantic invariants missed by broad cases."""
    cases: list[CorpusCase] = []

    def accept(
        name: str,
        source: str,
        *covers: str,
        oracle: bool = False,
    ) -> None:
        cases.append(
            _case(
                name,
                "supplemental",
                source,
                "accept",
                oracle=oracle,
                covers=covers,
            )
        )

    def reject(
        name: str,
        source: str,
        marker: str,
        *covers: str,
        marker_occurrence: int = 1,
        marker_start: int = 0,
        oracle: bool = True,
    ) -> None:
        cases.append(
            _case(
                name,
                "supplemental_negative",
                source,
                "reject",
                marker=marker,
                marker_occurrence=marker_occurrence,
                marker_start=marker_start,
                oracle=oracle,
                covers=covers,
            )
        )

    accept(
        "this-and-delegated-constructor",
        "class Point { var x: Int64\n public init(value: Int64) { this.x = value }\n public init() { this(0) } }\nmain(): Unit { let point: Point = Point() }\n",
        "grammar:expression:this",
        "grammar:constructor:delegated_this",
        oracle=False,
    )
    accept(
        "super-member-call",
        "class Base { public init() {}\n public func value(): Int64 { 1 } }\nclass Child <: Base { public init() {}\n public func value(): Int64 { super.value() } }\nmain(): Unit { println(Child().value()) }\n",
        "grammar:expression:super",
    )
    accept(
        "class-member-modifier-matrix",
        "class Members { value: Int64 = 1\n private init() {}\n private func hidden(): Int64 { value }\n public static func version(): Int64 { 1 } }\nmain(): Unit {}\n",
        "grammar:constructor:private",
        "grammar:method:private",
        "grammar:method:static",
        "grammar:field:implicit_kind",
    )
    accept(
        "generic-function-method-and-interface-method",
        "func identity<T>(value: T): T { value }\ninterface Transform { func apply<T>(value: T): T }\nclass Transformer <: Transform { public init() {}\n public func apply<T>(value: T): T { value } }\nmain(): Unit { let value: String = identity<String>(Transformer().apply<String>(\"ok\")) }\n",
        "grammar:generic:function",
        "grammar:generic:method",
        "grammar:generic:interface_method",
        oracle=True,
    )
    accept(
        "right-associative-assignment",
        "main(): Unit { var left: Int64 = 0\n var right: Int64 = 0\n left = right = 3 }\n",
        "grammar:assignment:right_associative",
    )
    accept(
        "block-expression-with-local-result",
        "main(): Unit { let result: Int64 = { let inner: Int64 = 1\n inner + 1 }\n println(result) }\n",
        "grammar:expression:block",
        oracle=True,
    )
    accept(
        "try-without-handler",
        "main(): Unit { try { println(1) } }\n",
        "grammar:statement:try_without_handler",
    )
    accept(
        "match-case-block-body",
        "main(): Unit { match (1) { case 1 => { println(1) }, case _ => { println(0) } } }\n",
        "grammar:statement:match_block_body",
    )
    accept(
        "dotted-nominal-type",
        "func consume(value: library.model.Item): Unit {}\nmain(): Unit {}\n",
        "grammar:type:dotted_name",
    )
    accept(
        "main-omitted-return-type",
        "main() { println(1) }\n",
        "grammar:declaration:main_omitted_return",
    )
    accept(
        "class-multiple-interface-parents",
        "interface Left {}\ninterface Right {}\nclass Both <: Left & Right { public init() {} }\nmain(): Unit { let item: Left = Both() }\n",
        "grammar:class:multiple_parents",
        oracle=True,
    )
    accept(
        "optional-semicolon-matrix",
        "let global: Int64 = 1;\nmain(): Unit { var local: Int64 = global; local = local + 1; return; }\n",
        "grammar:semicolon:declaration",
        "grammar:semicolon:expression",
        "grammar:semicolon:return",
    )
    accept(
        "three-element-tuple",
        'main(): Unit { let triple: (Int64, String, Bool) = (1, "two", true) }\n',
        "grammar:expression:tuple_three",
        oracle=True,
    )
    accept(
        "postfix-member-call-index-chain",
        "class Store { let rows: Array<Array<Int64>>\n public init(values: Array<Array<Int64>>) { rows = values }\n public func all(): Array<Array<Int64>> { rows } }\nmain(): Unit { let value: Int64 = Store([[1]]).all()[0][0]\n println(value) }\n",
        "grammar:postfix:chain",
        oracle=True,
    )
    accept(
        "constructor-default-parameter",
        "class Box { let value: Int64\n public init(initial: Int64 = 1) { value = initial } }\nmain(): Unit { let box: Box = Box() }\n",
        "grammar:constructor:default_parameter",
    )

    reject(
        "duplicate-local-declaration",
        "main(): Unit { let value: Int64 = 1\n let value: Int64 = 2\n println(value) }\n",
        "let value: Int64 = 2",
        "semantic:scope:duplicate_local",
        oracle=False,
    )
    reject(
        "duplicate-function-parameter",
        "func bad(value: Int64, value: Int64): Int64 { value }\nmain(): Unit { println(0) }\n",
        "value: Int64):",
        "semantic:scope:duplicate_parameter",
    )
    reject(
        "generic-type-argument-overflow",
        "class Box<T> { public init(value: T) {} }\nmain(): Unit { let box: Box<Int64, String> = Box<Int64, String>(1) }\n",
        ", String>",
        "semantic:generic:type_arity",
    )
    reject(
        "generic-function-type-argument-overflow",
        "func id<T>(value: T): T { value }\nmain(): Unit { let value: Int64 = id<Int64, String>(1) }\n",
        ", String>",
        "semantic:generic:function_arity",
    )
    reject(
        "interface-method-missing",
        "interface Named { func name(): String }\nclass Missing <: Named { public init() {} }\nmain(): Unit { println(0) }\n",
        "Missing <: Named",
        "semantic:interface:missing_method",
    )
    reject(
        "interface-method-parameter-mismatch",
        "interface Convert { func convert(value: Int64): String }\nclass Bad <: Convert { public init() {}\n public func convert(value: String): String { value } }\nmain(): Unit { println(0) }\n",
        "value: String",
        "semantic:interface:parameter_mismatch",
    )
    reject(
        "interface-method-return-mismatch",
        "interface Count { func count(): Int64 }\nclass Bad <: Count { public init() {}\n public func count(): String { \"bad\" } }\nmain(): Unit { println(0) }\n",
        "String",
        "semantic:interface:return_mismatch",
    )
    reject(
        "immutable-field-assignment-outside-constructor",
        "class Box { let value: Int64\n public init() { value = 1 }\n public func change(): Unit { value = 2 } }\nmain(): Unit {}\n",
        "value = 2",
        "semantic:field:immutable_assignment",
        oracle=False,
    )
    reject(
        "duplicate-named-argument",
        "func add(left: Int64, right: Int64): Int64 { left + right }\nmain(): Unit { let value: Int64 = add(left: 1, left: 2) }\n",
        "left: 2",
        "semantic:call:duplicate_named_argument",
    )
    reject(
        "for-variable-escapes-loop",
        "main(): Unit { for (item in [1, 2]) { println(item) }\n println(item) }\n",
        "item)",
        "semantic:scope:for_variable",
        marker_occurrence=2,
    )
    reject(
        "index-non-indexable-value",
        "main(): Unit { let value: Int64 = 1\n let bad: Int64 = value[0]\n println(bad) }\n",
        "value[0]",
        "semantic:index:receiver",
    )
    reject(
        "constructor-too-many-arguments",
        "class Box { public init(value: Int64) {} }\nmain(): Unit { let box: Box = Box(1, 2) }\n",
        "2)",
        "semantic:constructor:arity",
        oracle=True,
    )
    return cases


def build_cases(
    *,
    seed: int = 20260805,
    generated_cases_per_family: int = 8,
) -> list[CorpusCase]:
    """Return the complete deterministic corpus before materialization."""
    from benchmark.hidden_semantic_fuzz import generate_cases

    cases = (
        _manual_cases()
        + _systematic_cases()
        + _context_api_cases()
        + _scale_cases()
        + _supplemental_cases()
    )
    for hidden in generate_cases(seed=seed, cases_per_family=generated_cases_per_family):
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
                covers=(f"generated:{hidden.family}",),
                stage="accept" if hidden.expected_valid else "semantic",
            )
        )

    names = [case.name for case in cases]
    if len(names) != len(set(names)):
        raise RuntimeError("duplicate corpus case names")
    return sorted(cases, key=lambda case: (case.family, case.expected, case.name))


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _dependency_paths() -> tuple[Path, ...]:
    """Files whose bytes define grammar, context, generation, or oracle labels."""
    fixed = (
        ROOT / "tools" / "generate_comprehensive_cases.py",
        ROOT / "benchmark" / "hidden_semantic_fuzz.py",
        ROOT / "context.json",
        ROOT / "grammar" / "cangjie.gbnf",
        ROOT / "grammar" / "cangjie_token.gbnf",
    )
    oracle_root = ROOT / "third_party" / "cangjie_typechecker" / "typechecker"
    oracle = tuple(
        sorted(
            (
                path
                for path in oracle_root.iterdir()
                if path.is_file()
                and (path.suffix == ".py" or path.name in {"cangjie.lark", "context.json"})
            ),
            key=lambda path: path.as_posix(),
        )
    )
    paths = fixed + oracle
    missing = [path for path in paths if not path.is_file()]
    if missing:
        raise RuntimeError(
            "corpus integrity dependency is missing: "
            + ", ".join(str(path) for path in missing)
        )
    return paths


def _corpus_source_sha256(files: dict[str, str]) -> str:
    """Digest sorted ``path NUL UTF-8-source NUL`` records."""
    digest = hashlib.sha256()
    for relative, source in sorted(files.items()):
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(source.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _coverage_targets() -> set[str]:
    targets = {
        *(f"grammar:primitive:{name}" for name in (
            "Int8", "Int16", "Int32", "Int64", "IntNative",
            "UInt8", "UInt16", "UInt32", "UInt64", "UIntNative",
            "Float16", "Float32", "Float64", "Bool", "Rune", "String",
            "Unit", "Nothing",
        )),
        *(f"grammar:integer_suffix:{suffix}" for suffix in (
            "i8", "i16", "i32", "i64", "u8", "u16", "u32", "u64",
        )),
        *(f"grammar:float_suffix:{suffix}" for suffix in ("f16", "f32", "f64")),
        *(f"grammar:operator:{operator}" for operator in (
            "**", "<<", ">>", "&", "^", "|", "<", "<=", ">", ">=",
            "==", "!=", "&&", "||", "unary-", "unary!", "++", "--",
            "..", "..=", "range_step", "is", "as", "??", "|>", "~>",
        )),
        *(f"grammar:assignment:{operator}" for operator in (
            "+=", "-=", "*=", "/=", "%=", "**=", "<<=", ">>=", "&=",
            "^=", "|=", "&&=", "||=",
        )),
        *(f"grammar:declaration:operator:{operator}" for operator in (
            "+", "-", "*", "/", "%", "**", "==", "!=", "<", ">", "<=",
            ">=", "[]", "()",
        )),
        "grammar:literal:hex",
        "grammar:literal:octal",
        "grammar:literal:binary",
        "grammar:literal:float_exponent",
        "grammar:literal:string_escapes",
        "grammar:literal:unicode_escape",
        "grammar:literal:rune",
        "grammar:comment:nested",
        "grammar:comment:line",
        "grammar:whitespace:crlf",
        "grammar:whitespace:tab",
        "grammar:type:array_suffix",
        "grammar:type:nullable",
        "grammar:type:tuple",
        "grammar:type:function_zero_arg",
        "grammar:type:function_nested",
        "grammar:type:generic_nested",
        "grammar:postfix:unwrap",
        "grammar:expression:tuple",
        "grammar:expression:lambda_zero_arg",
        "grammar:expression:array_empty",
        "grammar:expression:array_trailing_comma",
        "grammar:expression:lambda_untyped",
        "grammar:expression:lambda_multi_param",
        "grammar:expression:lambda_block",
        "grammar:expression:iife",
        "grammar:expression:struct_init",
        "grammar:statement:if_else_if",
        "grammar:statement:do_while",
        "grammar:statement:throw",
        "grammar:statement:try",
        "grammar:statement:catch_typed",
        "grammar:statement:catch_untyped",
        "grammar:statement:finally",
        "grammar:statement:match",
        "grammar:pattern:literal",
        "grammar:pattern:identifier",
        "grammar:pattern:wildcard",
        "grammar:declaration:package",
        "grammar:declaration:import_single",
        "grammar:declaration:import_alias",
        "grammar:declaration:import_all",
        "grammar:declaration:public_function",
        "grammar:declaration:private_function",
        "grammar:declaration:static_function",
        "grammar:declaration:public_class",
        "grammar:declaration:field_modifiers",
        "grammar:declaration:struct",
        "grammar:declaration:generic",
        "grammar:declaration:parents",
        "grammar:declaration:enum",
        "grammar:declaration:enum_value",
        "grammar:declaration:enum_trailing_comma",
        "grammar:declaration:public_interface",
        "grammar:declaration:multiple_parents",
        "grammar:declaration:interface_semicolon",
        "grammar:declaration:extend",
        "grammar:declaration:top_level_let",
        "grammar:declaration:top_level_var",
        "grammar:declaration:main_parameter",
        "grammar:expression:this",
        "grammar:constructor:delegated_this",
        "grammar:expression:super",
        "grammar:constructor:private",
        "grammar:method:private",
        "grammar:method:static",
        "grammar:field:implicit_kind",
        "grammar:generic:function",
        "grammar:generic:method",
        "grammar:generic:interface_method",
        "grammar:assignment:right_associative",
        "grammar:expression:block",
        "grammar:statement:try_without_handler",
        "grammar:statement:match_block_body",
        "grammar:type:dotted_name",
        "grammar:declaration:main_omitted_return",
        "grammar:class:multiple_parents",
        "grammar:semicolon:declaration",
        "grammar:semicolon:expression",
        "grammar:semicolon:return",
        "grammar:expression:tuple_three",
        "grammar:postfix:chain",
        "grammar:constructor:default_parameter",
        "semantic:scope:duplicate_local",
        "semantic:scope:duplicate_parameter",
        "semantic:generic:type_arity",
        "semantic:generic:function_arity",
        "semantic:interface:missing_method",
        "semantic:interface:parameter_mismatch",
        "semantic:interface:return_mismatch",
        "semantic:field:immutable_assignment",
        "semantic:call:duplicate_named_argument",
        "semantic:scope:for_variable",
        "semantic:index:receiver",
        "semantic:constructor:arity",
    }

    context = json.loads((ROOT / "context.json").read_text(encoding="utf-8"))
    targets.update(f"context:global:{name}" for name in context["global_functions"])
    for name, overloads in context["global_functions"].items():
        if len(overloads) > 1:
            targets.update(
                f"context:global:{name}:overload:{index}"
                for index in range(len(overloads))
            )
    for name, spec in context["interfaces"].items():
        targets.add(f"context:interface:{name}")
        targets.update(
            f"context:interface:{name}:method:{method}"
            for method in spec.get("methods", {})
        )
    for name, spec in context["nominals"].items():
        if spec.get("constructors"):
            targets.add(f"context:{name}:ctor")
            targets.update(
                f"context:{name}:ctor:{index}"
                for index in range(len(spec["constructors"]))
            )
        targets.update(
            f"context:{name}:field:{field}"
            for field in spec.get("instance_fields", {})
        )
        targets.update(
            f"context:{name}:static_field:{field}"
            for field in spec.get("static_fields", {})
        )
        targets.update(
            f"context:{name}:method:{method}"
            for method in spec.get("instance_methods", {})
        )
        for method, entry in spec.get("instance_methods", {}).items():
            if isinstance(entry, list) and len(entry) > 1:
                targets.update(
                    f"context:{name}:method:{method}:overload:{index}"
                    for index in range(len(entry))
                )
        targets.update(
            f"context:{name}:static_method:{method}"
            for method in spec.get("static_methods", {})
        )
        if spec.get("iterable_element") is not None:
            targets.add(f"context:{name}:iterable")
    return targets


def _serialized(
    cases: list[CorpusCase],
    *,
    seed: int,
    generated_cases_per_family: int,
) -> tuple[dict[str, str], str, str]:
    files: dict[str, str] = {}
    manifest_cases: list[dict[str, object]] = []
    for case in cases:
        group = "prefix" if not case.complete else ("valid" if case.expected == "accept" else "invalid")
        relative = Path(group) / f"{_slug(case.family)}__{_slug(case.name)}.cj"
        if relative.as_posix() in files:
            raise RuntimeError(f"duplicate corpus output path: {relative}")
        files[relative.as_posix()] = case.source
        metadata = asdict(case)
        metadata.pop("source")
        metadata["file"] = relative.as_posix()
        source_bytes = case.source.encode("utf-8")
        metadata["source_bytes"] = len(source_bytes)
        metadata["source_sha256"] = _sha256(source_bytes)
        metadata["safe_prefix_sha256"] = (
            _sha256(source_bytes[:case.safe_prefix_bytes])
            if case.safe_prefix_bytes is not None
            else None
        )
        metadata["expectation_tier"] = _expectation_tier(case)
        manifest_cases.append(metadata)

    family_counts: dict[str, int] = {}
    expectation_counts: dict[str, int] = {}
    stage_counts: dict[str, int] = {}
    complete_counts = {"complete": 0, "incomplete": 0}
    oracle_counts = {"checked": 0, "skipped_complete": 0, "skipped_incomplete": 0}
    expectation_tier_counts: dict[str, int] = {}
    for case in cases:
        family_counts[case.family] = family_counts.get(case.family, 0) + 1
        label = "prefix_accept" if not case.complete else case.expected
        expectation_counts[label] = expectation_counts.get(label, 0) + 1
        stage_counts[case.stage] = stage_counts.get(case.stage, 0) + 1
        complete_counts["complete" if case.complete else "incomplete"] += 1
        if case.oracle:
            oracle_counts["checked"] += 1
        elif case.complete:
            oracle_counts["skipped_complete"] += 1
        else:
            oracle_counts["skipped_incomplete"] += 1
        tier = _expectation_tier(case)
        expectation_tier_counts[tier] = expectation_tier_counts.get(tier, 0) + 1
    coverage_counts: dict[str, int] = {}
    for case in cases:
        for target in case.covers:
            coverage_counts[target] = coverage_counts.get(target, 0) + 1
    coverage_targets = _coverage_targets()
    missing_coverage = sorted(coverage_targets - set(coverage_counts))
    if missing_coverage:
        raise RuntimeError(
            "corpus is missing required coverage:\n  " + "\n  ".join(missing_coverage)
        )
    dependencies = {
        path.relative_to(ROOT).as_posix(): _sha256(path.read_bytes())
        for path in _dependency_paths()
    }
    corpus_sha256 = _corpus_source_sha256(files)
    manifest: dict[str, object] = {
        "schema_version": 3,
        "description": "仓颉流式前缀检查器固定综合回归语料",
        "generator": "tools/generate_comprehensive_cases.py",
        "generation": {
            "seed": seed,
            "generated_cases_per_family": generated_cases_per_family,
        },
        "case_count": len(cases),
        "family_counts": dict(sorted(family_counts.items())),
        "expectation_counts": dict(sorted(expectation_counts.items())),
        "stage_counts": dict(sorted(stage_counts.items())),
        "complete_counts": complete_counts,
        "oracle_counts": oracle_counts,
        "expectation_tier_counts": dict(sorted(expectation_tier_counts.items())),
        "integrity": {
            "algorithm": "sha256",
            "corpus_digest_format": "sorted-path-nul-source-bytes-nul-v1",
            "corpus_sha256": corpus_sha256,
            "dependencies": dict(sorted(dependencies.items())),
        },
        "coverage": {
            "required_target_count": len(coverage_targets),
            "covered_target_count": len(coverage_targets),
            "missing_targets": [],
            "counts": dict(sorted(coverage_counts.items())),
        },
        "cases": manifest_cases,
    }
    coverage_lines = [
        "# 综合语料覆盖矩阵",
        "",
        f"- 样例总数：`{len(cases)}`",
        f"- 完整合法：`{expectation_counts.get('accept', 0)}`",
        f"- 完整错误：`{expectation_counts.get('reject', 0)}`",
        f"- 可补全前缀：`{expectation_counts.get('prefix_accept', 0)}`",
        f"- vendored reference-derived 类型 oracle 复核：`{oracle_counts['checked']}/{complete_counts['complete']}`",
        f"- 强制覆盖目标：`{len(coverage_targets)}/{len(coverage_targets)}`",
        f"- 语料源码 SHA-256：`{corpus_sha256}`",
        "",
        "## 按测试族统计",
        "",
        "| 测试族 | 数量 |",
        "|---|---:|",
        *(f"| `{name}` | {count} |" for name, count in sorted(family_counts.items())),
        "",
        "## 强制覆盖目标",
        "",
        "生成器会在以下任意目标缺失时直接失败。括号内为覆盖该目标的样例数。",
        "",
    ]
    grouped: dict[str, list[tuple[str, int]]] = {}
    for target in sorted(coverage_targets):
        group = target.split(":", 1)[0]
        grouped.setdefault(group, []).append((target, coverage_counts[target]))
    for group, entries in grouped.items():
        coverage_lines.extend(
            [
                f"### {group}",
                "",
                *(f"- `{target}` ({count})" for target, count in entries),
                "",
            ]
        )
    return (
        files,
        # Keep the checked-in manifest compact enough for readable reviews.
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
        "\n".join(coverage_lines).rstrip() + "\n",
    )


def _check_file(path: Path, expected: str) -> str | None:
    try:
        display = path.relative_to(ROOT)
    except ValueError:
        display = path
    if not path.is_file():
        return f"missing: {display}"
    actual = path.read_bytes().decode("utf-8")
    if actual != expected:
        return f"out of date: {display}"
    return None


def _validated_managed_sources(corpus_root: Path) -> dict[str, str]:
    """Return files that a trustworthy prior manifest allows us to replace.

    Merely finding a generator-looking string in JSON is not ownership proof.  A
    managed output must carry the current schema/integrity format, its aggregate
    digest must match, and every source must still match its recorded digest.
    """
    marker_path = corpus_root / OWNERSHIP_MARKER
    try:
        marker = marker_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError(
            f"refusing non-empty output without ownership marker: {corpus_root}"
        ) from error
    if marker != OWNERSHIP_MARKER_CONTENT:
        raise ValueError(f"refusing invalid ownership marker: {marker_path}")

    manifest_path = corpus_root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(
            f"refusing non-empty, unmanaged corpus output directory: {corpus_root}"
        ) from error
    if (
        not isinstance(manifest, dict)
        or manifest.get("generator") != "tools/generate_comprehensive_cases.py"
        or manifest.get("schema_version") != 3
    ):
        raise ValueError(
            f"refusing non-empty output without this generator's schema-3 manifest: "
            f"{corpus_root}"
        )
    integrity = manifest.get("integrity")
    cases = manifest.get("cases")
    if (
        not isinstance(integrity, dict)
        or integrity.get("algorithm") != "sha256"
        or integrity.get("corpus_digest_format")
        != "sorted-path-nul-source-bytes-nul-v1"
        or not isinstance(integrity.get("corpus_sha256"), str)
        or not isinstance(cases, list)
        or manifest.get("case_count") != len(cases)
    ):
        raise ValueError(f"refusing invalid managed corpus manifest: {manifest_path}")

    sources: dict[str, str] = {}
    aggregate: dict[str, str] = {}
    for index, raw_case in enumerate(cases):
        if not isinstance(raw_case, dict):
            raise ValueError(f"invalid managed corpus case at index {index}")
        relative = raw_case.get("file")
        declared_digest = raw_case.get("source_sha256")
        if (
            not isinstance(relative, str)
            or Path(relative).is_absolute()
            or Path(relative).suffix != ".cj"
            or not isinstance(declared_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", declared_digest) is None
            or relative in sources
        ):
            raise ValueError(f"invalid managed corpus source at index {index}")
        path = (corpus_root / relative).resolve()
        try:
            path.relative_to(corpus_root)
        except ValueError as error:
            raise ValueError(f"managed corpus source escapes output: {relative}") from error
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise ValueError(f"managed corpus source is missing: {relative}") from error
        if _sha256(payload) != declared_digest:
            raise ValueError(f"managed corpus source hash mismatch: {relative}")
        try:
            aggregate[relative] = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"managed corpus source is not UTF-8: {relative}") from error
        sources[relative] = declared_digest
    if _corpus_source_sha256(aggregate) != integrity["corpus_sha256"]:
        raise ValueError("managed corpus aggregate hash mismatch")

    actual = _managed_source_files(corpus_root)
    unknown = sorted(actual - set(sources))
    if unknown:
        raise ValueError(
            "refusing managed output with unknown .cj source(s): " + ", ".join(unknown)
        )
    return sources


def _validate_output_root(corpus_root: Path) -> dict[str, str]:
    """Refuse destinations where stale-source cleanup could touch other data."""
    if corpus_root == ROOT or corpus_root in ROOT.parents:
        raise ValueError(
            f"refusing unsafe corpus output directory at/above repository root: {corpus_root}"
        )
    if not corpus_root.exists():
        return {}
    if not corpus_root.is_dir():
        raise ValueError(f"corpus output exists but is not a directory: {corpus_root}")
    if not any(corpus_root.iterdir()):
        return {}
    return _validated_managed_sources(corpus_root)


def _managed_source_files(corpus_root: Path) -> set[str]:
    sources: set[str] = set()
    for group in ("valid", "invalid", "prefix"):
        group_root = corpus_root / group
        if group_root.is_dir():
            sources.update(
                path.relative_to(corpus_root).as_posix()
                for path in group_root.rglob("*.cj")
            )
    return sources


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Do not write; fail if checked-in corpus differs from the generator.",
    )
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument("--generated-cases-per-family", type=int, default=8)
    parser.add_argument(
        "--output",
        type=Path,
        default=CORPUS_ROOT,
        help="Corpus output directory; use a temporary path for fresh seeded suites.",
    )
    args = parser.parse_args()

    if args.generated_cases_per_family < 0:
        parser.error("--generated-cases-per-family must be non-negative")
    corpus_root = args.output.resolve()
    try:
        managed_sources = _validate_output_root(corpus_root)
    except ValueError as error:
        parser.error(str(error))
    cases = build_cases(
        seed=args.seed,
        generated_cases_per_family=args.generated_cases_per_family,
    )
    files, manifest, coverage_markdown = _serialized(
        cases,
        seed=args.seed,
        generated_cases_per_family=args.generated_cases_per_family,
    )
    expected = {
        **files,
        "manifest.json": manifest,
        "COVERAGE.md": coverage_markdown,
        OWNERSHIP_MARKER: OWNERSHIP_MARKER_CONTENT,
    }
    stale_sources = sorted(set(managed_sources) - set(files))
    if args.check:
        failures = [
            failure
            for relative, content in expected.items()
            if (failure := _check_file(corpus_root / relative, content)) is not None
        ]
        failures.extend(f"stale: {corpus_root / path}" for path in stale_sources)
        if failures:
            print("\n".join(failures), file=sys.stderr)
            return 1
        print(f"comprehensive corpus is current: {len(cases)} cases")
        return 0

    if stale_sources:
        print(
            "refusing to delete stale managed source(s); remove them explicitly:\n"
            + "\n".join(str(corpus_root / path) for path in stale_sources),
            file=sys.stderr,
        )
        return 1

    # A marker and manifest are deliberately not treated as permission to
    # overwrite an existing source with different bytes: both are public,
    # reproducible files and therefore can be forged in an unrelated
    # directory.  Updating generated metadata and adding missing sources is
    # safe, but changing an existing .cj requires the caller to remove or move
    # the old corpus explicitly first.
    conflicting_sources = []
    for relative, content in files.items():
        destination = corpus_root / relative
        if destination.is_file() and destination.read_bytes() != content.encode("utf-8"):
            conflicting_sources.append(destination)
    if conflicting_sources:
        print(
            "refusing to overwrite existing managed source(s) with different bytes; "
            "remove or move the old corpus explicitly:\n"
            + "\n".join(str(path) for path in conflicting_sources),
            file=sys.stderr,
        )
        return 1

    for relative, content in expected.items():
        destination = corpus_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    print(f"generated {len(cases)} cases under {corpus_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
