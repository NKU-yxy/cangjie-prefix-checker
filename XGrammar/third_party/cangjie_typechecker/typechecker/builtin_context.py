"""Built-in/import context adapter loaded from ``context.json``.

This module is the canonical implementation for built-in/import declarations.
It validates and decodes ``typechecker/context.json`` and exposes a single
adapter surface (`BuiltinContext`) used by the semantic checker.

Schema reference (shape-level; validated by ``validate_context_schema``):

Top-level object keys:

- ``schema_version``: int
- ``nominals``: object map ``name -> nominal_spec``
- ``interfaces``: object map ``name -> interface_spec``
- ``global_functions``: object map ``name -> [sig, ...]``
- ``global_variables``: array of ``{"name": str, "type": ty_spec, ...}``

Type specs (``ty_spec``):

- ``"Int64"`` / ``"Bool"`` / ``"String"`` / etc. (string primitive/nominal)
- ``{"tparam": "T"}``
- ``{"nominal": "Array", "args": [ty_spec, ...]}``
- ``{"tuple": [ty_spec, ty_spec, ...]}``

Signature object (``sig``):

- ``type_params``: optional ``[str, ...]`` (default ``[]``)
- ``params``: optional ``[{"name"?: str, "type": ty_spec}, ...]`` (default ``[]``)
- ``ret``: required ``ty_spec``

Interface spec:

- ``type_params``: optional ``[str, ...]``
- ``methods``: optional object map ``method_name -> sig | [sig, ...]``

Nominal spec:

- ``type_params``: optional ``[str, ...]``
- ``instance_fields``: optional object map ``field -> ty_spec``
- ``static_fields``: optional object map ``field -> ty_spec``
- ``instance_methods``: optional object map ``name -> sig | [sig, ...]``
- ``static_methods``: optional object map ``name -> sig | [sig, ...]``
- ``constructors``: optional ``[sig, ...]``
- ``supers``: optional ``[ty_spec, ...]`` (decoded and filtered to nominals)
- ``iterable_element``: optional ``ty_spec`` for ``for-in`` element type

Notes for editing ``context.json``:

- Validation is structural. Unknown extra keys are tolerated for forward
  compatibility, but required keys and value shapes must match the schema above.
- Type decoding happens after validation; malformed type specs fail fast with
  precise ``$.path.to.node`` diagnostics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Union

from typechecker.ast import PRIM, Ty, TyNominal, TyParam, TyTuple, subst_ty


@dataclass
class Sig:
    """Function / method / constructor signature (after resolving type parameters)."""

    type_params: tuple[str, ...]
    param_names: tuple[Optional[str], ...]
    param_types: tuple[Ty, ...]
    ret: Ty

    def subst(self, m: dict[str, Ty]) -> Sig:
        return Sig(
            (),
            self.param_names,
            tuple(subst_ty(m, p) for p in self.param_types),
            subst_ty(m, self.ret),
        )


MethodEntry = Union[Sig, List[Sig]]
MethodTable = dict[str, MethodEntry]
StaticMethodTable = dict[str, Sig]
CtorList = list[Sig]

_CONTEXT_PATH = Path(__file__).resolve().with_name("context.json")


def validate_context_schema(raw: object, *, path: str = "$") -> None:
    """Fail fast on malformed ``context.json`` (shape only; decodes types lazily elsewhere)."""

    if not isinstance(raw, dict):
        raise ValueError(f"{path}: context root must be object")
    required = ("schema_version", "nominals", "interfaces", "global_functions", "global_variables")
    for k in required:
        if k not in raw:
            raise ValueError(f"{path}: missing required key {k!r}")
    if not isinstance(raw["schema_version"], int):
        raise ValueError(f"{path}.schema_version: must be int")
    if not isinstance(raw["nominals"], dict):
        raise ValueError(f"{path}.nominals: must be object")
    if not isinstance(raw["interfaces"], dict):
        raise ValueError(f"{path}.interfaces: must be object")
    if not isinstance(raw["global_functions"], dict):
        raise ValueError(f"{path}.global_functions: must be object")
    if not isinstance(raw["global_variables"], list):
        raise ValueError(f"{path}.global_variables: must be array")

    for i, v in enumerate(raw["global_variables"]):
        vp = f"{path}.global_variables[{i}]"
        if not isinstance(v, dict) or "name" not in v or "type" not in v:
            raise ValueError(f"{vp}: must be object with name and type")
        _validate_ty_spec(v["type"], f"{vp}.type")

    for fname, sigs in raw["global_functions"].items():
        fp = f'{path}.global_functions["{fname}"]'
        if not isinstance(sigs, list):
            raise ValueError(f"{fp}: must be array")
        for i, s in enumerate(sigs):
            _validate_sig_dict(s, f"{fp}[{i}]")

    for iname, ispec in raw["interfaces"].items():
        ip = f'{path}.interfaces["{iname}"]'
        if not isinstance(ispec, dict):
            raise ValueError(f"{ip}: must be object")
        tps = ispec.get("type_params", [])
        if not isinstance(tps, list) or not all(isinstance(x, str) for x in tps):
            raise ValueError(f"{ip}.type_params: must be array of strings")
        methods = ispec.get("methods", {})
        if methods is not None and not isinstance(methods, dict):
            raise ValueError(f"{ip}.methods: must be object")
        if isinstance(methods, dict):
            for mn, ment in methods.items():
                mp = f'{ip}.methods["{mn}"]'
                if isinstance(ment, list):
                    for j, s in enumerate(ment):
                        _validate_sig_dict(s, f"{mp}[{j}]")
                else:
                    _validate_sig_dict(ment, mp)

    for nname, nspec in raw["nominals"].items():
        np = f'{path}.nominals["{nname}"]'
        if not isinstance(nspec, dict):
            raise ValueError(f"{np}: must be object")
        tps = nspec.get("type_params", [])
        if not isinstance(tps, list) or not all(isinstance(x, str) for x in tps):
            raise ValueError(f"{np}.type_params: must be array of strings")
        for fld in ("instance_fields", "static_fields"):
            block = nspec.get(fld, {})
            if block is not None and not isinstance(block, dict):
                raise ValueError(f"{np}.{fld}: must be object")
            if isinstance(block, dict):
                for k, ty in block.items():
                    _validate_ty_spec(ty, f'{np}.{fld}["{k}"]')
        for mname in ("instance_methods", "static_methods"):
            mtab = nspec.get(mname, {})
            if mtab is not None and not isinstance(mtab, dict):
                raise ValueError(f"{np}.{mname}: must be object")
            if isinstance(mtab, dict):
                for mn, ment in mtab.items():
                    mp = f'{np}.{mname}["{mn}"]'
                    if isinstance(ment, list):
                        for j, s in enumerate(ment):
                            _validate_sig_dict(s, f"{mp}[{j}]")
                    else:
                        _validate_sig_dict(ment, mp)
        ctors = nspec.get("constructors", [])
        if ctors is not None:
            if not isinstance(ctors, list):
                raise ValueError(f"{np}.constructors: must be array")
            for i, s in enumerate(ctors):
                _validate_sig_dict(s, f"{np}.constructors[{i}]")
        supers = nspec.get("supers", [])
        if supers is not None:
            if not isinstance(supers, list):
                raise ValueError(f"{np}.supers: must be array")
            for i, s in enumerate(supers):
                _validate_ty_spec(s, f"{np}.supers[{i}]")
        if "iterable_element" in nspec and nspec["iterable_element"] is not None:
            _validate_ty_spec(nspec["iterable_element"], f"{np}.iterable_element")


def _validate_sig_dict(s: object, path: str) -> None:
    if not isinstance(s, dict):
        raise ValueError(f"{path}: signature must be object")
    tps = s.get("type_params", [])
    if not isinstance(tps, list) or not all(isinstance(x, str) for x in tps):
        raise ValueError(f"{path}.type_params: must be array of strings")
    params = s.get("params", [])
    if not isinstance(params, list):
        raise ValueError(f"{path}.params: must be array")
    for i, p in enumerate(params):
        pp = f"{path}.params[{i}]"
        if not isinstance(p, dict) or "type" not in p:
            raise ValueError(f"{pp}: must be object with type")
        _validate_ty_spec(p["type"], f"{pp}.type")
    if "ret" not in s:
        raise ValueError(f"{path}: missing ret")
    _validate_ty_spec(s["ret"], f"{path}.ret")


def _validate_ty_spec(spec: object, path: str) -> None:
    if isinstance(spec, str):
        return
    if not isinstance(spec, dict):
        raise ValueError(f"{path}: type spec must be string or object")
    if "tparam" in spec:
        if not isinstance(spec["tparam"], str):
            raise ValueError(f"{path}.tparam: must be string")
        return
    if "nominal" in spec:
        if not isinstance(spec["nominal"], str):
            raise ValueError(f"{path}.nominal: must be string")
        args = spec.get("args", [])
        if not isinstance(args, list):
            raise ValueError(f"{path}.args: must be array")
        for i, a in enumerate(args):
            _validate_ty_spec(a, f"{path}.args[{i}]")
        return
    if "tuple" in spec:
        tup = spec["tuple"]
        if not isinstance(tup, list):
            raise ValueError(f"{path}.tuple: must be array")
        for i, a in enumerate(tup):
            _validate_ty_spec(a, f"{path}.tuple[{i}]")
        return
    raise ValueError(f"{path}: unsupported type spec shape {spec!r}")


@lru_cache(maxsize=1)
def _raw_context() -> dict:
    data = json.loads(_CONTEXT_PATH.read_text(encoding="utf-8"))
    validate_context_schema(data)
    return data


def _decode_ty(spec: object, tvars: dict[str, Ty]) -> Ty:
    if isinstance(spec, str):
        if spec in PRIM:
            return PRIM[spec]
        return TyNominal(spec, ())
    if isinstance(spec, dict):
        if "tparam" in spec:
            return tvars[str(spec["tparam"])]
        if "nominal" in spec:
            name = str(spec["nominal"])
            args = tuple(_decode_ty(a, tvars) for a in spec.get("args", []))
            return TyNominal(name, args)
        if "tuple" in spec:
            return TyTuple(tuple(_decode_ty(a, tvars) for a in spec["tuple"]))
    raise ValueError(f"unsupported type spec: {spec!r}")


def _decode_sig(spec: dict, tvars: dict[str, Ty]) -> Sig:
    sig_tps = tuple(spec.get("type_params", []))
    local = dict(tvars)
    for n in sig_tps:
        local[n] = TyParam(n)
    params = spec.get("params", [])
    pnames = tuple(p.get("name") for p in params)
    ptys = tuple(_decode_ty(p["type"], local) for p in params)
    ret = _decode_ty(spec["ret"], local)
    return Sig(sig_tps, pnames, ptys, ret)


def _decode_methods(spec: dict, tvars: dict[str, Ty]) -> MethodTable:
    out: MethodTable = {}
    for name, raw in spec.items():
        if isinstance(raw, list):
            out[name] = [_decode_sig(s, tvars) for s in raw]
        else:
            out[name] = _decode_sig(raw, tvars)
    return out


def _decode_fields(spec: dict[str, object], tvars: dict[str, Ty]) -> dict[str, Ty]:
    return {k: _decode_ty(v, tvars) for k, v in spec.items()}


class BuiltinContext:
    """Single adapter for built-in / import context (``context.json``)."""

    def nominal_type_param_arity(self, name: str) -> Optional[int]:
        spec = self._nominal_spec(name)
        if spec is None:
            return None
        return len(tuple(spec.get("type_params", [])))

    def interface_type_param_arity(self, name: str) -> Optional[int]:
        spec = self._interface_spec(name)
        if spec is None:
            return None
        return len(tuple(spec.get("type_params", [])))

    def nominal_names(self) -> frozenset[str]:
        return frozenset(_raw_context().get("nominals", {}).keys())

    def interface_names(self) -> frozenset[str]:
        return frozenset(_raw_context().get("interfaces", {}).keys())

    def _nominal_spec(self, name: str) -> Optional[dict]:
        return _raw_context().get("nominals", {}).get(name)

    def _interface_spec(self, name: str) -> Optional[dict]:
        return _raw_context().get("interfaces", {}).get(name)

    def _bind_nominal(self, n: TyNominal) -> tuple[dict, dict[str, Ty]] | None:
        spec = self._nominal_spec(n.name)
        if spec is None:
            return None
        tps = tuple(spec.get("type_params", []))
        if len(tps) != len(n.args):
            return None
        tvars = {tp: arg for tp, arg in zip(tps, n.args)}
        return spec, tvars

    def nominal_fields(self, n: TyNominal) -> dict[str, Ty]:
        bound = self._bind_nominal(n)
        if bound is None:
            return {}
        spec, tvars = bound
        return _decode_fields(spec.get("instance_fields", {}), tvars)

    def nominal_static_fields(self, name: str) -> dict[str, Ty]:
        spec = self._nominal_spec(name)
        if spec is None:
            return {}
        tps = tuple(spec.get("type_params", []))
        tvars = {tp: TyParam(tp) for tp in tps}
        return _decode_fields(spec.get("static_fields", {}), tvars)

    def nominal_instance_methods(self, n: TyNominal) -> Optional[MethodTable]:
        bound = self._bind_nominal(n)
        if bound is None:
            return None
        spec, tvars = bound
        return _decode_methods(spec.get("instance_methods", {}), tvars)

    def nominal_static_methods(self, n: TyNominal) -> Optional[StaticMethodTable]:
        bound = self._bind_nominal(n)
        if bound is None:
            return None
        spec, tvars = bound
        mts = _decode_methods(spec.get("static_methods", {}), tvars)
        return {k: v for k, v in mts.items() if isinstance(v, Sig)}

    def nominal_ctors(self, n: TyNominal) -> Optional[CtorList]:
        bound = self._bind_nominal(n)
        if bound is None:
            return None
        spec, tvars = bound
        return [_decode_sig(s, tvars) for s in spec.get("constructors", [])]

    def nominal_supers(self, n: TyNominal) -> list[TyNominal]:
        bound = self._bind_nominal(n)
        if bound is None:
            return []
        spec, tvars = bound
        out: list[TyNominal] = []
        for raw in spec.get("supers", []):
            ty = _decode_ty(raw, tvars)
            if isinstance(ty, TyNominal):
                out.append(ty)
        return out

    @lru_cache(maxsize=1)
    def global_function_sigs(self) -> dict[str, list[Sig]]:
        out: dict[str, list[Sig]] = {}
        for name, sigs in _raw_context().get("global_functions", {}).items():
            out[name] = [_decode_sig(s, {}) for s in sigs]
        return out

    def iterable_element_type(self, n: TyNominal) -> Optional[Ty]:
        bound = self._bind_nominal(n)
        if bound is None:
            return None
        spec, tvars = bound
        raw = spec.get("iterable_element")
        if raw is None:
            return None
        return _decode_ty(raw, tvars)

    def interface_methods(self, n: TyNominal) -> Optional[MethodTable]:
        spec = self._interface_spec(n.name)
        if spec is None:
            return None
        tps = tuple(spec.get("type_params", []))
        if len(tps) != len(n.args):
            return None
        tvars = {tp: arg for tp, arg in zip(tps, n.args)}
        return _decode_methods(spec.get("methods", {}), tvars)


_builtin_ctx_singleton: Optional[BuiltinContext] = None


def builtin_context() -> BuiltinContext:
    """Shared ``BuiltinContext`` (loads and validates ``context.json`` once)."""

    global _builtin_ctx_singleton
    if _builtin_ctx_singleton is None:
        _builtin_ctx_singleton = BuiltinContext()
    return _builtin_ctx_singleton


__all__ = [
    "Sig",
    "BuiltinContext",
    "builtin_context",
    "validate_context_schema",
]
