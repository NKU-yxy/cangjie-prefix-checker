"""Enumerate continuation methods that rescue a wrong-typed literal argument.

For `f("bad")` (f wants Int64), the prefix `f("bad` stays extendable iff some
suffix method on String yields Int64 (or the literal can convert).  Enumerate
every plausible member on String / Int64 / Float64 / Bool via the official
checker, keyed by (source-type, target-type).
"""
import sys
from pathlib import Path

sys.path.insert(0, "/ref/typechecker")
import typechecker.builtin_context as bc  # noqa: E402

bc._CONTEXT_PATH = Path("/workspace/context.json")
bc._builtin_ctx_singleton = None
from typechecker.checker import typecheck_tree  # noqa: E402
from typechecker.errors import TypeCheckError  # noqa: E402
from typechecker.parser import parse  # noqa: E402


def probe(src):
    try:
        typecheck_tree(parse(src))
        return True
    except Exception:
        return False


LITS = {"Int64": "1", "Float64": "1.5", "Bool": "true", "String": '"x"'}
METHODS = [
    "toString", "toInt64", "toFloat64", "toRune", "toBool", "size", "length",
    "len", "count", "ord", "unicode", "charAt", "get", "isDigit",
]
for stype, lit in LITS.items():
    for target in ["Int64", "Float64", "Bool", "String", "Rune"]:
        for m in METHODS:
            src = f'main(): Unit {{\n    let z: {target} = {lit}.{m}()\n    println(z)\n}}'
            if probe(src):
                print(f"{stype:8s} .{m}() -> {target:8s} OK")
    # property-style without parens
    for m in ["size", "length", "len", "count"]:
        src = f'main(): Unit {{\n    let z: Int64 = {lit}.{m}\n    println(z)\n}}'
        if probe(src):
            print(f"{stype:8s} .{m}   -> Int64     OK (property)")
