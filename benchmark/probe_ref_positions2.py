"""Get official checker error line:col AND map to token index.

The official GT semantics: first token whose including prefix cannot be
extended to a compilable program.  The checker's error position (line:col)
identifies the offending node; the GT token is the first token at/after that
position that cannot be continued (usually the token containing the position,
or the closing paren of the expression).
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
    {STMT}
}
"""
MARKER = "{STMT}"


def token_at(src, line, col):
    """Return token index whose byte span contains (line, col)."""
    ids = enc.encode(src)
    pos = 0
    starts = []
    for t in ids:
        starts.append(pos)
        pos += len(enc.decode_single_token_bytes(t))
    target = byte_offset(src, line, col)
    for i, s in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(src)
        if s <= target < end:
            return i, src[s:end]
    return None, None


def byte_offset(src, line, col):
    cur = 1
    for i, ch in enumerate(src):
        if cur == line:
            return i + max(col - 1, 0)
        if ch == "\n":
            cur += 1
    return len(src)


def probe(stmt):
    src = PAD.replace(MARKER, stmt)
    try:
        typecheck_tree(parse(src))
        return "ACCEPT"
    except TypeCheckError as e:
        msg = str(e).splitlines()[0]
        d = e.diagnostic
        if d is not None and d.line is not None:
            tok, txt = token_at(src, d.line, d.column)
            return f"{msg} @{d.line}:{d.column} tok#{tok} {txt!r}"
        return msg
    except Exception as e:  # ParseError etc.
        return f"{type(e).__name__}: {str(e).splitlines()[0]}"


cases = [
    "abs(1)",                      # Unit statement check position
    "abs(1) + 1",                  # compound statement, still non-Unit
    "abs(1).toString()",           # String result statement
    "st.contains(\"x\")",          # Bool result statement
    "println(1)",                  # Unit -> fine
    "xi + 1",                      # bare arithmetic
    "1",                           # bare literal
    "a.add(1)",                    # Unit -> fine
    'abs("bad")',                  # arg type error (calibration)
    "let y: Int64 = min(1, 2)",    # min assignment arity
    "let y: Int64 = min(1, 1, [1, 2])",  # min assignment
    "min(1, 2)",                   # min bare
    "min(1, 2, 3)",                # min bare 3 args
    "clamp(1.5, 0.5, 2.5)",        # valid call as statement (non-Unit)
    "min(1, 2, [3, 4])",
    "let z: String = min(1, 1, [1, 2])",
]
for c in cases:
    print(f"{c!r:40s} -> {probe(c)}")
