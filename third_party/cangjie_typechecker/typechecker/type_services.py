# Vendored from the competition reference implementation:
# https://gitcode.com/bhzhan/cangjie-fragment-checker
# Locally adapted for offline validation; not claimed as team-original code.
# See ../README.md and the repository-level THIRD_PARTY_NOTICES.md.

"""Core type services: built-ins and subtyping judgments."""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from typechecker.builtin_context import Sig, builtin_context
from typechecker.ast import Ty, TyArrow, TyNominal, TyParam, TyPrim, TyTuple, subst_ty

if TYPE_CHECKING:
    from typechecker.checker import TypeChecker

_ITERABLE_SOURCE_NAMES: frozenset[str] = frozenset(
    {"Range", "Array", "ArrayList", "HashSet", "KeysView", "ValuesView"}
)


class Service:
    def __init__(self, checker: TypeChecker) -> None:
        # ``_trace_depth`` ensures we emit one top-level trace line per subtype judgment.
        self.checker = checker
        self.builtin_ctx = builtin_context()
        self.builtins: dict[str, list[Sig]] = self.builtin_ctx.global_function_sigs()
        self._trace_depth = 0

    def is_subtype(self, a: Ty, b: Ty) -> bool:
        """Return whether ``a <: b``."""
        dmark: Optional[int] = None
        if self.checker._trace_enabled:
            self._trace_depth += 1
            dmark = self._trace_depth
        r = False
        try:
            r = self._is_subtype_inner(a, b)
        finally:
            if dmark is not None:
                if dmark == 1:
                    self.checker._trace(f"<: {a} <: {b} = {r}")
                self._trace_depth -= 1
        return r

    def _is_subtype_inner(self, a: Ty, b: Ty) -> bool:
        if isinstance(a, TyPrim) and isinstance(b, TyPrim):
            return a.name == b.name
        if isinstance(a, TyParam) and isinstance(b, TyParam):
            return a.name == b.name
        if isinstance(a, TyNominal) and isinstance(b, TyNominal):
            return self._subtype_nominal(a, b)
        if isinstance(a, TyTuple) and isinstance(b, TyTuple):
            return len(a.elems) == len(b.elems) and all(self.is_subtype(x, y) for x, y in zip(a.elems, b.elems))
        if isinstance(a, TyArrow) and isinstance(b, TyArrow):
            if len(a.params) != len(b.params):
                return False
            return all(self.is_subtype(bp, ap) for ap, bp in zip(a.params, b.params)) and self.is_subtype(a.ret, b.ret)
        return False

    def types_equivalent(self, x: Ty, y: Ty) -> bool:
        return self.is_subtype(x, y) and self.is_subtype(y, x)

    def meet_types(self, a: Ty, b: Ty) -> Optional[Ty]:
        """Greatest lower bound (meet) for contravariant positions (e.g. function params)."""
        if self.is_subtype(a, b):
            return a
        if self.is_subtype(b, a):
            return b
        if isinstance(a, TyTuple) and isinstance(b, TyTuple) and len(a.elems) == len(b.elems):
            elems: list[Ty] = []
            for x, y in zip(a.elems, b.elems):
                m = self.meet_types(x, y)
                if m is None:
                    return None
                elems.append(m)
            return TyTuple(tuple(elems))
        if isinstance(a, TyArrow) and isinstance(b, TyArrow) and len(a.params) == len(b.params):
            params: list[Ty] = []
            for ap, bp in zip(a.params, b.params):
                j = self.join_types(ap, bp)
                if j is None:
                    return None
                params.append(j)
            ret = self.meet_types(a.ret, b.ret)
            if ret is None:
                return None
            return TyArrow(tuple(params), ret)
        return None

    def join_types(self, a: Ty, b: Ty) -> Optional[Ty]:
        """Compute least upper bound (join) under current subtype relation.

        Returns ``None`` when no unique least upper bound exists.
        """
        if self.types_equivalent(a, b):
            return a
        if isinstance(a, TyTuple) and isinstance(b, TyTuple) and len(a.elems) == len(b.elems):
            elems: list[Ty] = []
            for x, y in zip(a.elems, b.elems):
                j = self.join_types(x, y)
                if j is None:
                    return None
                elems.append(j)
            return TyTuple(tuple(elems))
        if isinstance(a, TyArrow) and isinstance(b, TyArrow) and len(a.params) == len(b.params):
            params: list[Ty] = []
            for ap, bp in zip(a.params, b.params):
                m = self.meet_types(ap, bp)
                if m is None:
                    return None
                params.append(m)
            ret = self.join_types(a.ret, b.ret)
            if ret is None:
                return None
            return TyArrow(tuple(params), ret)
        if isinstance(a, TyNominal) and isinstance(b, TyNominal):
            return self._join_nominal(a, b)
        return None

    def iterable_element_for_subtyping(self, n: TyNominal) -> Optional[Ty]:
        """Element type used when decomposing ``n<...> <: Iterable<T_e>`` for inference."""
        if n.name in _ITERABLE_SOURCE_NAMES and len(n.args) == 1:
            return n.args[0]
        return self.builtin_ctx.iterable_element_type(n)

    def _declared_nominal_supers(self, n: TyNominal) -> List[TyNominal]:
        """Direct declared supertypes from built-ins (``context.json``) and user class/interface declarations (no transitive closure)."""
        out: List[TyNominal] = []
        out.extend(self.builtin_ctx.nominal_supers(n))
        cd = self.checker.classes.get(n.name)
        if cd is not None:
            subst = {tp: arg for tp, arg in zip(cd.type_params, n.args)}
            out.extend(subst_ty(subst, sup) for sup in cd.supers)
        idecl = self.checker.interfaces.get(n.name)
        if idecl is not None:
            subst = {tp: arg for tp, arg in zip(idecl.type_params, n.args)}
            out.extend(subst_ty(subst, sup) for sup in idecl.supers)
        return out

    def _subtype_to_iterable(self, a: TyNominal, b: TyNominal) -> bool:
        if b.name != "Iterable" or len(b.args) != 1:
            return False
        if a.name == "Iterable" and len(a.args) == 1:
            return self.is_subtype(a.args[0], b.args[0]) and self.is_subtype(b.args[0], a.args[0])
        elem = self.iterable_element_for_subtyping(a)
        return elem is not None and self.types_equivalent(elem, b.args[0])

    def _subtype_nominal(self, a: TyNominal, b: TyNominal) -> bool:
        if a.name == b.name and len(a.args) == len(b.args):
            if all(self.types_equivalent(x, y) for x, y in zip(a.args, b.args)):
                return True
        if self._subtype_to_iterable(a, b):
            return True
        for sup in self._declared_nominal_supers(a):
            if self.is_subtype(sup, b):
                return True
        return False

    def _nominal_supertypes_inclusive(self, n: TyNominal) -> List[TyNominal]:
        out: List[TyNominal] = []
        seen: set[str] = set()
        stack: List[TyNominal] = [n]
        while stack:
            cur = stack.pop()
            key = str(cur)
            if key in seen:
                continue
            seen.add(key)
            out.append(cur)
            for sup in self._declared_nominal_supers(cur):
                stack.append(sup)
        return out

    def _join_nominal(self, a: TyNominal, b: TyNominal) -> Optional[Ty]:
        sa = self._nominal_supertypes_inclusive(a)
        sb = self._nominal_supertypes_inclusive(b)
        common: List[TyNominal] = []
        for x in sa:
            if any(self.types_equivalent(x, y) for y in sb):
                common.append(x)
        if not common:
            return None
        minimal: List[TyNominal] = []
        for c in common:
            if any(self.is_subtype(o, c) and not self.types_equivalent(o, c) for o in common):
                continue
            minimal.append(c)
        if not minimal:
            return None
        if len(minimal) == 1:
            return minimal[0]
        for cand in minimal:
            if all(self.is_subtype(cand, other) for other in minimal):
                return cand
        return None
