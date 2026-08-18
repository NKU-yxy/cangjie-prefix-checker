"""Probe official checker: does a user-defined VARIADIC generic bind T?
min/max (builtin) never bind T per Fix A; is that a variadic property or
a builtin property?"""
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
        return "ACCEPT"
    except TypeCheckError as e:
        return "REJECT " + str(e).splitlines()[0]
    except Exception as e:
        return f"{type(e).__name__}: {str(e).splitlines()[0]}"


MAIN = """
func main(): Unit {
    let o: Int64 = {CALL}
    println(o)
}
"""
cases = [
    ("user-variadic-ok", "func vg<T>(a: T, rest: T...): T {\n    a\n}\n", "vg(1, 2, 3)"),
    ("user-variadic-mixed", "func vg<T>(a: T, rest: T...): T {\n    a\n}\n", 'vg(1, 2, "x")'),
    ("user-variadic-one", "func vg<T>(a: T, rest: T...): T {\n    a\n}\n", "vg(1)"),
    ("user-nonvar-ok", "func nv<T>(a: T, b: T): T {\n    a\n}\n", "nv(1, 2)"),
    ("user-nonvar-mixed", "func nv<T>(a: T, b: T): T {\n    a\n}\n", 'nv(1, "x")'),
    ("user-nonvar-fn", "func nv<T>(a: T, b: T): T {\n    a\n}\n", "nv(1, { v: Int64 => v })"),
    ("builtin-min-ok", "", "min(1, 2)"),
    ("builtin-min-one", "", "min(1)"),
    ("builtin-min-last", "", "min(1, 2, 3)"),
]
for label, pre, call in cases:
    print(f"{label:20s} -> {probe(pre + MAIN.replace('{CALL}', call))}")
