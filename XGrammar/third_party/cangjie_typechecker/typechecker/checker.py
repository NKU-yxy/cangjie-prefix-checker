"""Semantic phase: type judgments over lowered declarations and expression AST.

Parse -> lower -> typecheck:
- **Parse**: ``typechecker.parser``
- **Lower**: ``typechecker.decl_transformer.lower_program`` builds ``ast.ProgramDecls``
- **Typecheck**: this module (``TypeContext`` / ``TypeChecker``, rules per ``typing-rules.md``)

Expression synthesis/checking rules live in this module and operate on lowered
expression nodes from ``typechecker.ast``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

from lark import Token
from lark.tree import Tree

from typechecker.ast import (
    ArrayExpr,
    AssignExpr,
    BinaryExpr,
    BlockExpr,
    BreakExpr,
    CallArgs,
    CallSuffix,
    ClassDecl,
    ConstructorDecl,
    ContinueExpr,
    Expr,
    ForExpr,
    FuncDecl,
    IfExpr,
    IndexSuffix,
    InterfaceDecl,
    LambdaExpr,
    LiteralExpr,
    MemberSuffix,
    MethodDecl,
    NameExpr,
    PostfixExpr,
    PrimitiveTypeExpr,
    PRIM,
    ProgramDecls,
    RangeExpr,
    ReturnExpr,
    T_BOOL,
    T_INT64,
    T_RUNE,
    T_STRING,
    T_UNIT,
    TupleExpr,
    Ty,
    TyArrow,
    TyNominal,
    TyParam,
    TyPrim,
    TyTuple,
    TypeArgsSuffix,
    UnaryExpr,
    VarDeclExpr,
    WhileExpr,
    subst_ty,
)
from typechecker.builtin_context import MethodEntry, Sig
from typechecker.context_model import TypeContext
from typechecker.error_codes import E_CHECK_NO_MATCHING_CTOR
from typechecker.decl_transformer import lower_program, parse_type_after_colon
from typechecker.errors import TypeCheckError, check_error, decl_error, internal_error, subtype_error, synth_error
from typechecker.parser import parse_file
from typechecker.trace_fmt import format_expr_hint, format_gamma
from typechecker.type_inference import TypeInference
from typechecker.type_services import Service
from typechecker.type_transformer import parse_wrapped_type, type_args_from_tree

_REL_OPS: FrozenSet[str] = frozenset({"LESSTHAN", "MORETHAN", "LE", "GE"})
_EQ_OPS: FrozenSet[str] = frozenset({"EQEQ", "NE"})
_LOGICAL_OPS: FrozenSet[str] = frozenset({"OROR", "ANDAND"})
_ARITHMETIC_OPS: FrozenSet[str] = frozenset({"PLUS", "MINUS", "STAR", "SLASH"})
_MOD_OPS: FrozenSet[str] = frozenset({"PERCENT"})


@dataclass(frozen=True)
class OverloadSet:
    variants: Tuple[Sig, ...]


@dataclass(frozen=True)
class CallCandidate:
    sig: Sig


def _arrow_from_sig(s: Sig) -> TyArrow:
    return TyArrow(s.param_types, s.ret, s.param_names)


def _string_literal_scalar_count(token_text: str) -> Optional[int]:
    """Return Unicode scalar count for a ``STRING`` token body, or ``None`` if not a plain literal."""
    if len(token_text) < 2 or token_text[0] != '"' or token_text[-1] != '"':
        return None
    body = token_text[1:-1]
    if "${" in body:
        return None
    count = 0
    i = 0
    while i < len(body):
        if body[i] == "\\":
            if i + 1 >= len(body):
                return None
            count += 1
            i += 2
            continue
        count += 1
        i += 1
    return count


class TypeChecker:
    def __init__(self, *, trace: bool = False) -> None:
        self.funcs: Dict[str, List[FuncDecl]] = {}
        self.classes: Dict[str, ClassDecl] = {}
        self.interfaces: Dict[str, InterfaceDecl] = {}
        self._trace_enabled = trace
        self._trace_lines: List[str] = []
        self.services = Service(self)
        self.type_inference = TypeInference(self.services)
        self.builtin_ctx = self.services.builtin_ctx
        self._builtins: Dict[str, List[Sig]] = self.services.builtins

    def _trace(self, line: str) -> None:
        if self._trace_enabled:
            self._trace_lines.append(line)

    # --- subtyping (see ``typing-rules.md``; sections match rule groups) ---

    def is_subtype(self, a: Ty, b: Ty) -> bool:
        return self.services.is_subtype(a, b)

    # --- expression judgments ---

    def synth_operand(self, x: object, ctx: TypeContext) -> Ty:
        if isinstance(x, Expr):
            return self.synth_expr(x, ctx)
        if isinstance(x, Token):
            if x.type == "IDENT":
                return self.synth_expr(NameExpr(x), ctx)
            if x.type in ("INTEGER", "FLOAT", "TRUE", "FALSE", "STRING"):
                return self.synth_expr(LiteralExpr(x), ctx)
        raise TypeCheckError(f"unsupported synth_operand input: {type(x)}")

    def check_expr(self, e: Expr, ctx: TypeContext, want: Ty) -> None:
        if self._trace_enabled:
            self._trace(f"{format_gamma(ctx)} |- check({format_expr_hint(e)}) <= {want}")
        if isinstance(e, LambdaExpr):
            self._check_lambda(e, ctx, want)
            return
        if isinstance(e, ReturnExpr):
            self._check_return(e, ctx, want)
            return
        if isinstance(e, BreakExpr):
            self._check_break(e, ctx, want)
            return
        if isinstance(e, ContinueExpr):
            self._check_continue(e, ctx, want)
            return
        if isinstance(e, IfExpr):
            self._check_if(e, ctx, want)
            return
        if isinstance(e, WhileExpr):
            self._check_while(e, ctx, want)
            return
        if isinstance(e, ForExpr):
            self._check_for(e, ctx, want)
            return
        if isinstance(e, RangeExpr):
            self._check_range(e, ctx, want)
            return
        if isinstance(e, NameExpr):
            self._check_name(e, ctx, want)
            return
        if isinstance(want, TyNominal) and want.name == "Array" and len(want.args) == 1 and isinstance(e, ArrayExpr):
            self._check_array_elements(e, ctx, want.args[0])
            return
        if isinstance(e, LiteralExpr) and e.token.type == "STRING":
            self._check_string_literal(e, ctx, want)
            return
        got = self._synth_postfix(e, ctx, expected=want) if isinstance(e, PostfixExpr) else self.synth_expr(e, ctx)
        self._require_subtype(got, want, ctx)

    def _check_string_literal(self, e: LiteralExpr, ctx: TypeContext, want: Ty) -> None:
        if want == T_STRING:
            return
        if want == T_RUNE:
            n = _string_literal_scalar_count(str(e.token.value))
            if n == 1:
                return
            raise check_error(
                "E_CHECK_STRING_LITERAL_NOT_SINGLE_RUNE",
                "string literal for Rune must contain exactly one character",
                e.token,
            )
        got = self._synth_literal(e)
        self._require_subtype(got, want, ctx)

    def _check_return(self, e: ReturnExpr, ctx: TypeContext, want: Ty) -> None:
        _ = want
        self._synth_return(e, ctx)

    def _check_break(self, e: BreakExpr, ctx: TypeContext, want: Ty) -> None:
        _ = want
        self._synth_break(e, ctx)

    def _check_continue(self, e: ContinueExpr, ctx: TypeContext, want: Ty) -> None:
        _ = want
        self._synth_continue(e, ctx)

    def _check_array_elements(self, e: ArrayExpr, ctx: TypeContext, elem_ty: Ty) -> None:
        for elem in e.elems:
            self.check_expr(elem, ctx, elem_ty)

    def _has_lambda_param_annotation(self, lam_param_tree_children: tuple[object, ...]) -> bool:
        return len(lam_param_tree_children) > 1

    def _check_lambda(self, lam: LambdaExpr, ctx: TypeContext, want: Ty) -> None:
        if not isinstance(want, TyArrow):
            raise check_error("E_CHECK_LAMBDA_NEEDS_ARROW", "lambda needs function type")
        if len(want.params) != len(lam.params):
            raise check_error("E_CHECK_LAMBDA_ARITY", "lambda arity mismatch")
        lay: Dict[str, Ty] = {}
        for p, wt in zip(lam.params, want.params):
            has_annot = self._has_lambda_param_annotation(tuple(p.param_tree.children))
            pannot = parse_type_after_colon(tuple(p.param_tree.children), ctx.tparams) if has_annot else None
            if pannot is not None:
                self._require_subtype(wt, pannot, ctx)
            lay[p.name] = pannot or wt
        inner = ctx.push_layer(lay)
        if isinstance(lam.body, BlockExpr):
            self.check_block(lam.body, inner, want.ret)
        else:
            self.check_expr(lam.body, inner, want.ret)

    def _synth_lambda(self, lam: LambdaExpr, ctx: TypeContext) -> TyArrow:
        lay: Dict[str, Ty] = {}
        names: list[str] = []
        params: list[Ty] = []
        for p in lam.params:
            has_annot = self._has_lambda_param_annotation(tuple(p.param_tree.children))
            if not has_annot:
                raise synth_error("E_SYNTH_LAMBDA_NEEDS_PARAM_TYPES", "lambda params must be annotated for synthesis")
            pty = parse_type_after_colon(tuple(p.param_tree.children), ctx.tparams)
            lay[p.name] = pty
            names.append(p.name)
            params.append(pty)
        inner = ctx.push_layer(lay)
        if isinstance(lam.body, BlockExpr):
            ret = self._synth_block(lam.body, inner)
        else:
            ret = self.synth_expr(lam.body, inner)
        return TyArrow(tuple(params), ret, tuple(names))

    def _require_subtype(self, got: Ty, expect: Ty, ctx: TypeContext) -> None:
        if self._trace_enabled:
            self._trace(f"{format_gamma(ctx)} |- {got} <= {expect}")
        if not self.services.is_subtype(got, expect):
            raise subtype_error("E_SUBTYPE_MISMATCH", f"expected {expect}, got {got}")

    def _synth_block(self, e: BlockExpr, ctx: TypeContext) -> Ty:
        inner = ctx.enter_block()
        if not e.items:
            return T_UNIT
        for x in e.items[:-1]:
            if isinstance(x, VarDeclExpr):
                inner = self._var_decl(x, inner)
            else:
                self.synth_expr(x, inner)
        last = e.items[-1]
        if isinstance(last, VarDeclExpr):
            inner = self._var_decl(last, inner)
            return T_UNIT
        return self.synth_expr(last, inner)

    def synth_expr(self, e: Expr, ctx: TypeContext) -> Ty:
        if isinstance(e, BlockExpr):
            return self._synth_block(e, ctx)
        if isinstance(e, IfExpr):
            ty = self._synth_if(e, ctx)
        elif isinstance(e, WhileExpr):
            ty = self._synth_while(e, ctx)
        elif isinstance(e, ForExpr):
            ty = self._synth_for(e, ctx)
        elif isinstance(e, LambdaExpr):
            ty = self._synth_lambda(e, ctx)
        elif isinstance(e, PrimitiveTypeExpr):
            ty = self._synth_type_expr(e, ctx)
        elif isinstance(e, AssignExpr):
            ty = self._synth_assignment(e, ctx)
        elif isinstance(e, UnaryExpr):
            ty = self._synth_unary(e, ctx)
        elif isinstance(e, BinaryExpr):
            ty = self._synth_binary(e, ctx)
        elif isinstance(e, TupleExpr):
            ty = self._synth_tuple(e, ctx)
        elif isinstance(e, ArrayExpr):
            ty = self._synth_array(e, ctx)
        elif isinstance(e, LiteralExpr):
            ty = self._synth_literal(e)
        elif isinstance(e, ReturnExpr):
            ty = self._synth_return(e, ctx)
        elif isinstance(e, BreakExpr):
            ty = self._synth_break(e, ctx)
        elif isinstance(e, ContinueExpr):
            ty = self._synth_continue(e, ctx)
        elif isinstance(e, NameExpr):
            ty = self._synth_name(e, ctx)
        elif isinstance(e, PostfixExpr):
            ty = self._synth_postfix(e, ctx)
        elif isinstance(e, RangeExpr):
            ty = self._synth_range(e, ctx)
        else:
            raise synth_error("E_SYNTH_UNSUPPORTED_EXPR", f"cannot synth {type(e).__name__}")
        if self._trace_enabled:
            self._trace(f"{format_gamma(ctx)} |- synth({format_expr_hint(e)}) => {ty}")
        return ty

    def _synth_block_or_expr(self, n: Expr, ctx: TypeContext) -> Ty:
        if isinstance(n, BlockExpr):
            return self._synth_block(n, ctx)
        return self.synth_expr(n, ctx)

    def _check_block_or_expr(self, n: Expr, ctx: TypeContext, want: Ty) -> None:
        if isinstance(n, BlockExpr):
            self.check_block(n, ctx, want)
        else:
            self.check_expr(n, ctx, want)

    def _synth_if(self, e: IfExpr, ctx: TypeContext) -> Ty:
        self.check_expr(e.cond, ctx, T_BOOL)
        if e.else_branch is None:
            self._synth_block_or_expr(e.then_branch, ctx)
            return T_UNIT
        t1 = self._synth_block_or_expr(e.then_branch, ctx)
        t2 = self._synth_block_or_expr(e.else_branch, ctx)
        j = self.services.join_types(t1, t2)
        if j is None:
            raise synth_error("E_SYNTH_IF_NO_COMMON_SUPERTYPE", f"if branches cannot be joined: {t1} vs {t2}")
        return j

    def _check_if(self, e: IfExpr, ctx: TypeContext, want: Ty) -> None:
        self.check_expr(e.cond, ctx, T_BOOL)
        if e.else_branch is None:
            self._check_block_or_expr(e.then_branch, ctx, T_UNIT)
            self._require_subtype(T_UNIT, want, ctx)
            return
        self._check_block_or_expr(e.then_branch, ctx, want)
        self._check_block_or_expr(e.else_branch, ctx, want)

    def _synth_while(self, e: WhileExpr, ctx: TypeContext) -> Ty:
        self.check_expr(e.cond, ctx, T_BOOL)
        self.check_block(e.body, ctx.enter_loop(), T_UNIT)
        return T_UNIT

    def _check_while(self, e: WhileExpr, ctx: TypeContext, want: Ty) -> None:
        self.check_expr(e.cond, ctx, T_BOOL)
        self.check_block(e.body, ctx.enter_loop(), T_UNIT)
        self._require_subtype(T_UNIT, want, ctx)

    def _for_element_type(self, e: ForExpr, ctx: TypeContext) -> Ty:
        rt = self.synth_expr(e.rhs, ctx)
        elem = self.type_inference.infer_iterable_element(rt)
        if elem is None:
            raise synth_error("E_SYNTH_NOT_ITERABLE", f"not iterable: {rt}")
        return elem

    def _synth_for(self, e: ForExpr, ctx: TypeContext) -> Ty:
        elem = self._for_element_type(e, ctx)
        inner = ctx.enter_loop().push_layer({e.var_name: elem})
        self.check_block(e.body, inner, T_UNIT)
        return T_UNIT

    def _check_for(self, e: ForExpr, ctx: TypeContext, want: Ty) -> None:
        elem = self._for_element_type(e, ctx)
        inner = ctx.enter_loop().push_layer({e.var_name: elem})
        self.check_block(e.body, inner, T_UNIT)
        self._require_subtype(T_UNIT, want, ctx)

    def _synth_unary(self, e: UnaryExpr, ctx: TypeContext) -> Ty:
        if e.op.type == "MINUS":
            t = self.synth_expr(e.operand, ctx)
            if not self._is_signed_arithmetic_type(t):
                raise synth_error(
                    "E_SYNTH_UNARY_MINUS_NON_ARITHMETIC",
                    f"unary '-' requires Int64 or Float64 operand, got {t}",
                )
            return t
        if e.op.value == "!":
            self.check_expr(e.operand, ctx, T_BOOL)
            return T_BOOL
        raise synth_error("E_SYNTH_UNSUPPORTED_EXPR", f"unsupported unary operator {e.op!r}")

    def _synth_type_expr(self, e: PrimitiveTypeExpr, ctx: TypeContext) -> Ty:
        return parse_wrapped_type(e.type_tree, ctx.tparams)

    def _synth_assignment(self, e: AssignExpr, ctx: TypeContext) -> Ty:
        lt = self._synth_assignable(e.lhs, ctx)
        self.check_expr(e.rhs, ctx, lt)
        return T_UNIT

    def _synth_binary(self, e: BinaryExpr, ctx: TypeContext) -> Ty:
        if e.op.type in _LOGICAL_OPS:
            self.check_expr(e.left, ctx, T_BOOL)
            self.check_expr(e.right, ctx, T_BOOL)
            return T_BOOL
        if e.op.type in _EQ_OPS:
            lt = self.synth_expr(e.left, ctx)
            rt = self.synth_expr(e.right, ctx)
            if self.services.join_types(lt, rt) is None:
                raise synth_error("E_SYNTH_EQ_INCOMPARABLE", f"operands not comparable: {lt} and {rt}")
            return T_BOOL
        if e.op.type in _REL_OPS:
            lt = self.synth_expr(e.left, ctx)
            rt = self.synth_expr(e.right, ctx)
            if not (self._is_numeric_type(lt) and self._is_numeric_type(rt)):
                raise synth_error("E_SYNTH_REL_UNORDERED", f"relational operator requires numeric operands, got {lt} and {rt}")
            if not self.services.types_equivalent(lt, rt):
                raise synth_error("E_SYNTH_REL_MIXED_NUMERIC_FAMILY", f"relational operands must share numeric family: {lt} and {rt}")
            return T_BOOL
        if e.op.type in _ARITHMETIC_OPS:
            if e.op.type == "PLUS":
                lt = self.synth_expr(e.left, ctx)
                rt = self.synth_expr(e.right, ctx)
                if lt == T_STRING and rt == T_STRING:
                    return T_STRING
            return self._synth_arithmetic_binary(e.left, e.right, ctx)
        if e.op.type in _MOD_OPS:
            return self._synth_mod_binary(e.left, e.right, ctx)
        raise synth_error("E_SYNTH_UNSUPPORTED_EXPR", f"cannot synth binary op {e.op.type}")

    def _synth_array(self, e: ArrayExpr, ctx: TypeContext) -> Ty:
        if not e.elems:
            raise synth_error("E_SYNTH_EMPTY_ARRAY_NEEDS_EXPECTED", "empty array literal requires expected Array<T> type")
        elem_types = [self.synth_expr(ex, ctx) for ex in e.elems]
        joined = elem_types[0]
        for t in elem_types[1:]:
            j = self.services.join_types(joined, t)
            if j is None:
                raise synth_error(
                    "E_SYNTH_ARRAY_ELEMENT_JOIN",
                    f"array element types cannot be joined: {joined} and {t}",
                )
            joined = j
        return TyNominal("Array", (joined,))

    def _synth_tuple(self, e: TupleExpr, ctx: TypeContext) -> Ty:
        return TyTuple(tuple(self.synth_expr(c, ctx) for c in e.elems))

    def _synth_literal(self, e: LiteralExpr) -> Ty:
        c0 = e.token
        if c0.type in ("TRUE", "FALSE"):
            return T_BOOL
        if c0.type == "STRING":
            return T_STRING
        if c0.type == "INTEGER":
            return T_INT64
        if c0.type == "FLOAT":
            return PRIM["Float64"]
        raise synth_error("E_SYNTH_BAD_OPERAND", f"bad literal {c0}")

    def _synth_return(self, e: ReturnExpr, ctx: TypeContext) -> Ty:
        if e.value is None:
            self._require_subtype(T_UNIT, ctx.ret, ctx)
        else:
            self.check_expr(e.value, ctx, ctx.ret)
        return T_UNIT

    def _synth_break(self, e: BreakExpr, ctx: TypeContext) -> Ty:
        if not ctx.in_loop:
            raise synth_error("E_SYNTH_BREAK_OUTSIDE_LOOP", "break used outside loop")
        return T_UNIT

    def _synth_continue(self, e: ContinueExpr, ctx: TypeContext) -> Ty:
        if not ctx.in_loop:
            raise synth_error("E_SYNTH_CONTINUE_OUTSIDE_LOOP", "continue used outside loop")
        return T_UNIT

    def _synth_name(self, e: NameExpr, ctx: TypeContext) -> Ty:
        return self._synth_name_token(e.token, ctx)

    def _check_name(self, e: NameExpr, ctx: TypeContext, want: Ty) -> None:
        nm = str(e.token.value)
        v = ctx.lookup_var(nm)
        if v is not None:
            self._require_subtype(v, want, ctx)
            return
        got = self._resolve_name_after_var(nm, e.token, ctx)
        self._require_subtype(got, want, ctx)

    def _lookup_class_method_type(self, cd: ClassDecl, nm: str) -> Optional[Ty]:
        msub = {p: TyParam(p) for p in cd.type_params}
        mds = [md for md in cd.methods if md.name == nm]
        return self._method_types_from_decls(mds, msub)

    def _user_function_type(self, nm: str) -> Optional[Ty | OverloadSet]:
        fds = self.funcs.get(nm)
        if not fds:
            return None
        if len(fds) == 1:
            fd = fds[0]
            if not fd.type_params:
                return TyArrow(fd.param_types, fd.ret, fd.param_names)
            return OverloadSet((Sig(fd.type_params, fd.param_names, fd.param_types, fd.ret),))
        return OverloadSet(tuple(Sig(fd.type_params, fd.param_names, fd.param_types, fd.ret) for fd in fds))

    def _builtin_function_type(self, nm: str) -> Optional[Ty | OverloadSet]:
        bs = self._builtins.get(nm)
        if not bs:
            return None
        if len(bs) == 1:
            return _arrow_from_sig(bs[0])
        return OverloadSet(tuple(bs))

    def _resolve_name_after_var(self, nm: str, tok: Token, ctx: TypeContext) -> Ty:
        if ctx.class_decl is not None:
            member = self._lookup_class_method_type(ctx.class_decl, nm)
            if member is not None:
                if self._trace_enabled:
                    self._trace(f"{format_gamma(ctx)} |- ident {nm} => {member} (class method)")
                return member
        out = self._user_function_type(nm)
        if out is not None:
            if self._trace_enabled:
                self._trace(f"{format_gamma(ctx)} |- ident {nm} => {out}")
            return out  # type: ignore[return-value]
        out = self._builtin_function_type(nm)
        if out is not None:
            if self._trace_enabled:
                self._trace(f"{format_gamma(ctx)} |- ident {nm} => {out}")
            return out  # type: ignore[return-value]
        if nm in self.classes:
            cd = self.classes[nm]
            ty = TyNominal(nm, tuple(TyParam(p) for p in cd.type_params))
            if self._trace_enabled:
                self._trace(f"{format_gamma(ctx)} |- ident {nm} => {ty}")
            return ty
        if nm in self.builtin_ctx.nominal_names():
            ty = TyNominal(nm, ())
            if self._trace_enabled:
                self._trace(f"{format_gamma(ctx)} |- ident {nm} => {ty}")
            return ty
        if nm in self.interfaces:
            raise synth_error("E_SYNTH_INTERFACE_AS_VALUE", f"{nm} is interface, not value", tok)
        raise synth_error("E_SYNTH_UNKNOWN_NAME", f"unknown name {nm}", tok)

    def _synth_range(self, e: RangeExpr, ctx: TypeContext) -> Ty:
        lo = self.synth_expr(e.lo, ctx)
        hi = self.synth_expr(e.hi, ctx)
        if not self._is_integral_type(lo) or not self._is_integral_type(hi):
            raise synth_error("E_SYNTH_RANGE_NON_INTEGRAL", f"range endpoints must be integral, got {lo} and {hi}")
        if not self.services.types_equivalent(lo, hi):
            raise synth_error("E_SYNTH_RANGE_MIXED_FAMILY", f"range endpoints must share integral family: {lo} and {hi}")
        if e.step is not None:
            st = self.synth_expr(e.step, ctx)
            if not self._is_integral_type(st):
                raise synth_error("E_SYNTH_RANGE_BAD_STEP", f"range step must be integral, got {st}")
            if not self.services.types_equivalent(lo, st):
                raise synth_error("E_SYNTH_RANGE_BAD_STEP", f"range step must share endpoint family: {st} vs {lo}")
        return TyNominal("Range", (lo,))

    def _check_range(self, e: RangeExpr, ctx: TypeContext, want: Ty) -> None:
        if not isinstance(want, TyNominal) or want.name != "Range" or len(want.args) != 1:
            raise check_error("E_CHECK_RANGE_EXPECTED", f"expected Range<T>, got {want}")
        elem = want.args[0]
        self.check_expr(e.lo, ctx, elem)
        self.check_expr(e.hi, ctx, elem)
        if e.step is not None:
            self.check_expr(e.step, ctx, elem)

    def _is_numeric_type(self, t: Ty) -> bool:
        return isinstance(t, TyPrim) and t.name in {"Int64", "Float64", "Rune"}

    def _is_signed_arithmetic_type(self, t: Ty) -> bool:
        return isinstance(t, TyPrim) and t.name in {"Int64", "Float64"}

    def _is_integral_type(self, t: Ty) -> bool:
        return isinstance(t, TyPrim) and t.name in {"Int64", "Rune"}

    def _synth_arithmetic_binary(self, left: Expr, right: Expr, ctx: TypeContext) -> Ty:
        lt = self.synth_expr(left, ctx)
        rt = self.synth_expr(right, ctx)
        if not (self._is_signed_arithmetic_type(lt) and self._is_signed_arithmetic_type(rt)):
            raise synth_error(
                "E_SYNTH_ARITH_NON_ARITHMETIC",
                f"arithmetic operator requires Int64 or Float64 operands, got {lt} and {rt}",
            )
        if not self.services.types_equivalent(lt, rt):
            raise synth_error(
                "E_SYNTH_ARITH_MIXED_FAMILY",
                f"arithmetic operands must share type: {lt} and {rt}",
            )
        return lt

    def _synth_mod_binary(self, left: Expr, right: Expr, ctx: TypeContext) -> Ty:
        lt = self.synth_expr(left, ctx)
        rt = self.synth_expr(right, ctx)
        if lt != T_INT64 or rt != T_INT64:
            raise synth_error(
                "E_SYNTH_MOD_NON_INT64",
                f"'%' requires Int64 operands, got {lt} and {rt}",
            )
        return T_INT64

    def _synth_name_token(self, tok: Token, ctx: TypeContext) -> Ty:
        nm = str(tok.value)
        v = ctx.lookup_var(nm)
        if v is not None:
            if self._trace_enabled:
                self._trace(f"{format_gamma(ctx)} |- ident {nm} => {v}")
            return v
        return self._resolve_name_after_var(nm, tok, ctx)

    def _synth_assignable(self, lhs: Expr, ctx: TypeContext) -> Ty:
        if isinstance(lhs, NameExpr):
            return self._synth_name_token(lhs.token, ctx)
        if isinstance(lhs, PostfixExpr):
            return self._synth_postfix(lhs, ctx)
        raise check_error("E_CHECK_BAD_ASSIGNABLE", "bad assignable")

    def _validate_type_arg_arity(self, name: str, required: int, provided: Tuple[Ty, ...]) -> None:
        if len(provided) != required:
            raise check_error(
                "E_DECL_TYPE_ARITY_MISMATCH",
                f"{name} expects {required} type argument(s), got {len(provided)}",
            )

    def _instantiate_nominal_with_type_args(self, ty: TyNominal, targs: Tuple[Ty, ...]) -> TyNominal:
        required = self._declared_type_arity(ty.name)
        if required is None:
            raise synth_error("E_SYNTH_TYPE_ARGS_NON_NOMINAL", "type args on non-nominal")
        self._validate_type_arg_arity(ty.name, required, targs)
        return TyNominal(ty.name, targs)

    def _explicit_type_args_for_nominal_call(self, ty: TyNominal) -> Optional[Tuple[Ty, ...]]:
        cd = self.classes.get(ty.name)
        if cd is not None and cd.type_params:
            self._validate_type_arg_arity(ty.name, len(cd.type_params), ty.args)
            return ty.args
        return None

    def _synth_postfix(self, e: PostfixExpr, ctx: TypeContext, expected: Optional[Ty] = None) -> Ty:
        ty: object = self.synth_expr(e.primary, ctx)
        type_member = self._is_class_type_primary(e.primary, ctx)
        pending_explicit: Optional[Tuple[Ty, ...]] = None
        for idx, suffix in enumerate(e.suffixes):
            is_last = idx == len(e.suffixes) - 1
            if isinstance(suffix, MemberSuffix):
                ty = self._resolve_member(ty, suffix.field_name, ctx, type_member=type_member and idx == 0)
                member_explicit = pending_explicit
                if suffix.type_args_tree is not None:
                    member_explicit = type_args_from_tree(suffix.type_args_tree, ctx.tparams)
                if suffix.call_args is not None:
                    ty = self._apply_call(
                        ty,
                        suffix.call_args,
                        ctx,
                        expected if is_last else None,
                        explicit_type_args=member_explicit,
                    )
                    pending_explicit = None
                elif member_explicit is not None:
                    pending_explicit = member_explicit
                continue
            if isinstance(suffix, IndexSuffix):
                self.check_expr(suffix.index, ctx, T_INT64)
                ty = self._index_result(ty)
                continue
            if isinstance(suffix, CallSuffix):
                call_explicit = pending_explicit
                if isinstance(ty, TyNominal):
                    nominal_explicit = self._explicit_type_args_for_nominal_call(ty)
                    if nominal_explicit is not None:
                        call_explicit = nominal_explicit
                    else:
                        call_explicit = None
                ty = self._apply_call(
                    ty,
                    suffix.args,
                    ctx,
                    expected if is_last else None,
                    explicit_type_args=call_explicit,
                )
                pending_explicit = None
                continue
            if isinstance(suffix, TypeArgsSuffix):
                targs = type_args_from_tree(suffix.type_args_tree, ctx.tparams)
                if isinstance(ty, TyNominal):
                    ty = self._instantiate_nominal_with_type_args(ty, targs)
                    pending_explicit = targs
                elif isinstance(ty, (OverloadSet, TyArrow)):
                    pending_explicit = targs
                else:
                    raise synth_error("E_SYNTH_TYPE_ARGS_NON_NOMINAL", "type args on non-generic callee")
                continue
            raise synth_error("E_SYNTH_BAD_SUFFIX", "bad suffix")
        if isinstance(ty, OverloadSet):
            raise synth_error(
                "E_SYNTH_AMBIGUOUS_OVERLOADED_MEMBER",
                "ambiguous overloaded member reference; add a call or explicit disambiguation",
            )
        if not isinstance(ty, (TyArrow, TyNominal, TyParam, TyPrim, TyTuple)):
            raise synth_error("E_SYNTH_POSTFIX_NOT_TYPE", "postfix did not yield a type")
        return ty

    def _index_result(self, ty: Ty) -> Ty:
        if isinstance(ty, TyNominal) and ty.name in ("Array", "ArrayList") and ty.args:
            return ty.args[0]
        raise check_error("E_CHECK_BAD_INDEX_TARGET", f"cannot index {ty}")

    def _is_class_type_primary(self, primary: Expr, ctx: TypeContext) -> bool:
        if not isinstance(primary, NameExpr):
            return False
        nm = str(primary.token.value)
        if ctx.lookup_var(nm) is not None:
            return False
        if nm in self.interfaces:
            return False
        return nm in self.classes or nm in self.builtin_ctx.nominal_names()

    def _is_interface_nominal(self, ty: TyNominal) -> bool:
        return ty.name in self.interfaces or ty.name in self.builtin_ctx.interface_names()

    def _nominal_type_subst(self, type_params: Tuple[str, ...], ty: TyNominal) -> Dict[str, Ty]:
        return {p: arg for p, arg in zip(type_params, ty.args)}

    def _method_types_from_decls(self, mds: List[MethodDecl], msub: Dict[str, Ty]) -> Optional[Ty | OverloadSet]:
        sigs = [
            Sig(
                md.type_params,
                md.param_names,
                tuple(subst_ty(msub, t) for t in md.param_types),
                subst_ty(msub, md.ret),
            )
            for md in mds
        ]
        if not sigs:
            return None
        if len(sigs) == 1:
            sig = sigs[0]
            if not sig.type_params:
                return _arrow_from_sig(sig)
            return OverloadSet((sig,))
        return OverloadSet(tuple(sigs))

    def _method_type_from_entry(self, ent: MethodEntry) -> Ty | OverloadSet:
        if isinstance(ent, list):
            return OverloadSet(tuple(ent))
        return _arrow_from_sig(ent)

    def _transitive_supers(self, ty: TyNominal) -> List[TyNominal]:
        out: List[TyNominal] = []
        seen: set[str] = set()
        stack = list(self.services._declared_nominal_supers(ty))
        while stack:
            sup = stack.pop(0)
            key = str(sup)
            if key in seen:
                continue
            seen.add(key)
            out.append(sup)
            stack.extend(self.services._declared_nominal_supers(sup))
        return out

    def _declared_instance_methods_on_nominal(self, ty: TyNominal, field: str) -> Optional[Ty | OverloadSet]:
        idecl = self.interfaces.get(ty.name)
        if idecl is not None:
            msub = self._nominal_type_subst(idecl.type_params, ty)
            mds = [md for md in idecl.methods if md.name == field]
            return self._method_types_from_decls(mds, msub)
        table = self.builtin_ctx.interface_methods(ty)
        if table and field in table:
            return self._method_type_from_entry(table[field])
        cd = self.classes.get(ty.name)
        if cd is not None:
            msub = self._nominal_type_subst(cd.type_params, ty)
            mds = [md for md in cd.methods if not md.is_static and md.name == field]
            got = self._method_types_from_decls(mds, msub)
            if got is not None:
                return got
        inst = self.builtin_ctx.nominal_instance_methods(ty)
        if inst and field in inst:
            ent = inst[field]
            if isinstance(ent, list):
                return OverloadSet(tuple(ent))
            if not ent.param_types and field in ("first", "last"):
                return ent.ret
            return _arrow_from_sig(ent)
        return None

    def _resolve_interface_member(self, ty: TyNominal, field: str) -> Optional[Ty | OverloadSet]:
        got = self._declared_instance_methods_on_nominal(ty, field)
        if got is not None:
            return got
        for sup in self._transitive_supers(ty):
            got = self._declared_instance_methods_on_nominal(sup, field)
            if got is not None:
                return got
        return None

    def _resolve_instance_member(self, ty: TyNominal, field: str) -> Optional[Ty | OverloadSet]:
        cd = self.classes.get(ty.name)
        if cd is not None:
            msub = self._nominal_type_subst(cd.type_params, ty)
            if field in cd.fields:
                return subst_ty(msub, cd.fields[field])
        bf = self.builtin_ctx.nominal_fields(ty).get(field)
        if bf is not None:
            return bf
        got = self._declared_instance_methods_on_nominal(ty, field)
        if got is not None:
            return got
        for sup in self._transitive_supers(ty):
            got = self._declared_instance_methods_on_nominal(sup, field)
            if got is not None:
                return got
        return None

    def _resolve_type_member(self, ty: TyNominal, field: str) -> Optional[Ty | OverloadSet]:
        cd = self.classes.get(ty.name)
        if cd is not None:
            msub = self._nominal_type_subst(cd.type_params, ty)
            if field in cd.static_fields:
                return subst_ty(msub, cd.static_fields[field])
            mds = [md for md in cd.methods if md.is_static and md.name == field]
            got = self._method_types_from_decls(mds, msub)
            if got is not None:
                return got
        sf = self.builtin_ctx.nominal_static_fields(ty.name).get(field)
        if sf is not None:
            return sf
        tab = self.builtin_ctx.nominal_static_methods(ty)
        if tab and field in tab:
            return _arrow_from_sig(tab[field])
        return None


    def _resolve_member(self, ty: object, field: str, ctx: TypeContext, *, type_member: bool = False) -> Ty:
        if isinstance(ty, TyPrim) and field == "toString" and ty.name in {"Int64", "Float64", "Bool", "Rune"}:
            return TyArrow((), T_STRING)
        if isinstance(ty, TyNominal) and ty.name == "String" and field == "toString":
            return TyArrow((), T_STRING)
        if not isinstance(ty, TyNominal):
            raise synth_error("E_SYNTH_NO_MEMBER", f"no member {field} on {ty}")
        if type_member:
            got = self._resolve_type_member(ty, field)
        elif self._is_interface_nominal(ty):
            got = self._resolve_interface_member(ty, field)
        else:
            got = self._resolve_instance_member(ty, field)
        if got is None:
            raise synth_error("E_SYNTH_NO_MEMBER", f"no member {field} on {ty}")
        return got  # type: ignore[return-value]

    def _apply_call(
        self,
        callee: object,
        args: CallArgs,
        ctx: TypeContext,
        expected: Optional[Ty] = None,
        *,
        explicit_type_args: Optional[Tuple[Ty, ...]] = None,
    ) -> Ty:
        if self._trace_enabled:
            self._trace(f"{format_gamma(ctx)} |- call callee={callee}")
        candidates = self._resolve_call_candidates(callee)
        if candidates:
            return self._select_call_candidate(candidates, args, ctx, expected, explicit_type_args=explicit_type_args)
        raise synth_error("E_SYNTH_NOT_CALLABLE", f"not callable {callee}")

    def _resolve_call_candidates(self, callee: object) -> List[CallCandidate]:
        """Resolve callable candidates in deterministic implementation order.

        Candidate ordering policy (used by `_select_call_candidate`):
        1. Overload-set variants, in source/declaration order.
        2. Direct arrow callee as a single candidate.
        3. Nominal constructors:
           - builtin constructors first (table order),
           - otherwise user constructors (declaration order).

        Selection then tries candidates left-to-right and picks the first
        candidate whose application typechecks.
        """
        candidates: List[CallCandidate] = []
        if isinstance(callee, OverloadSet):
            for sig in callee.variants:
                candidates.append(CallCandidate(sig))
            return candidates
        if isinstance(callee, TyArrow):
            names = callee.param_names or tuple(f"a{i}" for i in range(len(callee.params)))
            candidates.append(CallCandidate(Sig((), names, callee.params, callee.ret)))
            return candidates
        if isinstance(callee, TyNominal):
            builtin_ctors = self.builtin_ctx.nominal_ctors(callee) or []
            for sig in builtin_ctors:
                candidates.append(CallCandidate(sig))
            if candidates:
                return candidates
            cd = self.classes.get(callee.name)
            if cd is not None:
                if not cd.constructors:
                    candidates.append(CallCandidate(Sig((), (), (), callee)))
                    return candidates
                for ctor in cd.constructors:
                    candidates.append(CallCandidate(self._sig_from_constructor(ctor, cd)))
            return candidates
        return candidates

    def _apply_call_candidate(
        self,
        candidate: CallCandidate,
        args: CallArgs,
        ctx: TypeContext,
        expected: Optional[Ty],
        *,
        explicit_type_args: Optional[Tuple[Ty, ...]] = None,
    ) -> Ty:
        return self._apply_sig(candidate.sig, args, ctx, expected, explicit_type_args=explicit_type_args)

    def _select_call_candidate(
        self,
        candidates: List[CallCandidate],
        args: CallArgs,
        ctx: TypeContext,
        expected: Optional[Ty],
        *,
        explicit_type_args: Optional[Tuple[Ty, ...]] = None,
    ) -> Ty:
        """Select the first candidate whose call application typechecks.

        If none matches, report diagnostics for every tried candidate.
        """
        failures: list[tuple[CallCandidate, TypeCheckError]] = []
        for candidate in candidates:
            try:
                return self._apply_call_candidate(
                    candidate,
                    args,
                    ctx,
                    expected,
                    explicit_type_args=explicit_type_args,
                )
            except TypeCheckError as err:
                failures.append((candidate, err))
        if failures:
            details = "\n".join(
                f"candidate[{idx}] {self._format_candidate_signature(candidate.sig)} -> {err}"
                for idx, (candidate, err) in enumerate(failures, start=1)
            )
            raise check_error(
                E_CHECK_NO_MATCHING_CTOR,
                f"no matching call candidate ({len(candidates)} tried); failures:\n{details}",
            )
        raise check_error(E_CHECK_NO_MATCHING_CTOR, "no matching call candidate")

    @staticmethod
    def _format_candidate_signature(sig: Sig) -> str:
        params = ", ".join(str(t) for t in sig.param_types)
        return f"({params}) -> {sig.ret}"

    def _sig_from_constructor(self, c: ConstructorDecl, cd: ClassDecl) -> Sig:
        return Sig(
            cd.type_params,
            c.param_names,
            c.param_types,
            TyNominal(cd.name, tuple(TyParam(x) for x in cd.type_params)),
        )

    def _apply_sig(
        self,
        sig: Sig,
        args: CallArgs,
        ctx: TypeContext,
        expected: Optional[Ty] = None,
        *,
        explicit_type_args: Optional[Tuple[Ty, ...]] = None,
    ) -> Ty:
        return self.type_inference.apply_sig(
            sig,
            args,
            ctx,
            synth_expr=self.synth_expr,
            check_expr=self.check_expr,
            expected_ret=expected,
            explicit_type_args=explicit_type_args,
        )

    # --- checking ---

    def check_program(self, prog: Tree) -> None:
        decls = self._stage_lower_declarations(prog)
        self._stage_load_declarations(decls)
        self._stage_check_declarations()
        self._stage_check_bodies(decls)

    def _stage_lower_declarations(self, prog: Tree) -> ProgramDecls:
        return lower_program(prog)

    def _stage_load_declarations(self, decls: ProgramDecls) -> None:
        self.funcs = decls.funcs
        self.classes = decls.classes
        self.interfaces = decls.interfaces

    def _stage_check_declarations(self) -> None:
        self._validate_declared_supertypes()
        self._validate_signature_wf()

    def _stage_check_bodies(self, decls: ProgramDecls) -> None:
        for fd in decls.ordered_funcs:
            self._trace(f"check func {fd.name} : {fd.ret}")
            ctx = TypeContext.for_function(fd)
            self.check_block(fd.body, ctx, fd.ret)
        for cname in decls.ordered_class_names:
            self._trace(f"check class {cname}")
            self._check_class(self.classes[cname])

    def _validate_signature_wf(self) -> None:
        for overloads in self.funcs.values():
            for fd in overloads:
                self._validate_type_params_unique(fd.type_params, f"function {fd.name}")
                self._validate_named_params(fd.param_names, fd.param_types, f"function {fd.name}")
                self._validate_types_wf(fd.param_types, set(fd.type_params), f"function {fd.name} parameter")
                self._validate_type_wf(fd.ret, set(fd.type_params), f"function {fd.name} return type")
        for cd in self.classes.values():
            self._validate_nominal_decl_name(cd.name, f"class {cd.name}")
            class_tparams = set(cd.type_params)
            self._validate_type_params_unique(cd.type_params, f"class {cd.name}")
            for field_name, field_ty in cd.fields.items():
                self._validate_type_wf(field_ty, class_tparams, f"class {cd.name} field {field_name}")
            for field_name, field_ty in cd.static_fields.items():
                self._validate_type_wf(field_ty, class_tparams, f"class {cd.name} static field {field_name}")
            for ctor in cd.constructors:
                self._validate_named_params(ctor.param_names, ctor.param_types, f"class {cd.name} constructor")
                self._validate_types_wf(ctor.param_types, class_tparams, f"class {cd.name} constructor parameter")
            for md in cd.methods:
                self._validate_method_signature_wf(md, class_tparams, f"class {cd.name} method {md.name}")
        for idecl in self.interfaces.values():
            self._validate_nominal_decl_name(idecl.name, f"interface {idecl.name}")
            iface_tparams = set(idecl.type_params)
            self._validate_type_params_unique(idecl.type_params, f"interface {idecl.name}")
            for md in idecl.methods:
                self._validate_method_signature_wf(md, iface_tparams, f"interface {idecl.name} method {md.name}")

    def _validate_method_signature_wf(self, md: MethodDecl, ambient_tparams: Set[str], where: str) -> None:
        self._validate_type_params_unique(md.type_params, where)
        self._validate_named_params(md.param_names, md.param_types, where)
        method_tparams = set(ambient_tparams)
        method_tparams.update(md.type_params)
        self._validate_types_wf(md.param_types, method_tparams, f"{where} parameter")
        self._validate_type_wf(md.ret, method_tparams, f"{where} return type")

    def _validate_types_wf(self, types: Tuple[Ty, ...], tparams: Set[str], where: str) -> None:
        for idx, ty in enumerate(types):
            self._validate_type_wf(ty, tparams, f"{where} {idx}")

    def _validate_type_wf(self, ty: Ty, tparams: Set[str], where: str) -> None:
        if isinstance(ty, TyPrim):
            return
        if isinstance(ty, TyParam):
            if ty.name not in tparams:
                raise decl_error("E_DECL_UNKNOWN_TYPE_PARAM", f"{where}: unknown type parameter {ty.name}")
            return
        if isinstance(ty, TyTuple):
            for idx, elem in enumerate(ty.elems):
                self._validate_type_wf(elem, tparams, f"{where} tuple[{idx}]")
            return
        if isinstance(ty, TyArrow):
            for idx, pty in enumerate(ty.params):
                self._validate_type_wf(pty, tparams, f"{where} param[{idx}]")
            self._validate_type_wf(ty.ret, tparams, f"{where} return")
            return
        if isinstance(ty, TyNominal):
            self._validate_nominal_type_wf(ty, tparams, where)
            return
        raise decl_error("E_DECL_UNKNOWN_TYPE_NODE", f"{where}: unsupported type node {type(ty).__name__}")

    def _validate_nominal_type_wf(self, ty: TyNominal, tparams: Set[str], where: str) -> None:
        arity = self._declared_type_arity(ty.name)
        if arity is None:
            raise decl_error("E_DECL_UNKNOWN_TYPE_NAME", f"{where}: unknown type {ty.name}")
        if len(ty.args) != arity:
            raise decl_error(
                "E_DECL_TYPE_ARITY_MISMATCH",
                f"{where}: type {ty.name} expects {arity} type argument(s), got {len(ty.args)}",
            )
        for idx, arg in enumerate(ty.args):
            self._validate_type_wf(arg, tparams, f"{where}<{idx}>")

    def _declared_type_arity(self, name: str) -> Optional[int]:
        cd = self.classes.get(name)
        if cd is not None:
            return len(cd.type_params)
        idecl = self.interfaces.get(name)
        if idecl is not None:
            return len(idecl.type_params)
        nom_arity = self.builtin_ctx.nominal_type_param_arity(name)
        if nom_arity is not None:
            return nom_arity
        iface_arity = self.builtin_ctx.interface_type_param_arity(name)
        if iface_arity is not None:
            return iface_arity
        return None

    def _validate_nominal_decl_name(self, name: str, where: str) -> None:
        if name in PRIM:
            raise decl_error(
                "E_DECL_TYPE_NAME_CONFLICTS_WITH_PRIMITIVE",
                f"{where}: type name {name} conflicts with primitive spelling",
            )

    def _validate_type_params_unique(self, names: Tuple[str, ...], where: str) -> None:
        seen: Set[str] = set()
        for name in names:
            if name in PRIM:
                raise decl_error(
                    "E_DECL_TYPE_PARAM_CONFLICTS_WITH_PRIMITIVE",
                    f"{where}: type parameter {name} conflicts with primitive spelling",
                )
            if name in seen:
                raise decl_error("E_DECL_DUPLICATE_TYPE_PARAM", f"{where}: duplicate type parameter {name}")
            seen.add(name)

    def _validate_named_params(self, names: Tuple[Optional[str], ...], types: Tuple[Ty, ...], where: str) -> None:
        if len(names) != len(types):
            raise decl_error("E_DECL_PARAM_SHAPE", f"{where}: parameter name/type length mismatch")
        seen: Set[str] = set()
        for name in names:
            if name is None:
                continue
            if name in seen:
                raise decl_error("E_DECL_DUPLICATE_PARAM_NAME", f"{where}: duplicate parameter name {name}")
            seen.add(name)

    def _check_class(self, cd: ClassDecl) -> None:
        for ctor in cd.constructors:
            self._check_constructor(cd, ctor)
        for m in cd.methods:
            params_layer = {n: t for n, t in zip(m.param_names, m.param_types) if n}
            ctx = TypeContext.for_class_method(cd, m).push_layer(params_layer)
            self.check_block(m.body, ctx, m.ret)

    def _validate_declared_supertypes(self) -> None:
        builtin_nominals = self.builtin_ctx.nominal_names()
        builtin_interfaces = self.builtin_ctx.interface_names()
        for cd in self.classes.values():
            class_supers = 0
            for sup in cd.supers:
                if sup.name in self.classes or sup.name in builtin_nominals:
                    class_supers += 1
                    continue
                if sup.name in self.interfaces or sup.name in builtin_interfaces:
                    continue
                raise decl_error("E_DECL_UNKNOWN_SUPERTYPE", f"class {cd.name} has unknown supertype {sup.name}")
            if class_supers > 1:
                raise decl_error(
                    "E_DECL_CLASS_MULTIPLE_SUPERCLASSES",
                    f"class {cd.name} has multiple superclass declarations",
                )
            self._validate_class_interface_methods(cd)
        for idecl in self.interfaces.values():
            for sup in idecl.supers:
                if sup.name in self.interfaces or sup.name in builtin_interfaces:
                    continue
                raise decl_error(
                    "E_DECL_UNKNOWN_SUPERTYPE",
                    f"interface {idecl.name} has unknown supertype {sup.name}",
                )

    def _validate_class_interface_methods(self, cd: ClassDecl) -> None:
        for sup in cd.supers:
            idecl = self.interfaces.get(sup.name)
            if idecl is None:
                continue
            subst = {tp: arg for tp, arg in zip(idecl.type_params, sup.args)}
            for required in idecl.methods:
                found = [m for m in cd.methods if not m.is_static and m.name == required.name]
                if not found:
                    raise decl_error(
                        "E_DECL_INTERFACE_METHOD_MISSING",
                        f"class {cd.name} does not implement {sup.name}.{required.name}",
                    )
                if not any(self._method_matches_interface(m, required, subst) for m in found):
                    raise decl_error(
                        "E_DECL_INTERFACE_METHOD_MISMATCH",
                        f"class {cd.name} method {required.name} does not match interface {sup.name}",
                    )

    def _method_matches_interface(self, got: MethodDecl, required: MethodDecl, subst: Dict[str, Ty]) -> bool:
        if len(got.param_types) != len(required.param_types):
            return False
        req_params = tuple(subst_ty(subst, t) for t in required.param_types)
        req_ret = subst_ty(subst, required.ret)
        if not all(self.services.types_equivalent(a, b) for a, b in zip(got.param_types, req_params)):
            return False
        return self.services.types_equivalent(got.ret, req_ret)

    def _check_constructor(self, cd: ClassDecl, c: ConstructorDecl) -> None:
        body = c.body
        if not isinstance(body, BlockExpr):
            raise internal_error("E_INTERNAL_AST_SHAPE", "constructor body must be BlockExpr")
        ctx = TypeContext.for_constructor(cd, c)
        self.check_block(body, ctx, T_UNIT)

    # --- blocks / expressions ---

    def check_block(self, b: BlockExpr, ctx: TypeContext, want: Ty) -> None:
        elems = list(b.items)
        if not elems:
            if self._trace_enabled:
                self._trace(f"{format_gamma(ctx)} |- {T_UNIT} <= {want}")
            if not self.services.is_subtype(T_UNIT, want):
                raise subtype_error("E_SUBTYPE_MISMATCH", f"expected {want}, got {T_UNIT}")
            return
        inner = ctx.enter_block()
        for e in elems[:-1]:
            if isinstance(e, VarDeclExpr):
                inner = self._var_decl(e, inner)
            else:
                self.synth_expr(e, inner)
        last = elems[-1]
        if isinstance(last, VarDeclExpr):
            inner = self._var_decl(last, inner)
            if self._trace_enabled:
                self._trace(f"{format_gamma(inner)} |- {T_UNIT} <= {want}")
            if not self.services.is_subtype(T_UNIT, want):
                raise subtype_error("E_SUBTYPE_MISMATCH", f"expected {want}, got {T_UNIT}")
        else:
            self.check_expr(last, inner, want)

    def _var_decl(self, n: VarDeclExpr, ctx: TypeContext) -> TypeContext:
        vn = n.name
        if n.annot_type_tree is None:
            raise check_error("E_CHECK_VAR_DECL_MISSING_ANNOT", f"variable declaration '{vn}' requires type annotation")
        ty = parse_wrapped_type(n.annot_type_tree, ctx.tparams)
        self.check_expr(n.init, ctx, ty)
        return ctx.with_binding(vn, ty)


def typecheck_file(path: str, *, trace: bool = False) -> Optional[list[str]]:
    tree = parse_file(path)
    return typecheck_tree(tree, trace=trace)


def typecheck_tree(tree: Tree, *, trace: bool = False) -> Optional[list[str]]:
    chk = TypeChecker(trace=trace)
    chk.check_program(tree)
    if trace:
        return list(chk._trace_lines)
    return None
