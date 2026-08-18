#!/usr/bin/env python3
"""Export an official context JSON into the canonical Context IR (context-ir-v1).

The canonical IR is the single source of truth for the runtime model: it is
exactly what ``src/context_loader.normalize_context()`` produces (the same
normalization that writes ``generated/context.bin``), serialized
deterministically.  Comparing it against ``./solution --dump-context-ir``
(see tools/compare_context_ir.py) audits that the runtime model and the
official context agree member-for-member (V14_Plan §5.4).

Canonical schema (context-ir-v1):

    {
      "schema": "context-ir-v1",
      "globals":  {"<name>": "<type-string>"},
      "functions": {"<name>": [<sig>, ...]},        // global function overloads
      "nominals": {"<name>": {
          "is_interface": bool,
          "type_params": ["T", ...],
          "supers": ["<type-string>", ...],
          "fields": {"<name>": "<type-string>"},
          "static_fields": {"<name>": "<type-string>"},
          "methods": {"<name>": [<sig>, ...]},
          "static_methods": {"<name>": [<sig>, ...]},
          "constructors": [<sig>, ...]
      }}
    }

    <sig> = {"name", "return_type", "type_params",
             "param_names", "param_types", "required_params"}

Type strings are the loader's normalized spellings ("Optional<T>", "(K, V)",
"(Int64, Int64) -> Bool").  Overload lists keep the official declaration
order; name maps are sorted for deterministic output.

Usage:
    python3 tools/export_official_context_ir.py \
        official-reference/typechecker/typechecker/context_final.json \
        /tmp/official_ir.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.context_loader import load_context  # noqa: E402

SCHEMA = "context-ir-v1"
SIG_KEYS = ("name", "return_type", "type_params", "param_names", "param_types",
            "required_params")


def _canonical_sig(sig: dict[str, object]) -> dict[str, object]:
    return {key: sig.get(key) for key in SIG_KEYS}


def _signature_map(flat: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for sig in flat:
        grouped.setdefault(str(sig.get("name")), []).append(_canonical_sig(sig))
    return dict(sorted(grouped.items()))


def _nominal_entry(info: dict[str, object], is_interface: bool) -> dict[str, object]:
    return {
        "is_interface": is_interface,
        "type_params": [str(item) for item in (info.get("type_params") or [])],
        "supers": [str(item) for item in (info.get("supers") or [])],
        "fields": {str(key): str(value) for key, value in (info.get("fields") or {}).items()},
        "static_fields": {str(key): str(value) for key, value in (info.get("static_fields") or {}).items()},
        "methods": _signature_map(list(info.get("methods") or [])),
        "static_methods": _signature_map(list(info.get("static_methods") or [])),
        "constructors": [_canonical_sig(sig) for sig in (info.get("constructor_signatures") or [])],
    }


def canonical_ir(normalized: dict[str, list[dict[str, object]]]) -> dict[str, object]:
    """Serialize the normalized context (loader output) as context-ir-v1."""
    globals_: dict[str, str] = {}
    for variable in normalized.get("variables") or []:
        name = str(variable.get("name") or "")
        if name:
            globals_[name] = str(variable.get("type") or "")

    nominals: dict[str, object] = {}
    for cls in normalized.get("classes") or []:
        name = str(cls.get("name") or "")
        if name:
            nominals[name] = _nominal_entry(cls, is_interface=False)
    for interface in normalized.get("interfaces") or []:
        name = str(interface.get("name") or "")
        if name:
            nominals[name] = _nominal_entry(interface, is_interface=True)

    return {
        "schema": SCHEMA,
        "globals": dict(sorted(globals_.items())),
        "functions": _signature_map(list(normalized.get("functions") or [])),
        "nominals": dict(sorted(nominals.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export an official context JSON into the canonical Context IR."
    )
    parser.add_argument("input", type=Path, help="official context JSON (context_final.json)")
    parser.add_argument("output", type=Path, help="canonical IR JSON output")
    args = parser.parse_args()

    normalized = load_context(str(args.input))
    ir = canonical_ir(normalized)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(ir, indent=1, ensure_ascii=False) + "\n", "utf-8")

    n_nominals = len(ir["nominals"])
    n_functions = sum(len(v) for v in ir["functions"].values())
    n_members = 0
    for info in ir["nominals"].values():
        n_members += len(info["fields"]) + len(info["static_fields"])
        n_members += sum(len(v) for v in info["methods"].values())
        n_members += sum(len(v) for v in info["static_methods"].values())
        n_members += len(info["constructors"])
    print(f"exported {args.output}: {n_nominals} nominals, "
          f"{len(ir['functions'])} global functions ({n_functions} overloads), "
          f"{n_members} member signatures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
