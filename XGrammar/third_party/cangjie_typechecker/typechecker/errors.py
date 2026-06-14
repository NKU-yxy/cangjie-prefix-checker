"""Structured diagnostics and exceptions for the typechecker package."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from lark import Token
from lark.tree import Tree


@dataclass(frozen=True)
class Diagnostic:
    """Machine-readable diagnostic payload carried by ``TypeCheckError``."""

    code: str
    phase: str
    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    source: Optional[str] = None

    def render(self) -> str:
        where = ""
        if self.line is not None and self.column is not None:
            where = f" ({self.line}:{self.column})"
        src = f" [{self.source}]" if self.source else ""
        return f"[{self.code}][{self.phase}] {self.message}{where}{src}"


def _loc_from_node(node: object) -> tuple[Optional[int], Optional[int]]:
    if isinstance(node, Token):
        return node.line, node.column
    if isinstance(node, Tree):
        meta = getattr(node, "meta", None)
        if meta is not None:
            return getattr(meta, "line", None), getattr(meta, "column", None)
    return None, None


def make_diagnostic(
    *,
    code: str,
    phase: str,
    message: str,
    node: object = None,
    source: Optional[str] = None,
) -> Diagnostic:
    line, column = _loc_from_node(node)
    return Diagnostic(code=code, phase=phase, message=message, line=line, column=column, source=source)


class TypeCheckError(Exception):
    """Raised when parsing of types, unification, or member resolution fails."""

    def __init__(self, message: str | Diagnostic, node: object = None) -> None:
        # Backward compatible path: existing sites pass ``TypeCheckError("msg", node)``.
        if isinstance(message, Diagnostic):
            diag = message
        else:
            diag = make_diagnostic(code="E_TYPECHECK", phase="check", message=message, node=node)
        self.diagnostic = diag
        super().__init__(diag.render())

    @classmethod
    def from_parts(
        cls,
        *,
        code: str,
        phase: str,
        message: str,
        node: object = None,
        source: Optional[str] = None,
    ) -> TypeCheckError:
        return cls(make_diagnostic(code=code, phase=phase, message=message, node=node, source=source))


class SyntaxError(TypeCheckError):
    """Raised for syntax/lowering shape violations after parsing."""

    def __init__(self, message: str | Diagnostic, node: object = None) -> None:
        if isinstance(message, Diagnostic):
            diag = message
        else:
            diag = make_diagnostic(code="E_SYNTAX", phase="syntax", message=message, node=node)
        super().__init__(diag)

    @classmethod
    def from_parts(
        cls,
        *,
        code: str,
        phase: str = "syntax",
        message: str,
        node: object = None,
        source: Optional[str] = None,
    ) -> SyntaxError:
        return cls(make_diagnostic(code=code, phase=phase, message=message, node=node, source=source))


def synth_error(code: str, message: str, node: object = None) -> TypeCheckError:
    return TypeCheckError.from_parts(code=code, phase="synth", message=message, node=node)


def check_error(code: str, message: str, node: object = None) -> TypeCheckError:
    return TypeCheckError.from_parts(code=code, phase="check", message=message, node=node)


def subtype_error(code: str, message: str, node: object = None) -> TypeCheckError:
    return TypeCheckError.from_parts(code=code, phase="subtype", message=message, node=node)


def decl_error(code: str, message: str, node: object = None) -> TypeCheckError:
    return TypeCheckError.from_parts(code=code, phase="decl", message=message, node=node)


def internal_error(code: str, message: str, node: object = None) -> TypeCheckError:
    return TypeCheckError.from_parts(code=code, phase="internal", message=message, node=node)


def syntax_error(code: str, message: str, node: object = None) -> SyntaxError:
    return SyntaxError.from_parts(code=code, phase="syntax", message=message, node=node)
