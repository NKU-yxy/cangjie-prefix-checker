# Vendored from the competition reference implementation:
# https://gitcode.com/bhzhan/cangjie-fragment-checker
# Not claimed as team-original code; provenance and adaptations are documented
# in ../README.md and the repository-level THIRD_PARTY_NOTICES.md.

"""CLI: ``cangjie-parse`` / ``python -m typechecker``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from typechecker.parser import UnexpectedCharacters, UnexpectedEOF, UnexpectedToken, parse_file


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Parse a Cangjie file with the contest-subset Lark grammar.")
    p.add_argument("path", type=Path, help="Path to a .cj file.")
    p.add_argument("--pretty", action="store_true", help="Print a pretty tree (Lark pretty).")
    args = p.parse_args(argv)
    try:
        tree = parse_file(args.path)
    except (UnexpectedCharacters, UnexpectedEOF, UnexpectedToken) as exc:
        print(exc, file=sys.stderr)
        return 1
    if args.pretty:
        print(tree.pretty())
    else:
        print(tree)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
