"""Probe official checker on bare function-name / min / explicit-type statements.

Decides the GT anchor model for unrescuable statements:
- If bare function names are ACCEPTED mid-block, prefix `abs`/`min` is
  continuable (`abs; println("ok")` compiles) and the GT for bad calls
  anchors at the '(' instead of the name itself.
- Whether `min<Int64>(1, 2, [3, 4])` compiles decides if explicit type
  args rescue the generic call.
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
        return f"REJECT: {str(e).splitlines()[0]}"
    except Exception as e:
        return f"{type(e).__name__}: {str(e).splitlines()[0]}"


cases = [
    "abs",                                # bare fn name, LAST statement
    "abs\n    println(\"ok\")",           # bare fn name mid-block
    "min(1, 2, [3, 4])",                  # min LAST statement
    "min(1, 2, [3, 4])\n    println(\"ok\")",   # min mid-block
    "min<Int64>(1, 2, [3, 4])",           # explicit type args
    "min<Int64>(1, 2, [3, 4])\n    println(\"ok\")",
    "min",                                # bare min name LAST
    "min\n    println(\"ok\")",           # bare min name mid-block
    "abs(1) == 1",                        # Bool trailing expr
    "abs(1) + 1",                         # Int64 trailing expr (already known)
    "abs(1).toFloat64()",                 # Float64 trailing expr
    "abs(1)\n    println(\"ok\")",        # call mid-block (re-verify)
    "let y = abs(1)",                     # declaration w/ inferred var type
    "var y = abs(1)",
    "let y: Float64 = abs(1)",            # OK assignment
    "y = abs(1)",                         # hmm: y undefined here; skip in PAD
]
for c in cases:
    print(f"{c!r:44s} -> {probe(c)}")
