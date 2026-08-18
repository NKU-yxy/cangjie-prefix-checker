"""Precisely measure solution error token for global-function cases."""
import subprocess
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
    {STMT}
}
"""


def sol_gt(stmt):
    full = PAD.replace("{STMT}", stmt)
    ids = enc.encode(full)
    toks = [enc.decode_single_token_bytes(t).decode("utf-8", "replace") for t in ids]
    p = subprocess.run(
        ["./solution"], input="\n".join(str(t) for t in ids) + "\n",
        capture_output=True, text=True, timeout=10)
    out = p.stdout.strip().split()
    errs = [i for i, o in enumerate(out) if o == "1"]
    if not errs:
        return None, "ALL-0"
    i = errs[0]
    # token text at error: recover from cumulative source
    pos = 0
    starts = []
    for t in ids:
        starts.append(pos)
        pos += len(enc.decode_single_token_bytes(t))
    start = starts[i]
    end = starts[i + 1] if i + 1 < len(starts) else len(full)
    return i, repr(full[start:end])


cases = [
    "min(1, 2)",
    "min(1, 2, 3)",
    "min(1, 2, [3, 4])",
    'min("bad", 1, [1, 2])',
    "min(1, 1)",
    "min(1, 1, [1, 2], 1)",
    "let z: String = min(1, 1, [1, 2])",
    "min(1, 1, [1, 2])",
    'min(1, 1, ["x"])',
    "max(1.5, 2.5)",
    "max(1, 2, 3)",
    "max(1, 2)",
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
    "let y: Int64 = min(1, 1, [1, 2])",
    "min(1, 1, 2)",
    "let y: Int64 = min(1, 2)",
    "min(1, 1, 1, 1)",
    "max(1, 2, [3, 4])",
    "clamp(1.5, 0.5, 2.5)",
    "min(1.5, 2.5, [3.5])",
]
for c in cases:
    gt, txt = sol_gt(c)
    print(f"{c!r:38s} sol_gt={gt} {txt}")
