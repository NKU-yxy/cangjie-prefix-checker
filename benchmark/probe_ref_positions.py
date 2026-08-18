"""Get official checker error POSITIONS (line:col) for key cases.

Reveals whether the official checker delays argument-type errors to the
closing paren or reports them at the offending literal itself.
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

PAD = """
func padAlpha(): Int64 {
    1
}

func padBeta(n: Int64): Int64 {
    n + padAlpha()
}

func padGamma(s: String): String {
    s
}

main(): Unit {
    var v: String = "x"
    let xi: Int64 = 1
    let xf: Float64 = 1.5
    let xb: Bool = true
    let a: ArrayList<Int64> = ArrayList<Int64>()
    let st: String = "hello"
    {STMT}
}
"""
MARKER = "{STMT}"


def probe(stmt):
    src = PAD.replace(MARKER, stmt)
    try:
        typecheck_tree(parse(src))
        return "ACCEPT"
    except TypeCheckError as e:
        return str(e)[:240]
    except Exception as e:  # ParseError etc.
        return f"{type(e).__name__}: {str(e).splitlines()[0]}"


cases = [
    'a.add("x")',
    "st.contains(1)",
    "abs(1)",
    "min(1, 2, [3, 4])",
    "min(1, 2)",
    "min(1, 2, 3)",
    'min("bad", 1, [1, 2])',
    "min(1, 1, [1, 2], 1)",
    "let z: String = min(1, 1, [1, 2])",
    'print("x", 1)',
    "print(1, true)",
    "clamp(1, 1.5, 1.5)",
    'clamp("bad", 1.5, 1.5)',
    'abs("bad")',
    "max(1, 2)",
    "min(1.5, 2.5)",
    "max(1, 2, 3)",
    "min(1, 1, 2)",
    "min(1.5, 2.5, [3.5])",
    "max(1, 2, [3, 4])",
    "min(1, 1, 1, 1)",
    "let y: Int64 = min(1, 2)",
]
for c in cases:
    print(f"{c!r:36s} -> {probe(c)}")
