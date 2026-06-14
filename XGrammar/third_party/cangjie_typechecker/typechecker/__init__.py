"""Cangjie contest-subset parser (Lark)."""

from typechecker.parser import get_parser, parse, parse_file
from typechecker.parser import strip_leading_package_and_import_lines

__all__ = ["get_parser", "parse", "parse_file", "strip_leading_package_and_import_lines"]
