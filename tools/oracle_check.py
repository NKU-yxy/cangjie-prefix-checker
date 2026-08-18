#!/usr/bin/env python3
"""Oracle: official Lark-based Cangjie typechecker (contest subset).

Usage: oracle_check.py <program.cj>

Exit 0 + "ACCEPT" when the whole program typechecks; exit 0 + "REJECT: ..."
when the checker raises (parse error or type error).  The official context is
selected with CANGJIE_TYPECHECKER_CONTEXT (default "final" here); the
typechecker package must be on PYTHONPATH (official-reference/typechecker).

This is the Patch 3 / Patch 5 "官方 typechecker 正向验证" oracle.
"""

import os
import sys

os.environ.setdefault("CANGJIE_TYPECHECKER_CONTEXT", "final")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typechecker.checker import typecheck_file  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: oracle_check.py <program.cj>", file=sys.stderr)
        return 2
    try:
        typecheck_file(sys.argv[1])
    except Exception as exc:  # parse or type error — the oracle REJECTs
        msg = str(exc).replace("\n", " ")
        print(f"REJECT: {type(exc).__name__}: {msg[:300]}")
        return 0
    print("ACCEPT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
