"""Probe official checker on declaration-RHS rescue continuations.

Decides the GT anchor model for declaration/reassignment RHS mismatches:
- Is the newline continuable? (`.getOrThrow()` / `.toString()` on the next line)
- Which rescue suffixes actually compile for which (rhs-type, target) pairs?
- Where does the official diagnostic point for the arg-error statement cases?
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
    let m: HashMap<String, Int64> = HashMap<String, Int64>()
    {STMT}
}
"""
MARKER = "{STMT}"


def probe(stmt, with_pos=False):
    src = PAD.replace(MARKER, stmt)
    try:
        typecheck_tree(parse(src))
        return "ACCEPT"
    except TypeCheckError as e:
        msg = str(e).splitlines()[0]
        d = e.diagnostic
        if with_pos and d is not None and d.line is not None:
            return f"{msg} @{d.line}:{d.column}"
        return msg
    except Exception as e:
        return f"{type(e).__name__}: {str(e).splitlines()[0]}"


# (a) newline continuability — RHS continued on the NEXT line
print("== newline continuation")
print(repr('let z: String = clamp(1.5, 0.5, 2.5)\n.toString()'), "->",
      probe('let z: String = clamp(1.5, 0.5, 2.5)\n    .toString()'))
print(repr('let z: Int64 = m.get("k")\n.getOrThrow()'), "->",
      probe('let z: Int64 = m.get("k")\n    .getOrThrow()'))

# (b) same-line rescue existence per (rhs-type, target)
print("== same-line rescues")
print("Int64->String  :", probe('let z: String = clamp(1.5, 0.5, 2.5).toString()'))
print("Float64->String:", probe('let z: String = clamp(1.5, 0.5, 2.5).toString()'))
print("Bool->Int64    :", probe('let z: Int64 = st.contains("x").toInt64()'))
print("Bool->String   :", probe('let z: String = st.contains("x").toString()'))
print("Optional->inner:", probe('let z: Int64 = m.get("k").getOrThrow()'))
print("Optional->Str  :", probe('let z: String = m.get("k").getOrThrow().toString()'))
print("String->Int64  :", probe('let z: Int64 = padGamma("ok").len()'))
print("Int64->Float64 :", probe('let z: Float64 = clamp(1.5, 0.5, 2.5).toFloat64()'))
print("Int64->Float64+:", probe('let z: Float64 = abs(1) + 0.5'))
print("Bool->String(atom):", probe('let z: String = true.toString()'))

# (c) diagnostic positions for the validated statement cases
print("== statement arg-error diagnostics")
print('a.add("x")     ->', probe('a.add("x")', with_pos=True))
print('st.contains(1) ->', probe('st.contains(1)', with_pos=True))
print('let flag: Int64 = true ->', probe('let flag: Int64 = true', with_pos=True))
print('let z: String = clamp(1.5, 0.5, 2.5) ->', probe('let z: String = clamp(1.5, 0.5, 2.5)', with_pos=True))
