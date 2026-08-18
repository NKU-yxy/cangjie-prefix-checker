#!/usr/bin/env python3
"""Compare the official canonical Context IR against the runtime dump.

Usage:
    ./solution --dump-context-ir > /tmp/runtime_ir.json
    python3 tools/compare_context_ir.py /tmp/official_ir.json /tmp/runtime_ir.json

Every difference is classified (V14_Plan §5.4):

    EXPECTED_BUILTIN           runtime-only member: language intrinsic the
                               official context does not cover (must be kept
                               per §5.2, otherwise a BUG_OVERLOAD-style leak)
    EXPECTED_DEVIATION         adjudicated deviation (F1: Array.first/last are
                               fields in the runtime per the official F1
                               ruling, zero-arg methods in the raw JSON)
    BUG_MEMBER_KIND            field vs method kind mismatch
    BUG_DISPATCH               instance vs static dispatch mismatch
    BUG_PARAMS                 parameter list (names/types/required) mismatch
    BUG_RETURN                 return/field type mismatch
    BUG_GENERIC_SUBSTITUTION   type-parameter list mismatch
    BUG_INHERITANCE            supers mismatch
    BUG_OVERLOAD               overload-set mismatch (count, order, or shape)
    BUG_MISSING_MEMBER         official member absent from the runtime model

Gate: the exit code is 0 iff no BUG_* difference remains; EXPECTED_BUILTIN and
EXPECTED_DEVIATION are informational.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# (owner, member) pairs where the runtime deliberately deviates from the raw
# official JSON.  F1 (officially adjudicated): Array.first/last are zero-arg
# methods returning Optional<T> in the JSON; the runtime keeps them as
# Optional<T> instance fields (V14_Plan §1.1 mandates keeping this).
EXPECTED_DEVIATIONS = {
    ("Array", "first"): "F1 adjudication: field Optional<T> (JSON: zero-arg method)",
    ("Array", "last"): "F1 adjudication: field Optional<T> (JSON: zero-arg method)",
}


def _sig_tuple(sig: dict) -> tuple:
    return (
        sig.get("name", ""),
        sig.get("return_type", ""),
        tuple(sig.get("type_params") or []),
        tuple(sig.get("param_names") or []),
        tuple(sig.get("param_types") or []),
        int(sig.get("required_params") or 0),
    )


def _sig_dims(a: tuple, b: tuple) -> str:
    """First differing dimension between two sig tuples."""
    if a[2] != b[2]:
        return "BUG_GENERIC_SUBSTITUTION"
    if a[4] != b[4] or a[3] != b[3] or a[5] != b[5]:
        return "BUG_PARAMS"
    if a[1] != b[1]:
        return "BUG_RETURN"
    return "BUG_OVERLOAD"


class DiffCollector:
    def __init__(self) -> None:
        self.diffs: list[tuple[str, str]] = []  # (category, detail)

    def add(self, category: str, detail: str) -> None:
        self.diffs.append((category, detail))

    def compare_signature_lists(self, owner: str, member: str, official: list, runtime: list) -> None:
        if official == runtime:
            return
        key = (owner, member)
        if key in EXPECTED_DEVIATIONS:
            self.add("EXPECTED_DEVIATION", f"{owner}.{member}: {EXPECTED_DEVIATIONS[key]}")
            return
        if len(official) != len(runtime):
            self.add("BUG_OVERLOAD", f"{owner}.{member}: {len(official)} official overloads "
                     f"vs {len(runtime)} runtime")
            return
        for index, (osig, rsig) in enumerate(zip(official, runtime)):
            ot, rt = _sig_tuple(osig), _sig_tuple(rsig)
            if ot != rt:
                self.add(_sig_dims(ot, rt),
                         f"{owner}.{member}[{index}]: official {list(ot)} vs runtime {list(rt)}")
                return

    def compare_members(self, owner: str, official: dict, runtime: dict, section: str) -> None:
        if official == runtime:
            return
        official_names = set(official)
        runtime_names = set(runtime)
        for name in sorted(official_names - runtime_names):
            self.add("BUG_MISSING_MEMBER",
                     f"{owner}.{name} ({section}): official only")
        for name in sorted(runtime_names - official_names):
            self.add("EXPECTED_BUILTIN",
                     f"{owner}.{name} ({section}): runtime-only")
        for name in sorted(official_names & runtime_names):
            o, r = official[name], runtime[name]
            if o == r:
                continue
            key = (owner, name)
            if key in EXPECTED_DEVIATIONS:
                self.add("EXPECTED_DEVIATION", f"{owner}.{name}: {EXPECTED_DEVIATIONS[key]}")
                continue
            if isinstance(o, list) and isinstance(r, list):
                self.compare_signature_lists(owner, name, o, r)
            elif isinstance(o, str) and isinstance(r, str):
                self.add("BUG_RETURN", f"{owner}.{name} ({section}): "
                         f"official {o!r} vs runtime {r!r}")
            else:
                self.add("BUG_MEMBER_KIND", f"{owner}.{name} ({section}): "
                         f"official {type(o).__name__} vs runtime {type(r).__name__}")


def compare(ir_official: dict, ir_runtime: dict, collector: DiffCollector) -> None:
    # --- globals ---------------------------------------------------------
    collector.compare_members("<global>", ir_official.get("globals") or {},
                              ir_runtime.get("globals") or {}, "global")

    # --- global functions ------------------------------------------------
    collector.compare_members("<global>", ir_official.get("functions") or {},
                              ir_runtime.get("functions") or {}, "function")

    # --- nominals ----------------------------------------------------------
    official_nominals = ir_official.get("nominals") or {}
    runtime_nominals = ir_runtime.get("nominals") or {}
    for name in sorted(set(official_nominals) - set(runtime_nominals)):
        collector.add("BUG_MISSING_MEMBER", f"nominal {name}: official only")
    for name in sorted(set(runtime_nominals) - set(official_nominals)):
        collector.add("EXPECTED_BUILTIN", f"nominal {name}: runtime-only")
    for name in sorted(set(official_nominals) & set(runtime_nominals)):
        o, r = official_nominals[name], runtime_nominals[name]
        if o == r:
            continue
        if bool(o.get("is_interface")) != bool(r.get("is_interface")):
            collector.add("BUG_MEMBER_KIND",
                          f"nominal {name}: official interface={o.get('is_interface')} "
                          f"vs runtime interface={r.get('is_interface')}")
        if (o.get("type_params") or []) != (r.get("type_params") or []):
            collector.add("BUG_GENERIC_SUBSTITUTION",
                          f"nominal {name} type_params: official {o.get('type_params')} "
                          f"vs runtime {r.get('type_params')}")
        if sorted(o.get("supers") or []) != sorted(r.get("supers") or []):
            collector.add("BUG_INHERITANCE",
                          f"nominal {name} supers: official {sorted(o.get('supers') or [])} "
                          f"vs runtime {sorted(r.get('supers') or [])}")
        # Cross-section kind deviation: a member that is a method on one side
        # and a field on the other (F1's Array.first/last).  Report once and
        # exclude the names from the section-level passes.
        cross_section: set[str] = set()
        for member in sorted((set(o.get("methods") or {}) & set(r.get("fields") or {})) |
                             (set(o.get("fields") or {}) & set(r.get("methods") or {}))):
            in_o_methods = member in (o.get("methods") or {})
            in_o_fields = member in (o.get("fields") or {})
            key = (name, member)
            if key in EXPECTED_DEVIATIONS:
                collector.add("EXPECTED_DEVIATION",
                              f"{name}.{member}: {EXPECTED_DEVIATIONS[key]}")
            else:
                collector.add("BUG_MEMBER_KIND",
                              f"{name}.{member}: official "
                              f"{'method' if in_o_methods else 'field'} vs runtime "
                              f"{'method' if member in (r.get('methods') or {}) else 'field'}"
                              f" (official field={in_o_fields})")
            cross_section.add(member)
        o_fields = {k: v for k, v in (o.get("fields") or {}).items() if k not in cross_section}
        r_fields = {k: v for k, v in (r.get("fields") or {}).items() if k not in cross_section}
        o_methods = {k: v for k, v in (o.get("methods") or {}).items() if k not in cross_section}
        r_methods = {k: v for k, v in (r.get("methods") or {}).items() if k not in cross_section}
        collector.compare_members(name, o_fields, r_fields, "field")
        collector.compare_members(name, o.get("static_fields") or {},
                                  r.get("static_fields") or {}, "static field")
        collector.compare_members(name, o_methods, r_methods, "method")
        collector.compare_members(name, o.get("static_methods") or {},
                                  r.get("static_methods") or {}, "static method")
        # dispatch: instance member in one side, static member in the other
        for member in sorted((set(o.get("methods") or {}) | set(r.get("methods") or {})) &
                             (set(o.get("static_methods") or {}) | set(r.get("static_methods") or {}))):
            in_o_instance = member in (o.get("methods") or {})
            in_r_instance = member in (r.get("methods") or {})
            if in_o_instance != in_r_instance:
                collector.add("BUG_DISPATCH",
                              f"{name}.{member}: official "
                              f"{'instance' if in_o_instance else 'static'} vs runtime "
                              f"{'instance' if in_r_instance else 'static'}")
        if (o.get("constructors") or []) != (r.get("constructors") or []):
            collector.compare_signature_lists(name, "<ctor>", o.get("constructors") or [],
                                              r.get("constructors") or [])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("official", type=Path, help="canonical IR from export_official_context_ir.py")
    parser.add_argument("runtime", type=Path, help="IR from ./solution --dump-context-ir")
    args = parser.parse_args()

    ir_official = json.loads(args.official.read_text("utf-8"))
    ir_runtime = json.loads(args.runtime.read_text("utf-8"))
    if ir_runtime.get("schema") != ir_official.get("schema"):
        print(f"schema mismatch: official {ir_official.get('schema')} "
              f"vs runtime {ir_runtime.get('schema')}", file=sys.stderr)
        return 2

    collector = DiffCollector()
    compare(ir_official, ir_runtime, collector)

    counts: dict[str, int] = {}
    for category, detail in collector.diffs:
        counts[category] = counts.get(category, 0) + 1
        print(f"{category:<28} {detail}")
    print()
    for category in sorted(counts):
        print(f"{category}: {counts[category]}")
    bugs = {c: n for c, n in counts.items() if c.startswith("BUG_")}
    if bugs:
        print(f"\nGATE FAILED: {sum(bugs.values())} BUG_* differences "
              f"({json.dumps(bugs, sort_keys=True)})")
        return 1
    print("\nGATE PASSED: no BUG_* differences")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
