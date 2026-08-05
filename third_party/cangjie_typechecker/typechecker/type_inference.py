# Vendored from the competition reference implementation:
# https://gitcode.com/bhzhan/cangjie-fragment-checker
# Locally adapted for offline validation; not claimed as team-original code.
# See ../README.md and the repository-level THIRD_PARTY_NOTICES.md.

"""Generic call inference (separate synth/check paths)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from typechecker.builtin_context import Sig
from typechecker.context_model import TypeContext
from typechecker.error_codes import (
    E_CHECK_ARG_MISMATCH,
    E_CHECK_CONFLICTING_INFERENCE,
    E_CHECK_INFERENCE_CONSTRAINT_MISMATCH,
    E_CHECK_INFERENCE_RETURN_MISMATCH,
    E_CHECK_TOO_MANY_POSITIONAL_ARGS,
    E_CHECK_UNKNOWN_NAMED_ARG,
    E_INTERNAL_UNCONSUMED_NAMED_ARGS,
)
from typechecker.errors import TypeCheckError, check_error, internal_error
from typechecker.ast import CallArgs, Expr, Ty, TyArrow, TyNominal, TyParam, TyPrim, TyTuple, subst_ty
from typechecker.trace_fmt import format_gamma

from typechecker.type_services import Service


class TypeInference:
    def __init__(self, services: Service) -> None:
        self.services = services

    def _trace(self, line: str) -> None:
        if self.services.checker._trace_enabled:
            self.services.checker._trace(line)

    def _collect_typarams(self, t: Ty, out: set[str]) -> None:
        # Collect free type-parameter names appearing anywhere inside ``t``.
        if isinstance(t, TyParam):
            out.add(t.name)
            return
        if isinstance(t, TyNominal):
            for a in t.args:
                self._collect_typarams(a, out)
            return
        if isinstance(t, TyTuple):
            for e in t.elems:
                self._collect_typarams(e, out)
            return
        if isinstance(t, TyArrow):
            for p in t.params:
                self._collect_typarams(p, out)
            self._collect_typarams(t.ret, out)

    @dataclass
    class _Bounds:
        lowers: list[Ty] = field(default_factory=list)  # lower <: T
        uppers: list[Ty] = field(default_factory=list)  # T <: upper

    def _push_lower(self, table: Dict[str, _Bounds], name: str, ty: Ty) -> None:
        # Add a lower bound for one type variable, deduplicating by equivalence.
        b = table[name]
        if not any(self.services.types_equivalent(ty, old) for old in b.lowers):
            b.lowers.append(ty)

    def _push_upper(self, table: Dict[str, _Bounds], name: str, ty: Ty) -> None:
        # Add an upper bound for one type variable, deduplicating by equivalence.
        b = table[name]
        if not any(self.services.types_equivalent(ty, old) for old in b.uppers):
            b.uppers.append(ty)

    def _collect_bounds_from_structural_match(
        self, sub: Ty, sup: Ty, inferable: set[str], table: Dict[str, _Bounds]
    ) -> bool:
        """Collect inference bounds from ``sub <: sup`` matching.

        Descends structurally when heads align. When nominal heads differ, also
        tries each declared supertype of ``sub`` so obligations such as
        ``Array<Int64> <: Collection<T>`` decompose via ``Collection<Int64>``.
        """

        if isinstance(sup, TyParam) and sup.name in inferable:
            self._push_lower(table, sup.name, sub)
            return True
        if isinstance(sub, TyParam) and sub.name in inferable:
            self._push_upper(table, sub.name, sup)
            return True
        if isinstance(sub, TyPrim) and isinstance(sup, TyPrim):
            return sub.name == sup.name
        if isinstance(sub, TyParam) and isinstance(sup, TyParam):
            return sub.name == sup.name
        if isinstance(sub, TyNominal) and isinstance(sup, TyNominal):
            if sup.name == "Iterable" and len(sup.args) == 1:
                elem = self.services.iterable_element_for_subtyping(sub)
                if elem is not None:
                    return self._collect_bounds_from_structural_match(elem, sup.args[0], inferable, table)
            if sub.name == sup.name and len(sub.args) == len(sup.args):
                # Nominal args are invariant in this checker.
                for sa, fa in zip(sub.args, sup.args):
                    left_ok = self._collect_bounds_from_structural_match(sa, fa, inferable, table)
                    right_ok = self._collect_bounds_from_structural_match(fa, sa, inferable, table)
                    if not (left_ok and right_ok):
                        return False
                return True
            for super_ty in self.services._declared_nominal_supers(sub):
                if self._collect_bounds_from_structural_match(super_ty, sup, inferable, table):
                    return True
            return False
        if isinstance(sub, TyTuple) and isinstance(sup, TyTuple):
            if len(sub.elems) != len(sup.elems):
                return False
            for se, fe in zip(sub.elems, sup.elems):
                if not self._collect_bounds_from_structural_match(se, fe, inferable, table):
                    return False
            return True
        if isinstance(sub, TyArrow) and isinstance(sup, TyArrow):
            if len(sub.params) != len(sup.params):
                return False
            # Function subtyping: params contravariant, return covariant.
            for sp, fp in zip(sub.params, sup.params):
                if not self._collect_bounds_from_structural_match(fp, sp, inferable, table):
                    return False
            return self._collect_bounds_from_structural_match(sub.ret, sup.ret, inferable, table)
        return False

    def _relation_holds(self, sub: Ty, sup: Ty) -> bool:
        """Semantic predicate for the subtype relation ``sub <: sup``."""
        return self.services.is_subtype(sub, sup)

    def _mentions_inferable(self, t: Ty, inferable: set[str]) -> bool:
        names: set[str] = set()
        self._collect_typarams(t, names)
        return any(name in inferable for name in names)

    def _pick_candidate_from_lowers(self, name: str, lowers: list[Ty], uppers: list[Ty]) -> Ty:
        # Choose a best lower-bound witness and verify it satisfies all uppers.
        cand = lowers[0]
        for lb in lowers[1:]:
            if self.services.is_subtype(lb, cand):
                continue
            if self.services.is_subtype(cand, lb):
                cand = lb
                continue
            raise check_error(E_CHECK_CONFLICTING_INFERENCE, f"conflicting lower bounds for {name}: {cand} vs {lb}")
        for ub in uppers:
            if not self.services.is_subtype(cand, ub):
                raise check_error(
                    E_CHECK_CONFLICTING_INFERENCE,
                    f"unsatisfied bounds for {name}: need {cand} <: {ub}",
                )
        return cand

    def _pick_candidate_from_uppers(self, name: str, uppers: list[Ty]) -> Ty:
        # Choose a most-specific upper-bound witness.
        cand = uppers[0]
        for ub in uppers[1:]:
            if self.services.is_subtype(cand, ub):
                continue
            if self.services.is_subtype(ub, cand):
                cand = ub
                continue
            raise check_error(E_CHECK_CONFLICTING_INFERENCE, f"conflicting upper bounds for {name}: {cand} vs {ub}")
        return cand

    def _solve_subst(self, inferable: set[str], table: Dict[str, _Bounds]) -> Dict[str, Ty]:
        # Solve one substitution map from per-variable lower/upper bounds.
        subst: Dict[str, Ty] = {}
        for name in sorted(inferable):
            b = table[name]
            if b.lowers:
                subst[name] = self._pick_candidate_from_lowers(name, b.lowers, b.uppers)
            elif b.uppers:
                subst[name] = self._pick_candidate_from_uppers(name, b.uppers)
        return subst

    def _infer_witness_from_subtype_obligation(self, sub: Ty, sup: Ty, var_name: str) -> Optional[Ty]:
        """Infer one witness type variable from a single obligation ``sub <: sup``."""
        inferable = {var_name}
        bounds: Dict[str, TypeInference._Bounds] = {var_name: TypeInference._Bounds()}
        matched = self._collect_bounds_from_structural_match(sub, sup, inferable, bounds)
        if not matched and not (self._mentions_inferable(sup, inferable) and self._relation_holds(sub, sup)):
            return None
        try:
            subst = self._solve_subst(inferable, bounds)
        except TypeCheckError:
            return None
        witness = subst.get(var_name)
        if witness is None:
            return None
        if not self._relation_holds(sub, subst_ty(subst, sup)):
            return None
        return witness

    def infer_iterable_element(self, sigma: Ty) -> Optional[Ty]:
        """Solve loop element type ``T_e`` from ``sigma <: Iterable<T_e>``.

        Uses the same bound collection and solving steps as generic call
        inference (``_collect_bounds_from_structural_match`` and
        ``_solve_subst``), including nominal supertype decomposition when
        heads differ.

        Returns ``None`` when ``sigma`` is not iterable or when no consistent
        witness element type can be solved.
        """
        elem_var = "__for_elem"
        target = TyNominal("Iterable", (TyParam(elem_var),))
        return self._infer_witness_from_subtype_obligation(sigma, target, elem_var)

    def _bind_arguments(self, sig: Sig, args: CallArgs) -> List[Expr]:
        # Reorder positional/named call arguments to signature parameter order.
        pos_nodes = list(args.positional)
        named_nodes = dict(args.named)
        params = list(zip(sig.param_names, sig.param_types))
        valid_named = {pn for pn, _ in params if pn is not None}
        unknown_named = sorted(k for k in named_nodes.keys() if k not in valid_named)
        if unknown_named:
            unknown = ", ".join(unknown_named)
            raise check_error(E_CHECK_UNKNOWN_NAMED_ARG, f"unknown named arg(s): {unknown}")
        pi = 0
        actual_nodes: List[Expr] = []
        for pn, _pt in params:
            if pn is not None and pn in named_nodes:
                actual_nodes.append(named_nodes.pop(pn))
            elif pi < len(pos_nodes):
                actual_nodes.append(pos_nodes[pi])
                pi += 1
            else:
                raise check_error(E_CHECK_ARG_MISMATCH, "arg mismatch")
        if pi != len(pos_nodes):
            raise check_error(E_CHECK_TOO_MANY_POSITIONAL_ARGS, "too many positional args")
        if named_nodes:
            leftover = ", ".join(sorted(named_nodes.keys()))
            raise internal_error(E_INTERNAL_UNCONSUMED_NAMED_ARGS, f"unconsumed named args after binding: {leftover}")
        return actual_nodes

    def _inferable_set(self, sig: Sig) -> set[str]:
        return set(sig.type_params)

    def _explicit_subst(self, sig: Sig, explicit_type_args: Tuple[Ty, ...]) -> Dict[str, Ty]:
        if len(explicit_type_args) != len(sig.type_params):
            raise check_error(
                "E_DECL_TYPE_ARITY_MISMATCH",
                f"call expects {len(sig.type_params)} type argument(s), got {len(explicit_type_args)}",
            )
        return {name: arg for name, arg in zip(sig.type_params, explicit_type_args)}

    def apply_sig_explicit_synth(
        self,
        sig: Sig,
        args: CallArgs,
        explicit_type_args: Tuple[Ty, ...],
        ctx: TypeContext,
        *,
        synth_expr: Callable[[Expr, TypeContext], Ty],
    ) -> Ty:
        subst = self._explicit_subst(sig, explicit_type_args)
        actual_nodes = self._bind_arguments(sig, args)
        inst_params = [subst_ty(subst, pt) for pt in sig.param_types]
        actual_types = [synth_expr(node, ctx) for node in actual_nodes]
        for actual, expect in zip(actual_types, inst_params):
            if not self.services.is_subtype(actual, expect):
                raise check_error(
                    E_CHECK_ARG_MISMATCH,
                    f"expected {expect}, got {actual}",
                )
        ret = subst_ty(subst, sig.ret)
        self._trace(f"{format_gamma(ctx)} |- apply_sig[explicit-synth] => {ret}")
        return ret

    def apply_sig_explicit_check(
        self,
        sig: Sig,
        args: CallArgs,
        explicit_type_args: Tuple[Ty, ...],
        expect: Ty,
        ctx: TypeContext,
        *,
        check_expr: Callable[[Expr, TypeContext, Ty], None],
    ) -> Ty:
        subst = self._explicit_subst(sig, explicit_type_args)
        actual_nodes = self._bind_arguments(sig, args)
        inst_params = [subst_ty(subst, pt) for pt in sig.param_types]
        ret = subst_ty(subst, sig.ret)
        if not self.services.is_subtype(ret, expect):
            raise check_error(
                E_CHECK_INFERENCE_RETURN_MISMATCH,
                f"expected {expect}, got {ret}",
            )
        for node, want in zip(actual_nodes, inst_params):
            check_expr(node, ctx, want)
        self._trace(f"{format_gamma(ctx)} |- apply_sig[explicit-check] => {ret}")
        return ret

    def _match_argument_types(
        self,
        sig: Sig,
        actual_types: List[Ty],
        inferable: set[str],
        bounds: Dict[str, _Bounds],
        subst: Optional[Dict[str, Ty]] = None,
    ) -> None:
        # Contribute bounds from ``actual_i <: formal_i`` for each argument.
        subst = subst or {}
        for actual, formal in zip(actual_types, sig.param_types):
            formal_inst = subst_ty(subst, formal)
            matched = self._collect_bounds_from_structural_match(actual, formal_inst, inferable, bounds)
            if not matched and self._mentions_inferable(formal_inst, inferable) and not self._relation_holds(actual, formal_inst):
                raise check_error(
                    E_CHECK_INFERENCE_CONSTRAINT_MISMATCH,
                    f"cannot infer type arguments from {actual} <: {formal_inst}",
                )

    def apply_sig_synth(
        self,
        sig: Sig,
        args: CallArgs,
        ctx: TypeContext,
        *,
        synth_expr: Callable[[Expr, TypeContext], Ty],
        check_expr: Callable[[Expr, TypeContext, Ty], None],
    ) -> Ty:
        """Infer and instantiate a call in synthesis mode.

        Algorithm:
            1. Bind call arguments to parameter order (positional + named).
            2. Synthesize each argument type (`T1..Tn`) using `synth_expr`.
            3. Build subtype constraints `Ti <: Pi` against signature parameters.
            4. Solve bounds (`lower <: X <: upper`) for each inferable type var.
            5. Instantiate parameter/return types with the solved substitution.
            6. Verify each synthesized argument type is a subtype of the
               instantiated parameter type (no second expression check).

        Args:
            sig: Callee signature, possibly generic.
            args: Call arguments (lowered expressions).
            ctx: Typing context for expression callbacks.
            synth_expr: Callback used to synthesize argument expression types.
            check_expr: Unused in synthesis mode (kept for a uniform ``apply_sig``
                callback surface).

        Returns:
            Instantiated return type of `sig` after solving generic arguments.
        """
        actual_nodes = self._bind_arguments(sig, args)
        actual_types = [synth_expr(node, ctx) for node in actual_nodes]
        inferable = self._inferable_set(sig)
        bounds: Dict[str, TypeInference._Bounds] = {name: TypeInference._Bounds() for name in inferable}
        self._match_argument_types(sig, actual_types, inferable, bounds)
        subst = self._solve_subst(inferable, bounds)
        inst_params = [subst_ty(subst, pt) for pt in sig.param_types]
        for actual, expect in zip(actual_types, inst_params):
            if not self.services.is_subtype(actual, expect):
                raise check_error(
                    E_CHECK_ARG_MISMATCH,
                    f"expected {expect}, got {actual}",
                )
        ret = subst_ty(subst, sig.ret)
        self._trace(f"{format_gamma(ctx)} |- apply_sig[synth] => {ret}")
        return ret

    def apply_sig_check(
        self,
        sig: Sig,
        args: CallArgs,
        expect: Ty,
        ctx: TypeContext,
        *,
        synth_expr: Callable[[Expr, TypeContext], Ty],
        check_expr: Callable[[Expr, TypeContext, Ty], None],
    ) -> Ty:
        """Infer and instantiate a call in checking mode.

        Algorithm:
            1. Bind call arguments to parameter order.
            2. Add constraints from the expected result type (`sig.ret <: expect`).
            3. Solve any type variables determined by return-position matching.
            4. If some variables remain unsolved, synthesize argument types, add
               argument constraints (`Ti <: Pi[subst]`), solve again, and verify
               each synthesized argument type against the instantiated parameter
               type; otherwise check each argument expression against
               ``theta_0(P_i)``.
            5. Return the instantiated signature return type.

        Args:
            sig: Callee signature, possibly generic.
            args: Call arguments (lowered expressions).
            expect: Expected type from the surrounding checking context.
            ctx: Typing context for expression callbacks.
            synth_expr: Callback used when argument synthesis is required to
                finish unsolved variables.
            check_expr: Callback used to validate each argument against
                instantiated parameter types.

        Returns:
            Instantiated return type of `sig`, constrained by `expect`.
        """
        actual_nodes = self._bind_arguments(sig, args)
        inferable = self._inferable_set(sig)
        bounds: Dict[str, TypeInference._Bounds] = {name: TypeInference._Bounds() for name in inferable}
        matched = self._collect_bounds_from_structural_match(sig.ret, expect, inferable, bounds)
        if not matched and self._mentions_inferable(sig.ret, inferable) and not self._relation_holds(sig.ret, expect):
            raise check_error(
                E_CHECK_INFERENCE_RETURN_MISMATCH,
                f"cannot infer return-constrained type arguments from {sig.ret} <: {expect}",
            )
        subst = self._solve_subst(inferable, bounds)
        if any(name not in subst for name in inferable):
            actual_types = [synth_expr(node, ctx) for node in actual_nodes]
            self._match_argument_types(sig, actual_types, inferable, bounds, subst)
            subst = self._solve_subst(inferable, bounds)
            inst_params = [subst_ty(subst, pt) for pt in sig.param_types]
            for actual, want in zip(actual_types, inst_params):
                if not self.services.is_subtype(actual, want):
                    raise check_error(
                        E_CHECK_ARG_MISMATCH,
                        f"expected {want}, got {actual}",
                    )
            ret = subst_ty(subst, sig.ret)
        else:
            inst_params = [subst_ty(subst, pt) for pt in sig.param_types]
            for node, want in zip(actual_nodes, inst_params):
                check_expr(node, ctx, want)
            ret = subst_ty(subst, sig.ret)
        self._trace(f"{format_gamma(ctx)} |- apply_sig[check] => {ret}")
        return ret

    def apply_sig(
        self,
        sig: Sig,
        args: CallArgs,
        ctx: TypeContext,
        *,
        synth_expr: Callable[[Expr, TypeContext], Ty],
        check_expr: Callable[[Expr, TypeContext, Ty], None],
        expected_ret: Optional[Ty] = None,
        explicit_type_args: Optional[Tuple[Ty, ...]] = None,
    ) -> Ty:
        """Apply one call signature, using explicit or inferred type arguments.

        When ``explicit_type_args`` is provided, every required type parameter must
        be supplied and inference is skipped.
        """
        if explicit_type_args is not None:
            if sig.type_params:
                if expected_ret is None:
                    return self.apply_sig_explicit_synth(
                        sig,
                        args,
                        explicit_type_args,
                        ctx,
                        synth_expr=synth_expr,
                    )
                return self.apply_sig_explicit_check(
                    sig,
                    args,
                    explicit_type_args,
                    expected_ret,
                    ctx,
                    check_expr=check_expr,
                )
            if explicit_type_args:
                raise check_error(
                    "E_DECL_TYPE_ARITY_MISMATCH",
                    f"call expects 0 type argument(s), got {len(explicit_type_args)}",
                )
        if expected_ret is None:
            return self.apply_sig_synth(sig, args, ctx, synth_expr=synth_expr, check_expr=check_expr)
        return self.apply_sig_check(
            sig,
            args,
            expected_ret,
            ctx,
            synth_expr=synth_expr,
            check_expr=check_expr,
        )
