"""Unified AST/IR definitions for types, expressions, and declarations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Tuple, Union

from lark import Token
from lark.tree import Tree


Ty = Union[
    "TyPrim",
    "TyParam",
    "TyNominal",
    "TyTuple",
    "TyArrow",
]


@dataclass(frozen=True)
class TyPrim:
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class TyParam:
    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True)
class TyNominal:
    name: str
    args: tuple[Ty, ...] = ()

    def __str__(self) -> str:
        if not self.args:
            return self.name
        inner = ", ".join(str(a) for a in self.args)
        return f"{self.name}<{inner}>"


@dataclass(frozen=True)
class TyTuple:
    elems: tuple[Ty, ...]

    def __str__(self) -> str:
        return "(" + ", ".join(str(e) for e in self.elems) + ")"


@dataclass(frozen=True)
class TyArrow:
    params: tuple[Ty, ...]
    ret: Ty
    param_names: Optional[Tuple[Optional[str], ...]] = None

    def __str__(self) -> str:
        ps = ", ".join(str(p) for p in self.params)
        return f"({ps}) -> {self.ret}"


TY_RUNTIME_CLASSES = (TyPrim, TyParam, TyNominal, TyTuple, TyArrow)


def subst_ty(m: Mapping[str, Ty], t: Ty) -> Ty:
    if isinstance(t, TyParam):
        return m.get(t.name, t)
    if isinstance(t, TyNominal):
        return TyNominal(t.name, tuple(subst_ty(m, a) for a in t.args))
    if isinstance(t, TyTuple):
        return TyTuple(tuple(subst_ty(m, e) for e in t.elems))
    if isinstance(t, TyArrow):
        return TyArrow(
            tuple(subst_ty(m, p) for p in t.params),
            subst_ty(m, t.ret),
            t.param_names,
        )
    return t


PRIM: dict[str, TyPrim] = {
    n: TyPrim(n)
    for n in (
        "Int64",
        "Float64",
        "Bool",
        "Rune",
        "Unit",
    )
}

T_UNIT: Ty = PRIM["Unit"]
T_BOOL: Ty = PRIM["Bool"]
T_RUNE: Ty = PRIM["Rune"]
T_STRING: Ty = TyNominal("String", ())
T_INT64: Ty = PRIM["Int64"]


@dataclass(frozen=True)
class Expr:
    pass


@dataclass(frozen=True)
class BlockExpr(Expr):
    items: Tuple[Union["VarDeclExpr", Expr], ...]


@dataclass(frozen=True)
class VarDeclExpr(Expr):
    kind: str
    name: str
    annot_type_tree: Optional[Tree]
    init: Expr
    source_tree: Tree


@dataclass(frozen=True)
class NameExpr(Expr):
    token: Token


@dataclass(frozen=True)
class LiteralExpr(Expr):
    token: Token


@dataclass(frozen=True)
class PrimitiveTypeExpr(Expr):
    type_tree: Tree


@dataclass(frozen=True)
class TupleExpr(Expr):
    elems: Tuple[Expr, ...]


@dataclass(frozen=True)
class ArrayExpr(Expr):
    elems: Tuple[Expr, ...]


@dataclass(frozen=True)
class ReturnExpr(Expr):
    value: Optional[Expr]


@dataclass(frozen=True)
class BreakExpr(Expr):
    token: Token


@dataclass(frozen=True)
class ContinueExpr(Expr):
    token: Token


@dataclass(frozen=True)
class IfExpr(Expr):
    cond: Expr
    then_branch: Expr
    else_branch: Optional[Expr]


@dataclass(frozen=True)
class WhileExpr(Expr):
    cond: Expr
    body: BlockExpr


@dataclass(frozen=True)
class RangeExpr(Expr):
    lo: Expr
    hi: Expr
    op_token: Token
    step: Optional[Expr]


@dataclass(frozen=True)
class ForExpr(Expr):
    var_name: str
    rhs: Expr
    body: BlockExpr


@dataclass(frozen=True)
class LambdaParam:
    name: str
    param_tree: Tree


@dataclass(frozen=True)
class LambdaExpr(Expr):
    params: Tuple[LambdaParam, ...]
    body: Expr


@dataclass(frozen=True)
class AssignExpr(Expr):
    lhs: Expr
    rhs: Expr


@dataclass(frozen=True)
class UnaryExpr(Expr):
    op: Token
    operand: Expr


@dataclass(frozen=True)
class BinaryExpr(Expr):
    op: Token
    left: Expr
    right: Expr


@dataclass(frozen=True)
class NamedArg:
    name: str
    value: Expr


@dataclass(frozen=True)
class CallArgs:
    positional: Tuple[Expr, ...]
    named: Dict[str, Expr]


@dataclass(frozen=True)
class MemberSuffix:
    field_name: str
    type_args_tree: Optional[Tree]
    call_args: Optional[CallArgs]


@dataclass(frozen=True)
class IndexSuffix:
    index: Expr


@dataclass(frozen=True)
class CallSuffix:
    args: CallArgs


@dataclass(frozen=True)
class TypeArgsSuffix:
    type_args_tree: Tree


Suffix = Union[MemberSuffix, IndexSuffix, CallSuffix, TypeArgsSuffix]


@dataclass(frozen=True)
class PostfixExpr(Expr):
    primary: Expr
    suffixes: Tuple[Suffix, ...]


@dataclass
class FuncDecl:
    name: str
    type_params: Tuple[str, ...]
    param_names: Tuple[Optional[str], ...]
    param_types: Tuple[Ty, ...]
    ret: Ty
    body: Expr


@dataclass
class MethodDecl:
    name: str
    is_static: bool
    type_params: Tuple[str, ...]
    param_names: Tuple[Optional[str], ...]
    param_types: Tuple[Ty, ...]
    ret: Ty
    body: Expr


@dataclass(frozen=True)
class ConstructorDecl:
    param_names: Tuple[Optional[str], ...]
    param_types: Tuple[Ty, ...]
    body: Expr


@dataclass
class ClassDecl:
    name: str
    type_params: Tuple[str, ...]
    supers: List[TyNominal]
    fields: Dict[str, Ty]
    static_fields: Dict[str, Ty]
    methods: List[MethodDecl]
    constructors: Tuple[ConstructorDecl, ...]


@dataclass
class InterfaceDecl:
    name: str
    type_params: Tuple[str, ...]
    supers: List[TyNominal]
    methods: List[MethodDecl]


@dataclass(frozen=True)
class ProgramDecls:
    ordered_funcs: Tuple[FuncDecl, ...]
    ordered_class_names: Tuple[str, ...]
    funcs: Dict[str, List[FuncDecl]]
    classes: Dict[str, ClassDecl]
    interfaces: Dict[str, InterfaceDecl]
