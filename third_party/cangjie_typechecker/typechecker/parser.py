# Vendored from the competition reference implementation:
# https://gitcode.com/bhzhan/cangjie-fragment-checker
# Not claimed as team-original code; provenance and adaptations are documented
# in ../README.md and the repository-level THIRD_PARTY_NOTICES.md.

"""Parse phase: Cangjie source -> Lark ``ParseTree``.

Later phases: ``typechecker.decl_transformer.lower_program`` (declaration IR), then
``typechecker.checker.TypeChecker`` (semantic judgments).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re

from lark import Lark, ParseTree, UnexpectedCharacters, UnexpectedEOF, UnexpectedToken

_GRAMMAR_PATH = Path(__file__).resolve().parent / "cangjie.lark"
_HEADER_DIRECTIVE_RE = re.compile(r"^(package|import)\b")


@lru_cache(maxsize=8)
def get_parser(*, start: str = "start", _grammar_mtime_ns: int = 0) -> Lark:
    _ = _grammar_mtime_ns  # cache key so grammar edits pick up a new Lark instance
    return Lark.open(
        str(_GRAMMAR_PATH),
        rel_to=Path(__file__).resolve().parent,
        parser="lalr",
        lexer="contextual",
        start=start,
        propagate_positions=True,
        maybe_placeholders=False,
    )


def _mtime_key() -> int:
    return int(_GRAMMAR_PATH.stat().st_mtime_ns)


def strip_leading_package_and_import_lines(text: str) -> str:
    """Blank leading package/import/comment lines while preserving line count."""
    lines = text.splitlines(keepends=True)
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped == "" or stripped.startswith("//"):
            i += 1
            continue
        if _HEADER_DIRECTIVE_RE.match(stripped):
            i += 1
            continue
        break
    # Preserve line numbers for diagnostics by replacing stripped header lines
    # with blank lines instead of deleting them.
    for j in range(i):
        lines[j] = "\n" if lines[j].endswith("\n") else ""
    return "".join(lines)


def parse(text: str, *, start: str = "start", preprocess: bool = True) -> ParseTree:
    """Parse Cangjie source *text* and return the Lark parse tree.

    When *preprocess* is true (default), strip leading ``package`` / ``import`` lines
    before parsing.
    """
    if preprocess:
        text = strip_leading_package_and_import_lines(text)
    return get_parser(start=start, _grammar_mtime_ns=_mtime_key()).parse(text)


def parse_file(
    path: str | Path, *, encoding: str = "utf-8", start: str = "start", preprocess: bool = True
) -> ParseTree:
    """Parse a ``.cj`` file."""
    p = Path(path)
    return parse(p.read_text(encoding=encoding), start=start, preprocess=preprocess)


__all__ = [
    "get_parser",
    "parse",
    "parse_file",
    "strip_leading_package_and_import_lines",
    "UnexpectedCharacters",
    "UnexpectedEOF",
    "UnexpectedToken",
]
