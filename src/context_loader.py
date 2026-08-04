"""Optional competition context loader."""

from __future__ import annotations

import json
import os
from typing import Any, Iterable


def empty_context() -> dict[str, list[dict[str, Any]]]:
    return {"variables": [], "functions": [], "classes": [], "interfaces": []}


def find_context_path(explicit_path: str | None = None, *, runtime_dir: str | None = None) -> str | None:
    candidates: list[str] = []
    if explicit_path:
        candidates.append(explicit_path)
    env_path = os.environ.get("CANGJIE_CONTEXT_PATH")
    if env_path:
        candidates.append(env_path)
    if runtime_dir:
        candidates.append(os.path.join(runtime_dir, "context.json"))
    candidates.append(os.path.join(os.getcwd(), "context.json"))

    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def load_context(path: str | None) -> dict[str, list[dict[str, Any]]]:
    if not path:
        return empty_context()
    with open(path, "r", encoding="utf-8") as f:
        return normalize_context(json.load(f))


def normalize_context(data: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    if not data:
        return empty_context()
    normalized = empty_context()
    normalized["variables"].extend(_normalize_variables(data.get("global_variables")))
    normalized["functions"].extend(_normalize_functions(data.get("global_functions")))
    # The public context uses ``nominals`` while some competition revisions
    # call the same section ``classes``.  Accept both without discarding either
    # section when a context happens to contain both.
    normalized["classes"].extend(_normalize_nominals(data.get("nominals")))
    normalized["classes"].extend(_normalize_nominals(data.get("classes")))
    normalized["interfaces"].extend(_normalize_interfaces(data.get("interfaces")))
    return normalized


def _iter_named_entries(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for name, entry in value.items():
            yield str(name), entry
    elif isinstance(value, list):
        for entry in value:
            if isinstance(entry, dict):
                name = entry.get("name") or entry.get("identifier") or entry.get("id")
                if name:
                    yield str(name), entry
            elif isinstance(entry, str):
                yield entry, {"name": entry}


def _normalize_variables(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name, entry in _iter_named_entries(value):
        kind = entry.get("kind") if isinstance(entry, dict) else None
        mutable = bool(entry.get("mutable", kind == "var")) if isinstance(entry, dict) else False
        result.append({"name": name, "type": _type_from_entry(entry), "mutable": mutable})
    return result


def _normalize_functions(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name, raw_entry in _iter_named_entries(value):
        # Functions and methods may map a name to an overload list.  Preserve
        # every overload instead of silently replacing the list with an empty
        # signature.
        variants = raw_entry if isinstance(raw_entry, list) else [raw_entry]
        for entry in variants:
            if not isinstance(entry, dict):
                entry = {"name": name}
            params = _normalize_params(
                entry.get("params")
                or entry.get("parameters")
                or entry.get("param_types")
            )
            defaults = entry.get("defaults") if isinstance(entry.get("defaults"), dict) else {}
            required_params = sum(
                1 for param in params if (param.get("name") or "") not in defaults
            )
            result.append({
                "name": name,
                "return_type": _format_type(
                    entry.get("return_type")
                    or entry.get("ret_type")
                    or entry.get("returns")
                    or entry.get("ret")
                    or entry.get("type")
                ),
                "param_types": [p.get("type") for p in params],
                "param_names": [p.get("name") or f"arg{i}" for i, p in enumerate(params)],
                "type_params": list(entry.get("type_params") or entry.get("generic_params") or []),
                "required_params": required_params,
            })
    return result


def _normalize_nominals(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name, entry in _iter_named_entries(value):
        if not isinstance(entry, dict):
            entry = {"name": name}
        type_params = list(entry.get("type_params") or entry.get("generic_params") or [])
        nominal_return = (
            f"{name}<{', '.join(str(item) for item in type_params)}>"
            if type_params
            else name
        )
        constructors = []
        constructor_signatures = []
        for item in _as_dict_list(entry.get("constructors") or entry.get("inits")):
            params = _normalize_params(item.get("params") or item.get("parameters"))
            constructors.append([p.get("type") for p in params])
            defaults = item.get("defaults") if isinstance(item.get("defaults"), dict) else {}
            constructor_signatures.append({
                "name": name,
                "return_type": _format_type(item.get("ret")) or nominal_return,
                "param_types": [p.get("type") for p in params],
                "param_names": [p.get("name") or f"arg{i}" for i, p in enumerate(params)],
                "type_params": type_params,
                "required_params": sum(
                    1 for param in params if (param.get("name") or "") not in defaults
                ),
            })

        methods = _normalize_functions(entry.get("instance_methods") or entry.get("methods"))
        static_methods = _normalize_functions(entry.get("static_methods"))
        fields = _normalize_field_map(entry.get("instance_fields") or entry.get("fields") or entry.get("members"))
        static_fields = _normalize_field_map(entry.get("static_fields"))
        result.append({
            "name": name,
            "kind": entry.get("kind") or entry.get("decl_kind") or "class",
            "type_params": type_params,
            "fields": fields,
            "static_fields": static_fields,
            "constructors": constructors,
            "constructor_signatures": constructor_signatures,
            "methods": methods,
            "static_methods": static_methods,
            "supers": [_format_type(item) or "" for item in entry.get("supers", [])],
            "iterable_element": _format_type(entry.get("iterable_element")),
        })
    return result


def _normalize_interfaces(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name, entry in _iter_named_entries(value):
        if not isinstance(entry, dict):
            entry = {"name": name}
        result.append({
            "name": name,
            "kind": "interface",
            "type_params": list(entry.get("type_params") or entry.get("generic_params") or []),
            "methods": _normalize_functions(entry.get("methods")),
            "supers": [_format_type(item) or "" for item in entry.get("supers", [])],
        })
    return result


def _normalize_params(value: Any) -> list[dict[str, str | None]]:
    params: list[dict[str, str | None]] = []
    if value is None:
        return params
    if isinstance(value, dict):
        for name, param in value.items():
            params.append({"name": str(name), "type": _type_from_entry(param)})
        return params
    if not isinstance(value, list):
        return params
    for idx, param in enumerate(value):
        if isinstance(param, str):
            if ":" in param:
                name, declared_type = param.split(":", 1)
                params.append({"name": name.strip(), "type": declared_type.strip()})
            else:
                params.append({"name": f"arg{idx}", "type": param})
        elif isinstance(param, dict):
            params.append({"name": param.get("name") or param.get("identifier") or f"arg{idx}", "type": _type_from_entry(param)})
    return params


def _normalize_field_map(value: Any) -> dict[str, str]:
    fields: dict[str, str] = {}
    for name, entry in _iter_named_entries(value):
        fields[name] = _type_from_entry(entry) or ""
    return fields


def _type_from_entry(entry: Any) -> str | None:
    if isinstance(entry, str):
        return entry
    if not isinstance(entry, dict):
        return None
    if "type" in entry:
        return _format_type(entry.get("type"))
    if "declared_type" in entry:
        return _format_type(entry.get("declared_type"))
    if "variable_type" in entry:
        return _format_type(entry.get("variable_type"))
    if "ty" in entry:
        return _format_type(entry.get("ty"))
    return _format_type(entry)


def _format_type(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if not isinstance(value, dict):
        return str(value)
    if "tparam" in value:
        return str(value["tparam"])
    if "nominal" in value:
        name = str(value["nominal"])
        args = [_format_type(arg) or "" for arg in value.get("args", [])]
        args = [arg for arg in args if arg]
        return f"{name}<{', '.join(args)}>" if args else name
    if "tuple" in value:
        parts = [_format_type(item) or "" for item in value.get("tuple", [])]
        return f"({', '.join(part for part in parts if part)})"
    if "function" in value and isinstance(value["function"], dict):
        fn = value["function"]
        params = [_format_type(item) or "" for item in fn.get("params", [])]
        ret = _format_type(fn.get("ret")) or "Unit"
        return f"({', '.join(part for part in params if part)}) -> {ret}"
    return None


def _as_dict_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [item for _name, item in _iter_named_entries(value) if isinstance(item, dict)]
    return []
