"""V15 Patch 5 smoke test: hard-commit call-close Dead synthesis.

All declarations use the `: Unit` annotation (the engine registers only
annotated top-level functions — established v12 behavior, corpus-consistent).

Checks:
  1. valid calls ending in ')' never fire (no new Dead);
  2. `if (...)` tails never fire (frontier classifies Value);
  3. a call whose every overload is eliminated fires at the committed ')'
     with rule v15-p5-call-close.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from generate_valid_prefix_corpus import PrefixScanner  # noqa: E402

CASES = [
    # (name, source, expect_fire, expect_rule)
    ("valid_call",
     "func g(x: Int64): Unit {}\nmain(): Unit { g(1) }\n",
     False, None),
    ("if_tail",
     "main(): Unit { let x = true; if (x) {} }\n",
     False, None),
    ("index_tail",
     "main(): Unit { let a = [1, 2]; let v = a[0]; }\n",
     False, None),
    ("dead_call_arg_type",
     "func g(x: Int64): Unit {}\nmain(): Unit { g(\"s\") }\n",
     True, "v15-p5-call-close"),
    ("dead_call_arity",
     "func g(x: Int64): Unit {}\nmain(): Unit { g() }\n",
     True, "v15-p5-call-close"),
    ("dead_call_expected_ret",
     "func f() -> Int64 { return 0 }\nmain(): Unit { let s: String = f() }\n",
     None, None),  # informational: let_initializer family
]


def main() -> int:
    scanner = PrefixScanner(str(ROOT / "solution"))
    failed = 0
    for name, src, expect, expect_rule in CASES:
        res = scanner.scan_ids(scanner.enc.encode(src), trace=True)
        fire = res["fire"]
        traces = res["traces"]
        msg = ""
        rule = ""
        frontier_end = None
        if traces:
            ev = traces[0]
            msg = ev.get("message", "") or ""
            rule = ev.get("rule", "") or ""
            frontier_end = ev.get("frontier_end")
        line = f"{name:26s} fire={fire!s:5s} rule={rule!s:26s} msg={msg[:60]!r}"
        print(line)
        if expect is not None:
            ok = (fire is not None) == expect
            if not ok:
                failed += 1
                print(f"  !! EXPECTED fire={expect} got fire={fire}")
            if expect and expect_rule is not None and rule != expect_rule:
                failed += 1
                print(f"  !! EXPECTED rule={expect_rule} got rule={rule}")
        if frontier_end is not None and fire is not None:
            cut = src[frontier_end:].split("\n")[0][:40]
            print(f"      frontier_end={frontier_end} suffix_head={cut!r}")
    print("SMOKE", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
