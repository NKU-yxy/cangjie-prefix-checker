"""Official GT (first non-continuable token) for declaration/reassignment RHS.

Uses the prefix oracle validated against wrong_error_positions.json:
GT = first prefix that the official checker rejects as a complete program.
Model under test: declaration RHS mismatches anchor at the RHS expression's
closure (atom -> itself, call -> ')', compound -> last token). No rescue
consideration: the checker evaluates the complete prefix as-is.
"""
import sys
import tiktoken

sys.path.insert(0, "benchmark")
from context_api_differential import _configure_oracle, oracle_accepts  # noqa: E402

_configure_oracle()
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


def gt_of(stmt):
    full = PAD.replace("{STMT}", stmt)
    ids = enc.encode(full)
    offsets = []
    pos = 0
    for t in ids:
        offsets.append(pos)
        pos += len(enc.decode_single_token_bytes(t))
    for k in range(len(ids)):
        ok, _ = oracle_accepts(full[:offsets[k]])
        if not ok:
            end = offsets[k + 1] if k + 1 < len(ids) else len(full)
            return k, repr(full[offsets[k]:end])
    return len(ids), "ACCEPT"


cases = [
    "let flag: Int64 = true",                    # atom RHS, no rescue (JSON GT=346=same shape)
    "let flag: Int64 = 1.5",                     # atom RHS
    "let z: String = clamp(1.5, 0.5, 2.5)",      # call RHS
    'let z: Int64 = st.contains("x")',           # call RHS Bool
    'let z: String = st.contains("x")',          # call RHS Bool
    'let z: Int64 = m.get("k")',                 # optional RHS
    'let z: String = m.get("k")',                # optional RHS
    "v = 1",                                     # reassign atom
    "v = clamp(1.5, 0.5, 2.5)",                  # reassign call RHS
    'let q: Int64 = st + "x"',                   # compound RHS (arith error)
    "let z: String = clamp(1.5, 0.5, 2.5).toString()",  # sanity: ACCEPT
    'let z: String = st.contains("x").toString()',      # sanity: ACCEPT
]
for c in cases:
    gt, nxt = gt_of(c)
    print(f"{c!r:50s} GT={gt:<4d} next={nxt}")
