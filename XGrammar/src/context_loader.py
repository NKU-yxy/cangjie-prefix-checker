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
    normalized["classes"].extend(_normalize_nominals(data.get("nominals")))
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
    return [{"name": name, "type": _type_from_entry(entry)} for name, entry in _iter_named_entries(value)]


def _normalize_functions(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name, entry in _iter_named_entries(value):
        if not isinstance(entry, dict):
            entry = {"name": name}
        params = _normalize_params(entry.get("params") or entry.get("parameters") or entry.get("param_types"))
        result.append({
            "name": name,
            "return_type": entry.get("return_type") or entry.get("ret_type") or entry.get("returns") or entry.get("type"),
            "param_types": [p.get("type") for p in params],
            "param_names": [p.get("name") or f"arg{i}" for i, p in enumerate(params)],
            "type_params": list(entry.get("type_params") or entry.get("generic_params") or []),
        })
    return result


def _normalize_nominals(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for name, entry in _iter_named_entries(value):
        if not isinstance(entry, dict):
            entry = {"name": name}
        constructors = [
            [p.get("type") for p in _normalize_params(item.get("params") or item.get("parameters"))]
            for item in _as_dict_list(entry.get("constructors") or entry.get("inits"))
        ]
        result.append({
            "name": name,
            "kind": entry.get("kind") or entry.get("decl_kind") or "class",
            "type_params": list(entry.get("type_params") or entry.get("generic_params") or []),
            "fields": _normalize_field_map(entry.get("fields") or entry.get("members")),
            "constructors": constructors,
            "methods": _normalize_functions(entry.get("methods")),
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
    return entry.get("type") or entry.get("declared_type") or entry.get("variable_type") or entry.get("ty")


def _as_dict_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        return [item for _name, item in _iter_named_entries(value) if isinstance(item, dict)]
    return []
