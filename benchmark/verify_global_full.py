"""Verify official accept/reject for full global-function programs."""
import sys

sys.path.insert(0, "benchmark")
from context_api_differential import _configure_oracle, oracle_accepts  # noqa: E402

_configure_oracle()
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

cases = [
    "min(1, 2)",
    "min(1, 2, 3)",
    "min(1, 2, [3, 4])",
    "min(1, 1)",
    "min(1, 1, [1, 2], 1)",
    "let z: String = min(1, 1, [1, 2])",
    "println('a')",
    "println('a', 1)",
    "abs(1)",
    "print(1, true)",
    'print("x", 1)',
    "let r: Rune = 'a'",
    "let r: Rune = 'ab'",
    'min(1, 1, ["x"])',
    "let y: Int64 = min(1, 1, [1, 2])",
    "max(1, 2)",
    "min(1.5, 2.5)",
    "min(1, 1, 2)",
    "let y = min(1, 1, [1, 2])",
]
for c in cases:
    ok, msg = oracle_accepts(PAD.replace("{STMT}", c))
    print(f"{c!r:38s} -> {'ACCEPT' if ok else msg.splitlines()[0]}")
