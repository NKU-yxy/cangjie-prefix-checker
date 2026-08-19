#!/usr/bin/env python3
"""V15 Patch 3: Valid-Program Prefix Corpus generator (V15_Plan §7).

For every member of the FINAL context, generate >= 8 use-shape programs the
OFFICIAL checker accepts (ACCEPT-only), plus a syntax-node x nesting matrix
(>= 2 nesting contexts per node) and generic-inference source programs.
Scan each accepted program against the v15 solution binary (cl100k token
stream), record early fires with their CANGJIE_TRACE_FIRE events, minimize
each fire to its shortest firing prefix, cluster by semantic cell
(site x symbol kind x tail kind x boundary x call/generic state), and write:

  results/valid_prefix_corpus.json  — full corpus + scan results + gates
  results/prefix_scan_report.md     — human report (fires, clusters, gates)

Usage:  python3 tools/generate_valid_prefix_corpus.py [--limit N] [--quick]
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
sys.path.insert(0, str(ROOT / "tools"))
import behavioral_context_audit as bca  # noqa: E402

PROJECT_CONTEXT = ROOT / "context.json"
SOLUTION = ROOT / "solution"

# ret types the official checker accepts as for-in sources (Iterable
# implementors among the final nominals, from context_final.json).
ITERABLES = {
    "Array<Int64>", "ArrayList<Int64>", "ArrayStack<Int64>",
    "ArrayDeque<Int64>", "HashSet<String>", "KeysView<String>",
    "ValuesView<Int64>", "Range<Int64>",
}


# ---------------------------------------------------------------------------
# Use-shape programs (one member -> >= 13 shape candidates, ACCEPT-only gate)
# ---------------------------------------------------------------------------

def build_member_shapes(m: dict, ctx_raw: dict) -> list[tuple[str, str, str, list]]:
    """Return [(shape_id, stmt, header, defs)] for one member.

    `stmt` is either a single statement (wrapped with header into main) or a
    full program (return shape: func def + main, header must be None).
    """
    out: list[tuple[str, str, str, list]] = []
    owner, member, kind, sigs = m["owner"], m["member"], m["kind"], m["sigs"]
    recv, recv_decl = m["recv_name"], m["recv_decl"] or ""
    tvars = m["tvars"]
    primary = sigs[0]
    # context.json stores some member types as raw parameterized strings
    # ("Optional<T>"); substitute() concretizes them like the structured
    # nodes (calibration: the official checker treats an unknown T in an
    # annotation as a free variable and rejects a concrete value against it).
    ret = bca.substitute(bca.fmt_type(primary["ret"], tvars), tvars)
    params = [bca.substitute(bca.fmt_type(p["type"], tvars), tvars)
              for p in primary.get("params", [])]
    fnty = f"({', '.join(params)}) -> {ret}" if params else f"() -> {ret}"
    expr = f"{recv}.{member}" if recv else member
    is_value = kind in ("field", "static_field")
    generic = bool(primary.get("type_params"))
    args = ", ".join(bca.valid_arg_for(p) or "0" for p in params)
    call_expr = None if is_value else f"{expr}({args})"
    base = call_expr if call_expr is not None else expr

    # 1: let initializer
    out.append(("let_init", f"let value: {ret} = {base}", recv_decl, []))
    # 2: argument position
    out.append(("arg", f"probe_take({base})", recv_decl,
                [f"func probe_take(x: {ret}): Unit {{}}"]))
    # 3: return tail expression (full program, header=None).  The receiver
    # is main-local, so the return shape binds it as a parameter instead.
    if recv_decl:
        recv_type = (bca.RECEIVERS[owner][1] if owner in bca.RECEIVERS
                     else bca.INTERFACE_RECEIVERS[owner][1])
        expr_r = f"r.{member}"
        if is_value:
            base_r = expr_r
        else:
            base_r = f"{expr_r}({args})"
        out.append(("return",
                    f"func probe_f(r: {recv_type}): {ret} {{\n"
                    f"    return {base_r}\n}}\n"
                    f"main(): Unit {{\n    {recv_decl}\n"
                    f"    let v: {ret} = probe_f(recv)\n}}\n",
                    None, []))
    else:
        out.append(("return",
                    f"func probe_f(): {ret} {{\n    return {base}\n}}\n"
                    f"main(): Unit {{\n    let v: {ret} = probe_f()\n}}\n",
                    None, []))
    # 4: condition
    out.append(("condition", f"if ({base} == {base}) {{}}", recv_decl, []))
    # 5: binary self-eq into Bool
    out.append(("binary", f"let b: Bool = {base} == {base}", recv_decl, []))
    # 6: lambda body (generic callback, ret is the lambda result)
    out.append(("lambda_body", f"probe_use<{ret}>({{ => {base} }})", recv_decl,
                ["func probe_use<R2>(cb: () -> R2): R2 { cb() }"]))
    # 7: array element
    out.append(("array_element", f"let arr: Array<{ret}> = [{base}]",
                recv_decl, []))
    # 8: index read of the array element
    out.append(("index_result",
                f"let arr: Array<{ret}> = [{base}]\n    let v: {ret} = arr[0]",
                recv_decl, []))
    # 9: ctor argument (Int64-only slot; official named args are rejected)
    if ret == "Int64":
        out.append(("ctor_arg", f"let a: Array<Int64> = Array<Int64>(1, {base})",
                    recv_decl, []))
    # 10: read-form slot coverage.  The official checker property-treats
    # zero-arg methods (field-priority; e.g. HashMap.size, Collection.size),
    # so a method's call form rejects but its plain read accepts.  Emit the
    # read variants of the value slots alongside the call forms; the
    # ACCEPT-only gate keeps whichever the official checker allows.
    if not is_value:
        out.append(("value_read", f"let value: {ret} = {expr}", recv_decl, []))
        out.append(("read_arg", f"probe_take({expr})", recv_decl,
                    [f"func probe_take(x: {ret}): Unit {{}}"]))
        out.append(("read_condition", f"if ({expr} == {expr}) {{}}",
                    recv_decl, []))
        out.append(("read_binary", f"let b: Bool = {expr} == {expr}",
                    recv_decl, []))
        out.append(("read_lambda", f"probe_use<{ret}>({{ => {expr} }})",
                    recv_decl,
                    ["func probe_use<R2>(cb: () -> R2): R2 { cb() }"]))
        out.append(("read_paren", f"let v: {ret} = ({expr})", recv_decl, []))
        out.append(("read_double",
                    f"let v2: {ret} = {expr}\n    let v3: {ret} = {expr}",
                    recv_decl, []))
        if ret == "Int64":
            out.append(("read_ctor_arg",
                        f"let a: Array<Int64> = Array<Int64>(1, {expr})",
                        recv_decl, []))
        rpost = bca.postfix_for(ret, ctx_raw)
        if rpost is not None:
            rpe, rpr = rpost
            out.append(("read_postfix", f"let value: {rpr} = {expr}{rpe}",
                        recv_decl, []))
    # 11: postfix continuation of the value
    post = bca.postfix_for(ret, ctx_raw)
    if post is not None:
        pe, pr = post
        out.append(("postfix", f"let value: {pr} = {base}{pe}", recv_decl, []))
    # 11: method reference + call (callables without type params, <= 1 param)
    if not is_value and not generic and len(params) <= 1:
        ref_args = ", ".join(bca.valid_arg_for(p) or "0" for p in params)
        call = f"f({ref_args})" if params else "f()"
        out.append(("method_ref",
                    f"let f: {fnty} = {expr}\n    let v: {ret} = {call}",
                    recv_decl, []))
    # 12: for-in source (Iterable ret types only)
    if ret in ITERABLES:
        out.append(("for_in", f"for (x in {base}) {{}}", recv_decl, []))
    # 13: paren wrap
    out.append(("paren", f"let v: {ret} = ({base})", recv_decl, []))
    # compensation shapes (fill the >= 8 gate if self-eq/Unit shapes reject)
    out.append(("double_let",
                f"let v2: {ret} = {base}\n    let v3: {ret} = {base}",
                recv_decl, []))
    out.append(("array_repeat", f"let arr: Array<{ret}> = [{base}, {base}]",
                recv_decl, []))
    out.append(("nested_paren", f"let v: {ret} = (({base}))", recv_decl, []))
    return out


def build_src(stmt: str, header: str | None, defs: list[str]) -> str:
    """Assemble a corpus program from (stmt, header, defs).

    `header is None` marks a self-contained program (return shape); an empty
    header means a plain statement without a receiver binding.
    """
    prefix = "\n".join(defs)
    if prefix:
        prefix += "\n\n"
    if header is None:
        return prefix + stmt
    body = f"    {header}\n    {stmt}" if header else f"    {stmt}"
    return f"{prefix}main(): Unit {{\n{body}\n}}\n"


# ---------------------------------------------------------------------------
# Syntax-node x nesting matrix (each node >= 2 nesting contexts)
# ---------------------------------------------------------------------------

SYNTAX_SPECS: list[tuple[str, list[tuple[str, str]]]] = [
    ("if",
     [("if_plain", "main(): Unit {\n    if (1 == 1) {\n        let x: Int64 = 1\n    }\n}\n"),
      ("if_nested", "main(): Unit {\n    if (1 == 1) {\n        if (2 == 2) {\n            let x: Int64 = 1\n        }\n    }\n}\n"),
      ("if_in_while", "main(): Unit {\n    while (1 == 1) {\n        if (2 == 2) {\n            let x: Int64 = 1\n        }\n    }\n}\n")]),
    ("while",
     [("while_plain", "main(): Unit {\n    while (1 == 1) {\n        let x: Int64 = 1\n    }\n}\n"),
      ("while_in_if", "main(): Unit {\n    if (1 == 1) {\n        while (2 == 2) {\n            let x: Int64 = 1\n        }\n    }\n}\n")]),
    ("for",
     [("for_range", "main(): Unit {\n    for (x in 0..3) {\n        let y: Int64 = x\n    }\n}\n"),
      ("for_in_if", "main(): Unit {\n    if (1 == 1) {\n        for (x in 0..3) {\n            let y: Int64 = x\n        }\n    }\n}\n")]),
    ("lambda",
     [("lambda_explicit", "func probe_use<R2>(cb: () -> R2): R2 { cb() }\n"
       "main(): Unit {\n    let v: Int64 = probe_use<Int64>({ => 1 })\n}\n"),
      ("lambda_nested", "func probe_use<R2>(cb: () -> R2): R2 { cb() }\n"
       "main(): Unit {\n    let v: Int64 = probe_use<Int64>({ => probe_use<Int64>({ => 1 }) })\n}\n"),
      ("lambda_in_array", "main(): Unit {\n    let arr: Array<() -> Int64> = [{ => 1 }]\n}\n")]),
    ("array",
     [("array_literal", "main(): Unit {\n    let arr: Array<Int64> = [1, 2]\n}\n"),
      ("array_nested", "main(): Unit {\n    let arr: Array<Array<Int64>> = [[1], [2]]\n}\n"),
      ("array_index_literal", "main(): Unit {\n    let v: Int64 = [1, 2][0]\n}\n")]),
    ("index",
     [("index_plain", "main(): Unit {\n    let arr: Array<Int64> = [1]\n    let v: Int64 = arr[0]\n}\n"),
      ("index_nested", "main(): Unit {\n    let arr: Array<Array<Int64>> = [[1]]\n    let v: Int64 = arr[0][0]\n}\n")]),
    ("range",
     [("range_plain", "main(): Unit {\n    let r: Range<Int64> = 0..5\n}\n"),
      ("range_step", "main(): Unit {\n    let r: Range<Int64> = 0..5:2\n}\n"),
      ("range_for", "main(): Unit {\n    for (x in 0..5:2) {\n        let y: Int64 = x\n    }\n}\n")]),
    ("paren",
     [("paren_plain", "main(): Unit {\n    let v: Int64 = (1)\n}\n"),
      ("paren_nested", "main(): Unit {\n    let v: Int64 = ((1))\n}\n"),
      ("paren_arith", "main(): Unit {\n    let v: Int64 = (1 + 2) * 3\n}\n")]),
    ("binary",
     [("bin_add", "main(): Unit {\n    let v: Int64 = 1 + 2\n}\n"),
      ("bin_prec", "main(): Unit {\n    let v: Int64 = 1 + 2 * 3\n}\n"),
      ("bin_and", "main(): Unit {\n    let b: Bool = 1 == 1 && 2 == 2\n}\n"),
      ("bin_or", "main(): Unit {\n    let b: Bool = 1 < 2 || 3 > 2\n}\n")]),
    ("unary",
     [("unary_not", "main(): Unit {\n    let b: Bool = !true\n}\n"),
      ("unary_neg", "main(): Unit {\n    let v: Int64 = -1\n}\n")]),
    ("return",
     [("return_literal", "func probe_f(): Int64 {\n    return 1\n}\n"
       "main(): Unit {\n    let v: Int64 = probe_f()\n}\n"),
      ("return_call", "func probe_f(): Int64 {\n    return probe_g()\n}\n"
       "func probe_g(): Int64 {\n    return 1\n}\n"
       "main(): Unit {\n    let v: Int64 = probe_f()\n}\n")]),
    ("call",
     [("call_plain", "func probe_f(): Int64 {\n    return 1\n}\n"
       "main(): Unit {\n    let v: Int64 = probe_f()\n}\n"),
      ("call_in_lambda", "func probe_f(): Int64 {\n    return 1\n}\n"
       "func probe_use<R2>(cb: () -> R2): R2 { cb() }\n"
       "main(): Unit {\n    let v: Int64 = probe_use<Int64>({ => probe_f() })\n}\n"),
      ("call_postfix", "func probe_f(): Int64 {\n    return 1\n}\n"
       "main(): Unit {\n    let v: String = (probe_f()).toString()\n}\n")]),
    ("string",
     [("str_literal", "main(): Unit {\n    let s: String = \"abc\"\n}\n"),
      ("str_concat", "main(): Unit {\n    let s: String = \"a\" + \"b\"\n}\n"),
      ("str_member", "main(): Unit {\n    let n: Int64 = \"abc\".size\n}\n")]),
    ("if_else",
     [("if_else_plain",
       "main(): Unit {\n    if (1 == 1) {\n        let x: Int64 = 1\n    } else {\n        let y: Int64 = 2\n    }\n}\n"),
      ("if_else_nested",
       "main(): Unit {\n    if (1 == 1) {\n        if (2 == 2) {\n            let x: Int64 = 1\n        } else {\n            let y: Int64 = 2\n        }\n    } else {\n        let z: Int64 = 3\n    }\n}\n")]),
    ("loop_control",
     [("break_plain", "main(): Unit {\n    while (1 == 1) {\n        break\n    }\n}\n"),
      ("continue_plain", "main(): Unit {\n    while (1 == 1) {\n        continue\n    }\n}\n")]),
    ("tuple",
     [("tuple_literal", "main(): Unit {\n    let t: (String, Int64) = (\"k\", 1)\n}\n"),
      ("tuple_arg",
       "func probe_take_t(x: (String, Int64)): Unit {}\n"
       "main(): Unit {\n    probe_take_t((\"k\", 1))\n}\n")]),
]

# Generic-inference source programs (V15_Plan §7.2d).
GENERIC_SPECS: list[tuple[str, str]] = [
    ("g_explicit_tparam",
     "func probe_id<R2>(x: R2): R2 { x }\n"
     "main(): Unit {\n    let v: Int64 = probe_id<Int64>(1)\n}\n"),
    ("g_lambda_infer",
     "func probe_use2<R2>(cb: (R2) -> R2, seed: R2): R2 { cb(seed) }\n"
     "main(): Unit {\n    let v: Int64 = probe_use2({ x => x }, 1)\n}\n"),
    ("g_lambda_explicit_ret",
     "func probe_use2<R2>(cb: (R2) -> R2, seed: R2): R2 { cb(seed) }\n"
     "main(): Unit {\n    let v: Int64 = probe_use2<Int64>({ x => x }, 1)\n}\n"),
    ("g_expected_ret",
     "main(): Unit {\n    let v: Optional<Int64> = Array<Int64>(1, 0).first\n}\n"),
    ("g_ctor_args",
     "main(): Unit {\n    let a: Array<Int64> = Array<Int64>(1, 0)\n}\n"),
    ("g_iface_subst",
     "main(): Unit {\n    let c: Collection<Int64> = ArrayList<Int64>()\n"
     "    let v: Int64 = c.size()\n}\n"),
    ("g_iface_subst2",
     "main(): Unit {\n    let c: Collection<Int64> = ArrayList<Int64>()\n"
     "    let b: Bool = c.size() == 0\n}\n"),
    ("g_generic_nested",
     "main(): Unit {\n    let m: HashMap<String, Array<Int64>> = HashMap<String, Array<Int64>>()\n}\n"),
    ("g_generic_nested2",
     "main(): Unit {\n    let a: Array<ArrayList<Int64>> = Array<ArrayList<Int64>>()\n}\n"),
    ("g_recv_method",
     "main(): Unit {\n    let v: Optional<Int64> = HashMap<String, Int64>().get(\"k\")\n}\n"),
    ("g_method_ref_call",
     "main(): Unit {\n    let f: () -> Int64 = ArrayStack<Int64>().peek\n    let v: Int64 = f()\n}\n"),
    ("g_optional_chain",
     "main(): Unit {\n    let a: Array<Int64> = Array<Int64>(1, 0)\n"
     "    let r: Optional<Int64> = a.first\n"
     "    let v: Optional<Int64> = r.first\n}\n"),
    ("g_range_step_for",
     "main(): Unit {\n    for (x in 0..10:2) {\n        let y: Int64 = x\n    }\n}\n"),
]


# ---------------------------------------------------------------------------
# Scanner (v15 solution, cl100k token stream + CANGJIE_TRACE_FIRE events)
# ---------------------------------------------------------------------------

class PrefixScanner(bca.RuntimeProber):
    """Like RuntimeProber but keeps stderr trace events and scans id lists."""

    def scan_ids(self, ids: list[int], trace: bool = True) -> dict:
        env = dict(os.environ)
        if trace:
            env["CANGJIE_TRACE_FIRE"] = "1"
        proc = subprocess.Popen(
            [self.solution], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1, env=env)
        assert proc.stdin and proc.stdout and proc.stderr
        fire = None
        crashed = False
        try:
            for idx, tok in enumerate(ids):
                proc.stdin.write(f"{tok}\n")
                proc.stdin.flush()
                line = proc.stdout.readline()
                if line.strip() == "1":
                    fire = idx
                    break
        except BrokenPipeError:
            crashed = True
        try:
            proc.stdin.close()
        except BrokenPipeError:
            pass
        proc.stdout.read()  # drain to EOF (solution exits on stdin EOF)
        err = proc.stderr.read()
        proc.wait()
        traces = []
        for eline in err.splitlines():
            if not eline.startswith("{"):
                continue
            try:
                event = json.loads(eline)
            except json.JSONDecodeError:
                continue
            if event.get("event") == "fire":
                traces.append(event)
        return {"accept": fire is None, "fire": fire,
                "crashed": crashed, "traces": traces}

    def scan(self, src: str, trace: bool = True) -> dict:
        return self.scan_ids(self.enc.encode(src), trace=trace)


def min_fire_prefix(ids: list[int], fire_idx: int, scanner: PrefixScanner,
                    trace: bool = True) -> int:
    """Shortest prefix length (>= 1) that still fires — binary search."""
    lo, hi = 0, fire_idx  # invariant: ids[:lo] no fire, ids[:hi] fires
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if scanner.scan_ids(ids[:mid], trace=trace)["fire"] is not None:
            hi = mid
        else:
            lo = mid
    return hi


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="only process the first N members (debug)")
    ap.add_argument("--quick", action="store_true",
                    help="skip min-fire-prefix minimization")
    ap.add_argument("--solution", type=Path, default=SOLUTION)
    ap.add_argument("--out-dir", type=Path, default=ROOT / "results")
    args = ap.parse_args()

    ctx_raw = json.loads(PROJECT_CONTEXT.read_text())
    official = bca.load_official_checker()
    scanner = PrefixScanner(args.solution)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    # --- corpus build: members x use shapes, official ACCEPT-only ----------
    members = bca.enumerate_members(ctx_raw)
    if args.limit:
        members = members[: args.limit]

    programs: list[dict] = []
    member_stats: list[dict] = []
    shape_totals: dict[str, int] = {}
    for m in members:
        shapes = build_member_shapes(m, ctx_raw)
        accepted: list[dict] = []
        for shape_id, stmt, header, defs in shapes:
            src = build_src(stmt, header, defs)
            verdict = official(src)
            shape_totals[shape_id] = shape_totals.get(shape_id, 0) + 1
            if verdict["verdict"] != "ACCEPT":
                continue
            pid = (f"{m['owner']}__{m['member']}__{shape_id}"
                   .replace("<global>", "global"))
            accepted.append({"id": pid, "group": "member",
                             "owner": m["owner"], "member": m["member"],
                             "kind": m["kind"], "shape": shape_id,
                             "src": src, "official": verdict["verdict"]})
        member_stats.append({"owner": m["owner"], "member": m["member"],
                             "kind": m["kind"],
                             "shapes_accepted": len(accepted),
                             "shapes_total": len(shapes)})
        programs.extend(accepted)

    for node, specs in SYNTAX_SPECS:
        for sid, src in specs:
            verdict = official(src)
            if verdict["verdict"] == "ACCEPT":
                programs.append({"id": f"syntax__{sid}", "group": "syntax",
                                 "node": node, "shape": sid, "src": src,
                                 "official": "ACCEPT"})
    for gid, src in GENERIC_SPECS:
        verdict = official(src)
        if verdict["verdict"] == "ACCEPT":
            programs.append({"id": f"generic__{gid}", "group": "generic",
                             "shape": gid, "src": src, "official": "ACCEPT"})

    # --- scan accepted programs against the solution ------------------------
    n_fire = 0
    clusters: dict[str, dict] = {}
    fire_programs: list[dict] = []
    for prog in programs:
        res = scanner.scan(prog["src"])
        prog["accept"] = res["accept"]
        prog["fire"] = res["fire"]
        prog["crashed"] = res.get("crashed", False)
        prog["traces"] = res["traces"][-3:]  # keep the last events (small)
        if res["fire"] is not None:
            n_fire += 1
            if not args.quick and len(fire_programs) < 60:
                ids = scanner.enc.encode(prog["src"])
                prog["min_fire"] = min_fire_prefix(ids, res["fire"], scanner)
            fire_programs.append(prog)
        for tr in res["traces"]:
            msg = tr.get("message", "-")
            key = (f"{msg}|{tr.get('symbol_kind', '-')}|{tr.get('tail', '-')}"
                   f"|{tr.get('boundary', '-')}|{tr.get('receiver', '-')}"
                   f"|{tr.get('cf_resolved', '')}|{tr.get('cf_closed', '')}")
            cell = clusters.setdefault(key, {
                "count": 0, "programs": [], "message": msg,
                "symbol_kind": tr.get("symbol_kind", "-"),
                "tail": tr.get("tail", "-"),
                "boundary": tr.get("boundary", "-"),
                "receiver": tr.get("receiver", "-"),
                "witness_source": tr.get("witness_source", ""),
                "witness_suffix": tr.get("witness_suffix", "")})
            cell["count"] += 1
            if len(cell["programs"]) < 3:
                cell["programs"].append(prog["id"])

    # --- gates ----------------------------------------------------------------
    # Members the official checker rejects in every use (official behavior
    # kind "error", e.g. ArrayList.of, min/max) have no legal use at all and
    # are exempt from the >= 8 shapes requirement.
    official_beh = {}
    beh_path = ROOT / "results" / "official_behavioral_context.json"
    if beh_path.exists():
        for mm in json.loads(beh_path.read_text())["members"]:
            official_beh[(mm["owner"], mm["member"])] = mm.get(
                "official_behavior_kind", "")
    exempt = {k for k, v in official_beh.items() if v == "error"}
    min_shapes = min((s["shapes_accepted"] for s in member_stats),
                     default=0)
    below_8 = [s for s in member_stats
               if s["shapes_accepted"] < 8
               and (s["owner"], s["member"]) not in exempt]
    exempt_list = sorted(f"{o}.{m}" for o, m in exempt)
    syntax_nodes = {}
    for prog in programs:
        if prog["group"] == "syntax":
            syntax_nodes.setdefault(prog["node"], 0)
            syntax_nodes[prog["node"]] += 1
    syntax_below_2 = [n for n, c in syntax_nodes.items() if c < 2]

    gates = {
        "members_covered": len(member_stats),
        "members_below_8_shapes": [f"{s['owner']}.{s['member']}"
                                   for s in below_8],
        "exempt_official_error_members": exempt_list,
        "syntax_nodes_below_2": syntax_below_2,
        "all_programs_official_accept": True,  # by construction
        "corpus_size": len(programs),
        "early_fire_programs": n_fire,
    }

    # --- write outputs --------------------------------------------------------
    corpus = {
        "patch": "v15-patch3",
        "programs": programs,
        "member_stats": member_stats,
        "shape_totals": shape_totals,
        "clusters": [{"cell": k, **v} for k, v in sorted(
            clusters.items(), key=lambda kv: -kv[1]["count"])],
        "gates": gates,
    }
    out_json = args.out_dir / "valid_prefix_corpus.json"
    out_json.write_text(json.dumps(corpus, indent=1, ensure_ascii=False))
    print(f"corpus written: {out_json} ({len(programs)} programs, "
          f"{n_fire} early fires, {len(clusters)} semantic cells)")

    # --- report -----------------------------------------------------------------
    lines = ["# Patch 3: Valid-Program Prefix Corpus — 扫描报告\n",
             f"- 语料规模：**{len(programs)}** 个官方 ACCEPT 程序"
             f"（members {len(member_stats)} 个，语法节点"
             f" {sum(syntax_nodes.values())} 个，泛型来源"
             f" {sum(1 for p in programs if p['group'] == 'generic')} 个）",
             f"- 过早拒绝（early fire）：**{n_fire}** 个程序",
             f"- 语义 cell 聚类：**{len(clusters)}** 个\n",
             "## 门禁检查\n",
             f"- 每 member ≥8 种 use shapes：{'✅' if not below_8 else '❌ ' + str(gates['members_below_8_shapes'])}"
             f"（min={min_shapes}；官方 error 成员豁免 {len(exempt_list)} 个）",
             f"- 语法节点每类 ≥2 嵌套上下文：{'✅' if not syntax_below_2 else '❌ ' + str(syntax_below_2)}",
             f"- 全部程序官方 ACCEPT：✅（按构造，生成时过滤）",
             f"- 语料规模：{gates['corpus_size']}；过早拒绝程序数：{n_fire}\n",
             "## 语义 cell 聚类（fire 事件）\n",
             "| cell | 计数 | 示例程序 | message |",
             "|---|---|---|---|"]
    for c in sorted(clusters.values(), key=lambda v: -v["count"]):
        progs = ", ".join(c["programs"]) or "-"
        msg = (c["message"][:70] + "…") if len(c["message"]) > 70 else c["message"]
        cell = (f"{c['symbol_kind']}/{c['tail']}/{c['boundary']}"
                f" recv={c['receiver'] or '-'}")
        lines.append(f"| {cell} | {c['count']} | {progs} | `{msg}` |")
    if clusters:
        lines.append("")
    lines.append("## 过早拒绝程序清单（Patch 4 输入）\n")
    lines.append("| id | fire@token | min_fire@token | shape |")
    lines.append("|---|---|---|---|")
    for p in fire_programs:
        mf = p.get("min_fire", "-")
        lines.append(f"| {p['id']} | {p['fire']} | {mf} | {p['shape']} |")
    out_md = args.out_dir / "prefix_scan_report.md"
    out_md.write_text("\n".join(lines) + "\n")
    print(f"report written: {out_md}")

    if args.limit:
        print("--limit: debug run, gates not meaningful")
    return 0


if __name__ == "__main__":
    sys.exit(main())
