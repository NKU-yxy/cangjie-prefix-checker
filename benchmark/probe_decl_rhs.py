"""Probe official checker AND solution on declaration/reassignment RHS anchors.

Model under test (closure-anchoring): a declaration RHS type mismatch anchors
at the RHS expression's closure (atom -> itself, call -> ')') UNLESS a
type-fixing suffix rescue exists on the same line (e.g. .toString(),
.getOrThrow()), in which case the prefix stays extendable and the GT moves to
the newline / next statement.
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "/ref/typechecker")
import typechecker.builtin_context as bc  # noqa: E402

bc._CONTEXT_PATH = Path("/workspace/context.json")
bc._builtin_ctx_singleton = None
from typechecker.checker import typecheck_tree  # noqa: E402
from typechecker.errors import TypeCheckError  # noqa: E402
from typechecker.parser import parse  # noqa: E402

import tiktoken

enc = tiktoken.get_encoding("cl100k_base")

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


def token_at(src, line, col):
    ids = enc.encode(src)
    starts = []
    pos = 0
    for t in ids:
        starts.append(pos)
        pos += len(enc.decode_single_token_bytes(t))
    cur = 1
    target = 0
    for i, ch in enumerate(src):
        if cur == line:
            target = i + max(col - 1, 0)
            break
        if ch == "\n":
            cur += 1
    for i, s in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(src)
        if s <= target < end:
            return i, src[s:end]
    return None, None


def off_gt(stmt):
    src = PAD.replace(MARKER, stmt)
    try:
        typecheck_tree(parse(src))
        return "ACCEPT"
    except TypeCheckError as e:
        msg = str(e).splitlines()[0]
        d = e.diagnostic
        if d is not None and d.line is not None:
            tok, txt = token_at(src, d.line, d.column)
            return f"{msg} @tok#{tok} {txt!r}"
        return msg
    except Exception as e:
        return f"{type(e).__name__}: {str(e).splitlines()[0]}"


def sol_gt(stmt):
    full = PAD.replace(MARKER, stmt)
    ids = enc.encode(full)
    p = subprocess.run(
        ["./solution"], input="\n".join(str(t) for t in ids) + "\n",
        capture_output=True, text=True, timeout=10)
    out = p.stdout.strip().split()
    errs = [i for i, o in enumerate(out) if o == "1"]
    if not errs:
        return "ALL-0"
    i = errs[0]
    pos = 0
    starts = []
    for t in ids:
        starts.append(pos)
        pos += len(enc.decode_single_token_bytes(t))
    start = starts[i]
    end = starts[i + 1] if i + 1 < len(starts) else len(full)
    return f"err#{i} {full[start:end]!r}"


cases = [
    "let flag: Int64 = true",                    # atom RHS, no rescue (err_type_mismatch analog)
    "let flag: Int64 = 1.5",                     # atom RHS, rescue .toString()=String!=Int64
    "let z: String = clamp(1.5, 0.5, 2.5)",      # call RHS, rescue .toString() exists
    'let z: Int64 = st.contains("x")',           # call RHS Bool, no rescue
    'let z: String = st.contains("x")',          # call RHS Bool, rescue exists
    'let z: Int64 = m.get("k")',                 # optional RHS, rescue .getOrThrow() exists
    'let z: String = m.get("k")',                # optional RHS, rescue .getOrThrow().toString()
    "v = 1",                                     # reassign atom
    "v = clamp(1.5, 0.5, 2.5)",                  # reassign call RHS, rescue exists
    'let q: Int64 = st + "x"',                   # compound RHS, no rescue
    "let z: String = clamp(1.5, 0.5, 2.5).toString()",  # sanity: ACCEPT
    'let z: String = st.contains("x").toString()',      # sanity: ACCEPT
]
for c in cases:
    print(f"{c!r:50s} off={off_gt(c):42s} sol={sol_gt(c)}")
