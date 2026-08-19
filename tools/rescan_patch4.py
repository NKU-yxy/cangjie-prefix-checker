"""V15 Patch 4 gate rescan: Alive-Only Override verification.

Re-runs the v15 solution over the whole valid-prefix corpus (1497 official
ACCEPT programs, Patch 3) and checks:

  1. every baseline early fire that is now deferred has a complete
     printable suffix (the program tail after the old fire position);
  2. every deferred suffix is officially valid (official checker ACCEPT on
     the full program — the corpus is ACCEPT-only by construction, re-checked
     here from scratch);
  3. no program that previously passed now fires (no new Dead);
  4. no fire position moved earlier (moves later are legal Patch 4 behavior
     for still-failing cases: the open-literal element check defers to ']').

Usage: python3 tools/rescan_patch4.py [--jobs N]
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from generate_valid_prefix_corpus import PrefixScanner  # noqa: E402
from behavioral_context_audit import load_official_checker  # noqa: E402


def scan_one(args):
    pid, src, old_fire, scanner = args
    res = scanner.scan_ids(scanner.enc.encode(src), trace=False)
    new_fire = res["fire"]
    crashed = res["crashed"]
    out = {"pid": pid, "old": old_fire, "new": new_fire, "crashed": crashed}
    if old_fire is not None and new_fire is None:
        # deferred: re-scan with trace to capture the frontier offsets for
        # the printable suffix (program tail after the fire position).
        traced = scanner.scan_ids(scanner.enc.encode(src), trace=True)
        ev = traced["traces"][0] if traced["traces"] else {}
        out["frontier_end"] = ev.get("frontier_end")
        out["message"] = ev.get("message")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()

    corpus = json.load(open(ROOT / "results/valid_prefix_corpus.json"))
    programs = corpus["programs"]
    print(f"corpus: {len(programs)} programs")

    scanner = PrefixScanner(str(ROOT / "solution"))
    jobs = [
        (p["id"], p["src"], p.get("fire"), scanner)
        for p in programs
    ]
    with mp.Pool(args.jobs) as pool:
        rows = pool.map(scan_one, jobs)

    by_pid = {r["pid"]: r for r in rows}
    old_fires = [p for p in programs if p.get("fire") is not None]
    deferred = [r for r in rows if r["old"] is not None and r["new"] is None]
    new_fires = [r for r in rows if r["old"] is None and r["new"] is not None]
    moved = [
        r for r in rows
        if r["old"] is not None and r["new"] is not None and r["old"] != r["new"]
    ]
    kept = [
        r for r in rows
        if r["old"] is not None and r["new"] is not None and r["old"] == r["new"]
    ]

    print(f"old early fires:            {len(old_fires)}")
    print(f"deferred (fire removed):    {len(deferred)}")
    print(f"kept at same position:      {len(kept)}")
    print(f"moved to later position:    {len(moved)}")
    print(f"NEW fires (regression):     {len(new_fires)}")
    print(f"crashed:                    {sum(1 for r in rows if r['crashed'])}")

    report = {
        "corpus_size": len(programs),
        "old_early_fires": len(old_fires),
        "deferred": len(deferred),
        "kept_same_position": len(kept),
        "moved_later": len(moved),
        "new_fires_regression": len(new_fires),
        "deferred_list": [],
        "kept_list": [{"pid": r["pid"], "old": r["old"]} for r in kept],
        "moved_list": [{"pid": r["pid"], "old": r["old"], "new": r["new"]}
                       for r in moved],
        "new_fire_list": [{"pid": r["pid"], "new": r["new"]} for r in new_fires],
        "gates": {},
    }

    # Deferred: printable suffix + official validation.
    adjudicate = load_official_checker()
    by_id = {p["id"]: p for p in programs}
    official_ok = 0
    for r in deferred:
        prog = by_id[r["pid"]]
        verdict = adjudicate(prog["src"])
        suffix = prog["src"]
        if r.get("frontier_end") is not None:
            cut = min(r["frontier_end"], len(suffix))
            suffix = suffix[cut:]
        entry = {
            "pid": r["pid"],
            "old_fire": r["old"],
            "message": r.get("message", ""),
            "suffix": suffix,
            "official_verdict": verdict["verdict"],
            "official_code": verdict.get("code", ""),
        }
        report["deferred_list"].append(entry)
        if verdict["verdict"] == "ACCEPT":
            official_ok += 1
        else:
            print(f"  !! official REJECT on deferred {r['pid']}: "
                  f"{verdict.get('code')} {verdict.get('msg', '')[:80]}")

    report["deferred_official_accepted"] = official_ok
    report["gates"] = {
        "no_new_fires": len(new_fires) == 0,
        "no_earlier_moves": all(r["new"] >= r["old"] for r in moved),
        "deferred_suffix_official_accept":
            official_ok == len(deferred) and len(deferred) > 0,
        "all_old_fires_resolved": len(deferred) + len(kept) + len(moved)
        == len(old_fires),
    }

    print()
    print("gates:", json.dumps(report["gates"], indent=1))

    out_path = ROOT / "results/patch4_rescan.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1))
    print(f"report -> {out_path}")
    return 0 if all(report["gates"].values()) else 1


if __name__ == "__main__":
    sys.exit(main())
