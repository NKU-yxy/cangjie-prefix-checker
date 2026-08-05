# Vendored from the competition reference implementation:
# https://gitcode.com/bhzhan/cangjie-fragment-checker
# Not claimed as team-original code; provenance and adaptations are documented
# in ../README.md and the repository-level THIRD_PARTY_NOTICES.md.

"""Small formatting helpers for human-readable typing traces.

These functions intentionally keep trace output compact and stable so tests and
debugging output remain easy to scan.
"""

from __future__ import annotations

from lark import Token
from lark.tree import Tree

from typechecker.context_model import TypeContext
from typechecker.ast import Expr

def format_expr_hint(node: Expr | Token | Tree) -> str:
    """Return a short printable hint for an expression-like input.

    Args:
        node: Lowered expression node, token, or parse tree fragment to format.

    Returns:
        A compact human-readable string used in trace lines.
    """
    if isinstance(node, Token):
        v = repr(node.value)
        if len(v) > 32:
            v = v[:29] + "..."
        return f"{node.type}:{v}"
    if isinstance(node, Tree):
        return node.data
    return type(node).__name__


def format_gamma(ctx: TypeContext) -> str:
    """Render a compact snapshot of the current typing context.

    Args:
        ctx: Active typechecking context.

    Returns:
        A ``Γ[...]`` string containing the top variable layer and return type.
    """
    items = ", ".join(f"{k}: {v}" for k, v in sorted(ctx.layer.items()))
    return f"Γ[{items}; ret={ctx.ret}]"
