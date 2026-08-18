"""Compute official ground-truth (first non-continuable token) for global-function cases.

The official GT is the first token whose prefix cannot be extended into a
fully compilable program; if the whole program compiles, GT == len(tokens).
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
            return k, full[offsets[k]:offsets[k] + 16]
    return len(ids), ""


cases = [
    "min(1, 2)",
    "min(1, 2, 3)",
    "min(1, 2, [3, 4])",
    'min("bad", 1, [1, 2])',
    "min(1, 1)",
    "min(1, 1, [1, 2], 1)",
    "let z: String = min(1, 1, [1, 2])",
    "min(1, 1, [1, 2])",
    "max(1.5, 2.5)",
    "println('a')",
    "println('a', 1)",
    'print("x", 1)',
    "print(1, true)",
    "abs(1)",
    "abs(1.5)",
    "clamp(1, 1.5, 1.5)",
    'clamp("bad", 1.5, 1.5)',
    'abs("bad")',
    "min(1.5, 2.5)",
    "max(1, 2)",
    "min(1.5, 2.5, 3.5)",
    "max(1, 2, 3)",
    "min(1, 1, 2)",
    "let y = min(1, 2)",
    "let y = min(1)",
    "let y = min(1, 1, 1, 1)",
    "let y: Int64 = min(1, 1, [1, 2])",
]
for c in cases:
    gt, nxt = gt_of(c)
    print(f"{c!r:42s} GT={gt:<4d} next={nxt!r}")
