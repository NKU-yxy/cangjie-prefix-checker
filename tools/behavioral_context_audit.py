#!/usr/bin/env python3
"""V15 Patch 2: Behavioral Context Audit (V15_Plan §6.1–6.3).

For every member of every nominal / interface / global function in the
official FINAL context, generate the four behavioral probes of §6.1:

    A: let value: R = x.member          (value use, declared type R)
    B: let value: R = x.member(<args>)  (call use)
    C: let f: (P...) -> R = x.member    (function reference)
    D: let value: R2 = x.member.<postfix>  (postfix continuation)

and adjudicate each probe twice:

    official : the official typechecker (CANGJIE_TYPECHECKER_CONTEXT=final)
    runtime  : the v15 solution binary (token harness, cl100k_base)

Classify official behavior per the §6.1 truth table
(A ok + B not-callable + C fail -> field; A fail + B ok + C ok -> method;
 A ok + B ok -> callable field / special; all fail -> error), compare with
the runtime model's member grouping, and emit:

    results/official_behavioral_context.json
    results/runtime_behavioral_context.json
    results/behavioral_context_diff.md

Gate (V15_Plan Patch 2): runtime accept/reject == official accept/reject on
every probe; every raw-JSON-vs-official-behavior discrepancy listed.

Usage:
    python3 tools/behavioral_context_audit.py \
        --solution ./solution \
        --out-dir results
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import tiktoken

ROOT = Path(__file__).resolve().parents[1]
OUTER = ROOT.parent  # cloud-code-cli-api (holds official-reference)

OFFICIAL_CONTEXT = (
    OUTER / "official-reference" / "typechecker" / "typechecker" / "context_final.json"
)
PROJECT_CONTEXT = ROOT / "context.json"
TYPECHECKER_DIR = OUTER / "official-reference" / "typechecker"

# Concrete receiver per nominal: (binding_expr, declared_type).  Every probe
# binds the receiver to an IDENTIFIER first — the runtime cannot resolve
# member access on non-identifier receivers (literal/call receivers), which
# would mask the member-behavior under test.  The literal receiver form is
# audited separately (receiver_shape section).
RECEIVERS: dict[str, tuple[str, str]] = {
    "Array": ("[1, 2, 3]", "Array<Int64>"),
    "ArrayList": ("ArrayList<Int64>()", "ArrayList<Int64>"),
    "ArrayStack": ("ArrayStack<Int64>()", "ArrayStack<Int64>"),
    "ArrayDeque": ("ArrayDeque<Int64>()", "ArrayDeque<Int64>"),
    "HashMap": ('HashMap<String, Int64>()', 'HashMap<String, Int64>'),
    "HashSet": ('HashSet<String>()', 'HashSet<String>'),
    "String": ('"abc"', "String"),
    # The Optional receiver relies on the official auto-apply of zero-arg
    # first/last — itself one of the audited behaviors.
    # Optional has no constructor; the only legal receiver is a `.first`
    # read.  Bound in two steps so the runtime resolves `a.first` (a field
    # in the runtime model) instead of failing on the member chain.
    "Optional": ("Array<Int64>(1, 0).first", "Optional<Int64>"),
    "KeysView": ('HashMap<String, Int64>().keys()', 'KeysView<String>'),
    "ValuesView": ('HashMap<String, Int64>().values()', 'ValuesView<Int64>'),
    "Range": ("0..10", "Range<Int64>"),
}

# Interface members resolve through a concrete implementor.
INTERFACE_RECEIVERS: dict[str, tuple[str, str]] = {
    "Stack": ("ArrayStack<Int64>()", "ArrayStack<Int64>"),
    "Deque": ("ArrayDeque<Int64>()", "ArrayDeque<Int64>"),
    "Collection": ("ArrayList<Int64>()", "ArrayList<Int64>"),
    "Iterable": ("[1, 2, 3]", "Array<Int64>"),
    # Equatable<T> / Hashable have no concrete implementor among the final
    # nominals (checked against context_final.json supers); their members
    # cannot be probed through a receiver.
}

NO_RECEIVER = {"Equatable", "Hashable"}

# Default type-variable bindings follow the receiver's concrete instantiation.
TVARS: dict[str, dict[str, str]] = {
    "HashSet": {"T": "String"},
    "HashMap": {"K": "String", "V": "Int64"},
    "KeysView": {"K": "String"},
    "ValuesView": {"V": "Int64"},
}
DEFAULT_TVARS = {"T": "Int64", "K": "String", "V": "Int64"}

# Per-parameter-type argument factory: valid literal for the concrete type.
ARGUMENTS: dict[str, str] = {
    "Int64": "1",
    "Float64": "1.0",
    "Bool": "true",
    "String": '"x"',
    "Unit": "",
    "Array<Int64>": "[1, 2]",
    "Array<String>": '["x"]',
    "ArrayList<Int64>": "ArrayList<Int64>()",
    "HashMap<String, Int64>": 'HashMap<String, Int64>()',
    "HashSet<String>": 'HashSet<String>()',
    "Optional<Int64>": "Array<Int64>(1, 0).first",
    "KeysView<String>": 'HashMap<String, Int64>().keys()',
    "ValuesView<Int64>": 'HashMap<String, Int64>().values()',
    "Range<Int64>": "0..10",
    "(String, Int64)": '("k", 1)',
}

# Primitive ret types that the official checker (like the runtime) supports
# .toString() on — used for the D postfix probe.
TOSTRING_PRIMITIVES = {"Int64", "Float64", "Bool"}


def fmt_type(t, tvars: dict[str, str]) -> str:
    """Format a context type JSON node as Cangjie source text."""
    if isinstance(t, str):
        return t
    if isinstance(t, dict):
        if "nominal" in t:
            args = [fmt_type(a, tvars) for a in t.get("args", [])]
            return t["nominal"] + (f"<{', '.join(args)}>" if args else "")
        if "tparam" in t:
            return tvars.get(t["tparam"], t["tparam"])
        if "tuple" in t:
            return "(" + ", ".join(fmt_type(e, tvars) for e in t["tuple"]) + ")"
    raise ValueError(f"unhandled type node: {t!r}")


def substitute(text: str, tvars: dict[str, str]) -> str:
    import re
    for name, value in tvars.items():
        text = re.sub(r"\b" + re.escape(name) + r"\b", value, text)
    return text


def tvars_for(owner: str) -> dict[str, str]:
    return TVARS.get(owner, DEFAULT_TVARS)


def program(stmt: str, header: str | None = None) -> str:
    """Probe program: `main(): Unit { [header] <stmt> }`.

    No println suffix: a trailing print of the probe value would shift the
    official error site to the println call (calibration finding).
    """
    body = f"    {header}\n    {stmt}" if header else f"    {stmt}"
    return f"main(): Unit {{\n{body}\n}}\n"


# ---------------------------------------------------------------------------
# Official adjudication
# ---------------------------------------------------------------------------

def load_official_checker():
    os.environ["CANGJIE_TYPECHECKER_CONTEXT"] = "final"
    sys.path.insert(0, str(TYPECHECKER_DIR))
    from typechecker.checker import typecheck_tree  # noqa: E402
    from typechecker.errors import TypeCheckError  # noqa: E402
    from typechecker.parser import parse  # noqa: E402
    from lark.exceptions import UnexpectedInput  # noqa: E402

    def adjudicate(src: str) -> dict:
        try:
            typecheck_tree(parse(src))
            return {"verdict": "ACCEPT", "code": ""}
        except TypeCheckError as error:
            diag = getattr(error, "diagnostic", None)
            code = getattr(diag, "code", "?") if diag is not None else "?"
            return {"verdict": "REJECT", "code": code,
                    "msg": str(error)[:120]}
        except UnexpectedInput as error:
            return {"verdict": "PARSE", "code": "", "msg": str(error)[:120]}
        except Exception as error:  # noqa: BLE001
            return {"verdict": "EXC", "code": type(error).__name__,
                    "msg": str(error)[:120]}

    return adjudicate


# ---------------------------------------------------------------------------
# Runtime adjudication (the v15 solution binary)
# ---------------------------------------------------------------------------

class RuntimeProber:
    def __init__(self, solution: Path):
        # pathlib strips "./" -> bare name -> execvp PATH lookup.  Resolve so
        # the binary is always launched by absolute path.
        self.solution = str(Path(solution).resolve())
        self.enc = tiktoken.get_encoding("cl100k_base")

    def adjudicate(self, src: str) -> dict:
        ids = self.enc.encode(src)
        proc = subprocess.Popen(
            [self.solution], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        assert proc.stdin and proc.stdout
        fire = None
        try:
            for idx, tok in enumerate(ids):
                proc.stdin.write(f"{tok}\n")
                proc.stdin.flush()
                line = proc.stdout.readline()
                if line.strip() == "1":
                    fire = idx
                    break
        finally:
            proc.terminate()
            proc.wait()
        return {"accept": fire is None, "fire": fire}


# ---------------------------------------------------------------------------
# Probe generation
# ---------------------------------------------------------------------------

def valid_arg_for(t: str) -> str | None:
    return ARGUMENTS.get(t)


def postfix_for(rtype: str, ctx_raw: dict) -> tuple[str, str] | None:
    """Pick (postfix_expr, result_type) for the D probe, or None.

    Preference: a field of R (plain member read), then a zero-arg method
    (call), then the official .toString() surface for primitives.
    """
    if rtype in TOSTRING_PRIMITIVES:
        return ".toString()", "String"
    if rtype == "String":
        return ".size", "Int64"
    if rtype in ("Unit",):
        return None
    nominal = ctx_raw["nominals"].get(rtype)
    if nominal is None:
        return None
    fields = nominal.get("instance_fields") or {}
    if fields:
        name = next(iter(fields))
        return f".{name}", fmt_type(fields[name], DEFAULT_TVARS)
    for mname, spec in (nominal.get("instance_methods") or {}).items():
        sigs = spec if isinstance(spec, list) else [spec]
        for sig in sigs:
            if not sig.get("params"):
                return f".{mname}()", fmt_type(sig["ret"], DEFAULT_TVARS)
    return None


def build_member_probes(owner, member, kind, sigs, recv_name, recv_decl,
                        tvars, ctx_raw):
    """Return list of (probe_id, stmt, header) for one member's overload set.

    `recv_name` is the bound identifier ("" for globals / statics accessed
    through the type name); `recv_decl` is the binding statement.

    Calibration findings encoded here:
    - D postfixes the member VALUE.  For a method the value is the call
      result, so D must call first (`recv.m(args).postfix`); postfixing the
      bare method name would chain onto the function value and always fail
      with E_SYNTH_NO_MEMBER.
    - generic signatures (min/max) are uninferable in the official checker:
      flagged generic_uninferable, verdicts still recorded.
    """
    out = []
    primary = sigs[0]
    ret = fmt_type(primary["ret"], tvars)
    params = [fmt_type(p["type"], tvars) for p in primary.get("params", [])]
    fnty = f"({', '.join(params)}) -> {ret}" if params else f"() -> {ret}"
    expr = f"{recv_name}.{member}" if recv_name else member
    is_value = kind in ("field", "static_field")
    generic = bool(primary.get("type_params"))
    if is_value:
        call_expr = None  # fields are read, not called (B probes the call)
    else:
        args = ", ".join(valid_arg_for(p) or "0" for p in params)
        call_expr = f"{expr}({args})"
    note = "generic_uninferable" if generic else ""
    # A: value use with the declared result type (field-like read, or method
    # read as a function value fails unless auto-applied).
    out.append(("A", f"let value: {ret} = {expr}", recv_decl))
    # B: call use — methods get valid args; fields probe the call form.
    out.append(("B", f"let value: {ret} = {expr}()" if is_value else
                f"let value: {ret} = {call_expr}", recv_decl))
    # C: function reference with the function type.
    out.append(("C", f"let f: {fnty} = {expr}", recv_decl))
    # D: postfix continuation of the member value (call result for methods).
    postfix = postfix_for(ret, ctx_raw)
    if postfix is not None:
        post_expr, post_ret = postfix
        base = call_expr if call_expr is not None else expr
        out.append(("D", f"let value: {post_ret} = {base}{post_expr}",
                    recv_decl))
    else:
        out.append(("D", None, None))
    # Overload dimension: one extra B per additional overload shape.
    for index, sig in enumerate(sigs[1:], start=1):
        oparams = [fmt_type(p["type"], tvars) for p in sig.get("params", [])]
        oret = fmt_type(sig["ret"], tvars)
        oargs = ", ".join(valid_arg_for(p) or "0" for p in oparams)
        out.append((f"B_overload_{index}",
                    f"let value: {oret} = {expr}({oargs})", recv_decl))
    return out


def enumerate_members(ctx_raw) -> list[dict]:
    """Yield the full member list with receiver/kind/sigs resolved.

    Each member carries `recv_name` (the bound identifier used in probes,
    "" when accessed via the type name directly or a global) and `recv_decl`
    (the binding statement, or None).
    """
    members = []

    def bind(owner: str, for_static: bool) -> tuple[str, str | None]:
        expr, rtype = RECEIVERS[owner]
        if for_static:
            return "", None  # Owner.member — no binding needed
        if owner == "Optional":
            # Two-step binding: `let a: Array<Int64> = Array<Int64>(1, 0)`
            # then `let recv: Optional<Int64> = a.first` — the runtime
            # resolves the plain identifier receiver `a`.
            return ("recv", "let a: Array<Int64> = Array<Int64>(1, 0)\n"
                    "    let recv: Optional<Int64> = a.first")
        return "recv", f"let recv: {rtype} = {expr}"

    for owner, info in ctx_raw["nominals"].items():
        tvars = tvars_for(owner)
        if owner not in RECEIVERS:
            continue
        recv_name, recv_decl = bind(owner, for_static=False)
        for fname, ftype in (info.get("instance_fields") or {}).items():
            members.append({"owner": owner, "member": fname, "kind": "field",
                            "sigs": [{"type_params": [], "params": [],
                                      "ret": ftype}],
                            "recv_name": recv_name, "recv_decl": recv_decl,
                            "tvars": tvars})
        for fname, ftype in (info.get("static_fields") or {}).items():
            members.append({"owner": owner, "member": fname,
                            "kind": "static_field",
                            "sigs": [{"type_params": [], "params": [],
                                      "ret": ftype}],
                            "recv_name": owner, "recv_decl": None,
                            "tvars": tvars})
        for mname, spec in (info.get("instance_methods") or {}).items():
            sigs = spec if isinstance(spec, list) else [spec]
            members.append({"owner": owner, "member": mname, "kind": "method",
                            "sigs": sigs, "recv_name": recv_name,
                            "recv_decl": recv_decl, "tvars": tvars})
        for mname, spec in (info.get("static_methods") or {}).items():
            sigs = spec if isinstance(spec, list) else [spec]
            members.append({"owner": owner, "member": mname,
                            "kind": "static_method",
                            "sigs": sigs, "recv_name": owner,
                            "recv_decl": None, "tvars": tvars})
    for iface, info in ctx_raw["interfaces"].items():
        if iface in NO_RECEIVER:
            continue
        if iface not in INTERFACE_RECEIVERS:
            continue
        expr, rtype = INTERFACE_RECEIVERS[iface]
        tvars = tvars_for(iface)
        recv_name, recv_decl = "recv", f"let recv: {rtype} = {expr}"
        for mname, spec in info["methods"].items():
            sigs = spec if isinstance(spec, list) else [spec]
            members.append({"owner": iface, "member": mname,
                            "kind": "interface_method",
                            "sigs": sigs, "recv_name": recv_name,
                            "recv_decl": recv_decl, "tvars": tvars})
    for gname, sigs in ctx_raw["global_functions"].items():
        sigs = sigs if isinstance(sigs, list) else [sigs]
        members.append({"owner": "<global>", "member": gname,
                        "kind": "function", "sigs": sigs, "recv_name": "",
                        "recv_decl": None, "tvars": DEFAULT_TVARS})
    return members


# ---------------------------------------------------------------------------
# Classification (§6.1 truth table)
# ---------------------------------------------------------------------------

def classify_official(a: dict, b: dict, c: dict) -> tuple[str, str]:
    """Return (behavior_kind, note)."""
    a_ok = a["verdict"] == "ACCEPT"
    b_ok = b["verdict"] == "ACCEPT"
    b_not_callable = b.get("code") == "E_SYNTH_NOT_CALLABLE"
    c_ok = c["verdict"] == "ACCEPT"
    if a_ok and not b_ok and b_not_callable and not c_ok:
        return "field", ""
    if not a_ok and b_ok and c_ok:
        return "method", ""
    if a_ok and b_ok:
        return "callable_field", "A and B both accepted"
    if not a_ok and not b_ok and not c_ok:
        return "error", f"A={a['code']} B={b['code']} C={c['code']}"
    return "special", f"A={a['code'] if not a_ok else 'ok'} B={b['code'] if not b_ok else 'ok'} C={c['code'] if not c_ok else 'ok'}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--solution", type=Path, required=True,
                        help="path to the v15 solution binary")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "results")
    parser.add_argument("--limit", type=int, default=0,
                        help="probe only the first N members (debug)")
    args = parser.parse_args()

    ctx_raw = json.loads(OFFICIAL_CONTEXT.read_text("utf-8"))
    project_raw = json.loads(PROJECT_CONTEXT.read_text("utf-8"))
    members = enumerate_members(ctx_raw)
    if args.limit:
        members = members[:args.limit]

    adjudicate = load_official_checker()
    runtime = RuntimeProber(args.solution)

    skipped = []
    official_rows, runtime_rows = [], []
    mismatches = []

    for member in members:
        owner, mname, kind = (
            member["owner"], member["member"], member["kind"]
        )
        tvars = member["tvars"]
        probes = build_member_probes(
            owner, mname, kind, member["sigs"], member["recv_name"],
            member["recv_decl"], tvars, ctx_raw
        )
        raw_kind = {
            "field": "field", "static_field": "static_field",
            "method": "method", "static_method": "static_method",
            "interface_method": "method", "function": "function",
        }[kind]

        # Also mark members that are both field AND method in the raw JSON
        # (HashMap.size / HashMap.capacity).
        info = ctx_raw["nominals"].get(owner) or {}
        both = (mname in (info.get("instance_fields") or {}) and
                mname in (info.get("instance_methods") or {}))
        if both:
            raw_kind = "field+method"

        o_result = {"owner": owner, "member": mname, "raw_json_kind": raw_kind,
                    "probes": {}}
        r_result = {"owner": owner, "member": mname, "runtime_kind": raw_kind,
                    "probes": {}}
        for pid, stmt, header in probes:
            if stmt is None:
                o_result["probes"][pid] = {"skipped": "no postfix member"}
                r_result["probes"][pid] = {"skipped": "no postfix member"}
                continue
            src = program(stmt, header)
            o = adjudicate(src)
            r = runtime.adjudicate(src)
            o_result["probes"][pid] = {"verdict": o["verdict"], "code": o["code"]}
            r_result["probes"][pid] = {"accept": r["accept"], "fire": r["fire"]}
            # Gate comparison: accept/reject equivalence per probe.
            official_accept = o["verdict"] == "ACCEPT"
            if official_accept != r["accept"]:
                mismatches.append({
                    "owner": owner, "member": mname, "probe": pid,
                    "official": o["verdict"], "official_code": o["code"],
                    "runtime_accept": r["accept"], "runtime_fire": r["fire"],
                    "stmt": stmt,
                })

        generic_note = ("generic_uninferable " if
                        member["sigs"][0].get("type_params") else "")
        if "A" in o_result["probes"] and "B" in o_result["probes"] and \
                "C" in o_result["probes"]:
            kind_c, note = classify_official(
                o_result["probes"]["A"], o_result["probes"]["B"],
                o_result["probes"]["C"])
        else:
            kind_c, note = "error", "probes incomplete"
        o_result["official_behavior_kind"] = kind_c
        o_result["note"] = generic_note + note
        o_result["value_type"] = fmt_type(member["sigs"][0]["ret"], tvars)
        o_result["callable"] = o_result["probes"].get("B", {}).get(
            "verdict") == "ACCEPT"
        # Runtime model kind (project context grouping; F1 moved zero-arg
        # first/last into fields, matching official behavior).
        p_info = project_raw["nominals"].get(owner) or {}
        if kind == "method" and mname in ("first", "last") and \
                mname in (p_info.get("instance_fields") or {}):
            r_result["runtime_kind"] = "field (F1 moved)"
        elif kind in ("field", "static_field", "method", "static_method"):
            r_result["runtime_kind"] = raw_kind
        elif kind == "interface_method":
            r_result["runtime_kind"] = "method"
        elif kind == "function":
            r_result["runtime_kind"] = "function"
        official_rows.append(o_result)
        runtime_rows.append(r_result)

    # ---- receiver-shape dimension (non-identifier receivers) ---------------
    # The runtime cannot resolve member access on literal/call receivers
    # (calibration: receiver grab produced "3" for `[1,2,3].size`); the
    # official checker can.  Document the family separately — it is a
    # receiver-resolution gap, not a member-behavior gap, so it stays out of
    # the per-member gate.
    receiver_shape: list[dict] = []
    for owner, (expr, rtype) in RECEIVERS.items():
        info = ctx_raw["nominals"].get(owner)
        if info is None:
            continue
        fields = info.get("instance_fields") or {}
        probe = None
        if fields:
            fname, ftype = next(iter(fields.items()))
            probe = (f"{expr}.{fname}", fmt_type(ftype, DEFAULT_TVARS))
        else:
            for mname, spec in (info.get("instance_methods") or {}).items():
                sigs = spec if isinstance(spec, list) else [spec]
                for sig in sigs:
                    if not sig.get("params"):
                        probe = (f"{expr}.{mname}()",
                                 fmt_type(sig["ret"], DEFAULT_TVARS))
                        break
                if probe:
                    break
        if probe is None:
            continue
        src = program(f"let value: {probe[1]} = {probe[0]}")
        o = adjudicate(src)
        r = runtime.adjudicate(src)
        receiver_shape.append({
            "owner": owner, "stmt": probe[0], "declared": probe[1],
            "official": o["verdict"], "official_code": o["code"],
            "runtime_accept": r["accept"], "runtime_fire": r["fire"],
        })

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "official_behavioral_context.json").write_text(
        json.dumps({
            "context": str(OFFICIAL_CONTEXT), "probe_count": len(official_rows),
            "members": official_rows,
        }, ensure_ascii=False, indent=1), "utf-8")
    (out_dir / "runtime_behavioral_context.json").write_text(
        json.dumps({
            "context": str(PROJECT_CONTEXT), "probe_count": len(runtime_rows),
            "solution": args.solution.name, "members": runtime_rows,
        }, ensure_ascii=False, indent=1), "utf-8")

    # ---- diff report -------------------------------------------------------
    lines = []
    lines.append("# Behavioral Context Diff (V15 Patch 2)")
    lines.append("")
    lines.append(f"- official context: `{OFFICIAL_CONTEXT.name}` "
                 f"({len(official_rows)} members probed)")
    lines.append(f"- runtime: `{args.solution}`")
    lines.append("")
    lines.append("## Gate: runtime accept/reject == official accept/reject")
    lines.append("")
    if mismatches:
        lines.append(f"**FAIL — {len(mismatches)} probe mismatches**")
        lines.append("")
        lines.append("| owner | member | probe | official | runtime |")
        lines.append("|-------|--------|-------|----------|---------|")
        for m in mismatches:
            lines.append(
                f"| {m['owner']} | {m['member']} | {m['probe']} | "
                f"{m['official']} ({m['official_code']}) | "
                f"accept={m['runtime_accept']} fire={m['runtime_fire']} |")
    else:
        lines.append("**PASS — every probe matches**")
    lines.append("")
    lines.append("## raw JSON kind vs official behavior kind")
    lines.append("")
    lines.append("| owner | member | raw JSON | official behavior | note |")
    lines.append("|-------|--------|----------|-------------------|------|")
    raw_diffs = 0
    for o in official_rows:
        raw = o["raw_json_kind"]
        beh = o["official_behavior_kind"]
        if raw != beh:
            raw_diffs += 1
            lines.append(f"| {o['owner']} | {o['member']} | {raw} | "
                         f"**{beh}** | {o['note']} |")
    lines.append("")
    lines.append(f"{raw_diffs} members where official behavior differs from "
                 "the raw JSON grouping (all listed above).")
    lines.append("")
    lines.append("## runtime kind vs official behavior kind")
    lines.append("")
    lines.append("| owner | member | runtime kind | official behavior | match |")
    lines.append("|-------|--------|--------------|-------------------|-------|")
    kind_mismatch = 0
    by_owner: dict[str, dict[str, dict]] = {}
    for r in runtime_rows:
        by_owner.setdefault(r["owner"], {})[r["member"]] = r
    for o in official_rows:
        r = by_owner.get(o["owner"], {}).get(o["member"])
        rk = r["runtime_kind"] if r else "?"
        rk_base = rk.split(" (")[0]  # strip "field (F1 moved)" -> "field"
        ok = "field" if o["official_behavior_kind"] == "field" else \
             ("method" if o["official_behavior_kind"] == "method" else
              o["official_behavior_kind"])
        match = "yes" if rk_base == ok else "**NO**"
        if match != "yes":
            kind_mismatch += 1
        lines.append(f"| {o['owner']} | {o['member']} | {rk} | "
                     f"{o['official_behavior_kind']} | {match} |")
    lines.append("")
    lines.append(f"{kind_mismatch} runtime/model kind mismatches vs official "
                 "behavior.")
    lines.append("")
    lines.append("## receiver shape (non-identifier receivers)")
    lines.append("")
    lines.append("The A/B/C/D probes above bind the receiver to an identifier. "
                 "The literal/call receiver form is a separate runtime "
                 "limitation: member access on a non-identifier receiver does "
                 "not resolve (calibration: receiver grab produced `3` for "
                 "`[1, 2, 3].size`).  This section documents that gap — it is "
                 "NOT part of the per-member gate.")
    lines.append("")
    lines.append("| owner | stmt | declared | official | runtime |")
    lines.append("|-------|------|----------|----------|---------|")
    for rs in receiver_shape:
        ok = "match" if (
            (rs["official"] == "ACCEPT") == rs["runtime_accept"]
        ) else "**GAP**"
        lines.append(f"| {rs['owner']} | `{rs['stmt']}` | {rs['declared']} | "
                     f"{rs['official']} ({rs['official_code']}) | "
                     f"accept={rs['runtime_accept']} fire={rs['runtime_fire']} "
                     f"| {ok} |")
    lines.append("")
    lines.append("## skipped")
    lines.append("")
    for name in sorted(NO_RECEIVER):
        lines.append(f"- {name}: no concrete implementor in final context — "
                     "members not probeable through a receiver")
    (out_dir / "behavioral_context_diff.md").write_text(
        "\n".join(lines) + "\n", "utf-8")

    print(f"members probed: {len(official_rows)}")
    print(f"receiver-shape probes: {len(receiver_shape)}, "
          f"gaps: {sum(1 for rs in receiver_shape if (rs['official'] == 'ACCEPT') != rs['runtime_accept'])}")
    print(f"probe mismatches (runtime vs official): {len(mismatches)}")
    for m in mismatches:
        print(f"  MISMATCH {m['owner']}.{m['member']} {m['probe']}: "
              f"official={m['official']}({m['official_code']}) "
              f"runtime_accept={m['runtime_accept']} fire={m['runtime_fire']}")
    print(f"raw JSON vs official behavior diffs: {raw_diffs}")
    print(f"runtime kind vs official behavior mismatches: {kind_mismatch}")
    print(f"artifacts written to {out_dir}/")
    return 0 if not mismatches else 1


if __name__ == "__main__":
    sys.exit(main())
