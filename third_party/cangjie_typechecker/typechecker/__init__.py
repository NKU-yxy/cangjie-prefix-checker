# Vendored from the competition reference implementation:
# https://gitcode.com/bhzhan/cangjie-fragment-checker
# Not claimed as team-original code; provenance and adaptations are documented
# in ../README.md and the repository-level THIRD_PARTY_NOTICES.md.

"""Cangjie contest-subset parser (Lark)."""

from typechecker.parser import get_parser, parse, parse_file
from typechecker.parser import strip_leading_package_and_import_lines

__all__ = ["get_parser", "parse", "parse_file", "strip_leading_package_and_import_lines"]
