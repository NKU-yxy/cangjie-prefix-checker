# Vendored from the competition reference implementation:
# https://gitcode.com/bhzhan/cangjie-fragment-checker
# Not claimed as team-original code; provenance and adaptations are documented
# in ../README.md and the repository-level THIRD_PARTY_NOTICES.md.

"""Lark ``Transformer``: type-syntax subtrees → internal ``Ty`` (see Lark docs on Transformers)."""

from __future__ import annotations

from typing import Tuple, Union

from lark import Token
from lark.tree import Tree
from lark.visitors import Transformer

from typechecker.ast import PRIM, TY_RUNTIME_CLASSES, Ty, TyArrow, TyNominal, TyParam, TyTuple
from typechecker.error_codes import (
    E_INTERNAL_UNKNOWN_SYNTAX_MESSAGE,
    E_SYNTAX_INTERNAL_TYPE_ARGS_RESULT,
    E_SYNTAX_INTERNAL_TYPE_ARGS_SHAPE,
    TYPE_SYNTAX_CODES,
)
from typechecker.errors import internal_error, syntax_error


_NO_FUNC_SUFFIX = object()

def _syntax(key: str, message: str, node: object = None):
    code = TYPE_SYNTAX_CODES.get(key)
    if code is None:
        raise internal_error(E_INTERNAL_UNKNOWN_SYNTAX_MESSAGE, f"unknown type syntax key: {key}")
    return syntax_error(code, message, node)


def _tok_ty(t: Token, tparams: set[str]) -> Ty:
    v = str(t.value)
    if t.type == "IDENT":
        if v in tparams:
            return TyParam(v)
        return TyNominal(v, ())
    if v in PRIM:
        return PRIM[v]
    raise _syntax("BAD_TYPE_TOKEN", f"bad type token {t}")


class TypeTransformer(Transformer):
    """Bottom-up conversion of Lark *type* rules to ``Ty``."""

    def __init__(self, tparams: set[str]) -> None:
        super().__init__()
        self.tparams = tparams

    def _coerce_ty(self, c: object) -> Ty | None:
        """Coerce transformed child nodes to ``Ty`` values."""

        if isinstance(c, Token):
            return _tok_ty(c, self.tparams)
        if isinstance(c, TY_RUNTIME_CLASSES):
            return c
        raise _syntax("UNEXPECTED_CHILD", f"unexpected child in type transform: {type(c).__name__}", c)

    def __default__(self, data: str, children: list, meta) -> Ty:
        raise _syntax("UNSUPPORTED_TYPE_RULE", f"unsupported type rule {data}", meta)

    def primitive_type(self, children: list) -> Ty:
        tok = children[0]
        name = str(tok.value)
        if name not in PRIM:
            raise _syntax("UNKNOWN_PRIMITIVE", f"unknown primitive {name}", tok)
        return PRIM[name]

    def simple_type(self, children: list) -> Ty:
        ident = children[0]
        assert isinstance(ident, Token) and ident.type == "IDENT"
        name = str(ident.value)
        args: Tuple[Ty, ...] = ()
        if len(children) > 1:
            extra = children[1]
            if not isinstance(extra, tuple) or not all(isinstance(x, TY_RUNTIME_CLASSES) for x in extra):
                raise syntax_error(E_SYNTAX_INTERNAL_TYPE_ARGS_SHAPE, "type_arguments must transform to tuple of Ty", ident)
            args = extra
        if name in self.tparams:
            if args:
                raise _syntax("TPARAM_TAKES_ARGS", "type parameter cannot take arguments here", ident)
            return TyParam(name)
        return TyNominal(name, args)

    def type_arguments(self, children: list) -> Tuple[Ty, ...]:
        out: list[Ty] = []
        for child in children:
            t = self._coerce_ty(child)
            if t is not None:
                out.append(t)
        return tuple(out)

    def expr_type_arguments(self, children: list) -> Tuple[Ty, ...]:
        return self.type_arguments(children)

    def func_suffix(self, children: list) -> object:
        if not children:
            return _NO_FUNC_SUFFIX
        ret = self._coerce_ty(children[0])
        if ret is None:
            raise _syntax("FUNC_MISSING_RET", "function type missing return after ->", children[0] if children else None)
        return ret

    def paren_type_form(self, children: list) -> Ty:
        if not children:
            raise _syntax("PAREN_MISSING_INNER", "parenthesized type without inner types", None)
        suffix = children[-1]
        param_nodes = children[:-1]
        param_types: list[Ty] = []
        for child in param_nodes:
            t = self._coerce_ty(child)
            if t is not None:
                param_types.append(t)
        if suffix is not _NO_FUNC_SUFFIX:
            if not isinstance(suffix, TY_RUNTIME_CLASSES):
                raise _syntax("FUNC_MISSING_RET", "function type missing return after ->", suffix)
            return TyArrow(tuple(param_types), suffix, tuple(None for _ in param_types))
        if len(param_types) == 1:
            return param_types[0]
        if len(param_types) >= 2:
            return TyTuple(tuple(param_types))
        raise _syntax("PAREN_MISSING_INNER", "parenthesized type without inner types", children[0])

    def paren_type(self, children: list) -> Ty:
        return self.paren_type_form(children)

    def tuple_type(self, children: list) -> Ty:
        return self.paren_type_form(children)

    def func_type(self, children: list) -> Ty:
        return self.paren_type_form(children)

    def type(self, children: list) -> Ty:
        if len(children) != 1:
            raise _syntax("TYPE_NODE_BAD_ARITY", "type node expected one child", children[0] if children else None)
        c0 = children[0]
        t = self._coerce_ty(c0)
        if t is not None:
            return t
        raise _syntax("TYPE_NODE_NOT_TY", "type node did not yield Ty", c0)


def parse_type(t: Union[Tree, Token], tparams: set[str]) -> Ty:
    """Convert a Lark *type* subtree (or bare type token) to ``Ty``."""

    if isinstance(t, Token):
        return _tok_ty(t, tparams)
    return TypeTransformer(tparams).transform(t)


def parse_wrapped_type(node: Tree, tparams: set[str]) -> Ty:
    """Handle optional ``type`` wrapper produced by some Lark inlines."""

    if node.data == "type":
        return parse_type(node.children[0], tparams)
    return parse_type(node, tparams)


def type_args_from_tree(ta: Tree, tparams: set[str]) -> Tuple[Ty, ...]:
    if ta.data not in ("type_arguments", "expr_type_arguments"):
        raise _syntax("TYPE_ARGS_WRAPPER_EXPECTED", "expected type_arguments or expr_type_arguments", ta)
    out = TypeTransformer(tparams).transform(ta)
    if not isinstance(out, tuple):
        raise syntax_error(E_SYNTAX_INTERNAL_TYPE_ARGS_RESULT, "type args transform must return tuple", ta)
    return out
