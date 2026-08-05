# Vendored from the competition reference implementation:
# https://gitcode.com/bhzhan/cangjie-fragment-checker
# Not claimed as team-original code; provenance and adaptations are documented
# in ../README.md and the repository-level THIRD_PARTY_NOTICES.md.

"""Typing context object shared by expression and declaration checking.

``TypeContext`` is a persistent parent-linked environment. Each context stores
bindings introduced at one layer and delegates lookup to ``parent``.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Dict, Mapping, Optional

from typechecker.ast import ClassDecl, ConstructorDecl, FuncDecl, MethodDecl, T_UNIT, Ty, TyParam, subst_ty
from typechecker.errors import internal_error


@dataclass(frozen=True)
class TypeContext:
    """Active semantic typing context.

    Attributes:
        parent: Outer lexical context or ``None`` at root.
        layer: Value bindings introduced at this layer only.
        layer_tparams: Type parameters introduced at this layer only.
        layer_ret: Return type introduced at this layer, or ``None`` to inherit.
        layer_in_loop: Whether this layer establishes loop context.
    """

    parent: Optional["TypeContext"]
    layer: Mapping[str, Ty]
    layer_tparams: frozenset[str]
    layer_ret: Optional[Ty]
    layer_in_loop: bool
    class_decl: Optional[ClassDecl] = None

    def __post_init__(self) -> None:
        """Normalize mutable constructor inputs into immutable representations."""
        object.__setattr__(self, "layer", MappingProxyType(dict(self.layer)))
        object.__setattr__(self, "layer_tparams", frozenset(self.layer_tparams))

    @staticmethod
    def empty(*, ret: Ty = T_UNIT) -> "TypeContext":
        """Build an empty root context (used for tests or top-level checks)."""
        return TypeContext(None, {}, frozenset(), ret, False, None)

    @property
    def tparams(self) -> frozenset[str]:
        """All in-scope type parameters from the current layer outward."""
        if self.parent is None:
            return self.layer_tparams
        return self.layer_tparams | self.parent.tparams

    @property
    def ret(self) -> Ty:
        """Active function return type from the nearest defining layer."""
        if self.layer_ret is not None:
            return self.layer_ret
        if self.parent is None:
            raise internal_error("E_INTERNAL_CTX_MISSING_RET", "TypeContext has no return type in scope")
        return self.parent.ret

    @property
    def in_loop(self) -> bool:
        """Whether the current judgment is inside a loop body."""
        if self.layer_in_loop:
            return True
        if self.parent is None:
            return False
        return self.parent.in_loop

    def with_binding(self, n: str, t: Ty) -> "TypeContext":
        """Context with one extra name binding added to the current layer."""
        lay = dict(self.layer)
        lay[n] = t
        return TypeContext(
            self.parent, lay, self.layer_tparams, self.layer_ret, self.layer_in_loop, self.class_decl
        )

    def lookup_var(self, n: str) -> Optional[Ty]:
        """Look up a variable type, walking from inner to outer layers."""
        if n in self.layer:
            return self.layer[n]
        if self.parent is None:
            return None
        return self.parent.lookup_var(n)

    def enter_block(self) -> TypeContext:
        """Child context with a fresh empty local scope layer."""
        return TypeContext(self, {}, frozenset(), None, False, self.class_decl)

    def push_layer(self, layer: Mapping[str, Ty]) -> TypeContext:
        """Child context with the given bindings as its innermost scope."""
        return TypeContext(self, dict(layer), frozenset(), None, False, self.class_decl)

    def enter_loop(self) -> TypeContext:
        """Child context that marks loop-body checking scope."""
        return TypeContext(self, {}, frozenset(), None, True, self.class_decl)

    @staticmethod
    def for_function(fd: FuncDecl) -> TypeContext:
        """Entry context for checking a top-level function body."""
        lay = {n: t for n, t in zip(fd.param_names, fd.param_types) if n}
        return TypeContext(None, lay, frozenset(fd.type_params), fd.ret, False, None)

    @staticmethod
    def for_class_method(cd: ClassDecl, m: MethodDecl) -> TypeContext:
        """Entry context for checking a class method body."""
        msub = {x: TyParam(x) for x in cd.type_params}
        lay0 = {k: subst_ty(msub, v) for k, v in cd.static_fields.items()}
        if not m.is_static:
            lay0.update({k: subst_ty(msub, v) for k, v in cd.fields.items()})
        return TypeContext(
            None, lay0, frozenset(set(cd.type_params) | set(m.type_params)), m.ret, False, cd
        )

    @staticmethod
    def for_constructor(cd: ClassDecl, c: ConstructorDecl) -> TypeContext:
        """Entry context for checking a constructor body; parameters shadow fields in a child layer."""
        msub = {x: TyParam(x) for x in cd.type_params}
        field_layer: Dict[str, Ty] = {k: subst_ty(msub, v) for k, v in cd.static_fields.items()}
        field_layer.update({k: subst_ty(msub, v) for k, v in cd.fields.items()})
        base = TypeContext(None, field_layer, frozenset(cd.type_params), T_UNIT, False, cd)
        param_layer = {n: t for n, t in zip(c.param_names, c.param_types) if n}
        return base.push_layer(param_layer)
