#!/usr/bin/env python3
"""Patch 3 validator: forward-validate production recovery witnesses with the
official typechecker (V14_Plan §7.5, completion standard "任何生产候选
witness 都通过官方 typechecker").

For every fire record in --trace (captured by trace_fires.py with the
CANGJIE_TRACE_FIRE=1 C++ trace): when a witness was found and its suffix is
concrete (no "…" placeholder), rebuild the program as

    source up to the frontier-expression end + witness suffix + rest

and run tools/oracle_check.py (official typechecker, final context).
ACCEPT  -> the witness genuinely recovers the program (production-valid)
REJECT  -> the suffix does not fix the error (disabled witness)

Insertion point (the suffix is a postfix of the frontier expression):
  * tail == Call: after the call group's matching ')' when the call is
    complete in the walked-up line, else at the end of the walked-up line
    (the call is still open at the fire point);
  * tail == Member: after the member call's matching ')' when a call group
    follows the member name, else at the end of the member identifier;
  * otherwise: at the end of the frontier identifier (the fire cursor is
    mid-expression: "if (v", "n[", "a <", "for (i in n").

Non-production witnesses ("…" markers) are counted and skipped.

Cross-check: the official typechecker package is stricter than the judge
checker in places (e.g. String.toString, statement-Unit); a rebuilt program
the package rejects may still recover the program under judge-aligned
semantics.  Each rebuilt program is therefore ALSO fed to --solver (this
project's checker): "self-ACCEPT" (no fire) + oracle-REJECT => the witness
fixes the fire error; the package rejected a pre-existing strict construct.
Only oracle-ACCEPT counts as production-valid (plan §7.5 letter); the
self-accept bucket is reported separately as "witness OK (judge-aligned)".

Usage: validate_witnesses.py --trace /tmp/fire_trace.json
       --root official-reference [--solver ./solution] [--outdir work/patch3_rebuilds]
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ORACLE = TOOLS_DIR / "oracle_check.py"


def solver_accepts(solver: Path, program_text: str) -> bool:
    """Feed the program's tokens to the checker; True when it never fires."""
    import tiktoken
    enc = tiktoken.get_encoding("cl100k_base")
    ids = enc.encode(program_text)
    p = subprocess.Popen([str(solver)], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                         text=True, bufsize=1)
    assert p.stdin and p.stdout
    try:
        for tok in ids:
            p.stdin.write(f"{tok}\n")
            p.stdin.flush()
            if p.stdout.readline().strip() == "1":
                return False
    finally:
        p.terminate()
        p.wait()
    return True


def find_matching_close(text, open_at):
    """Offset of the ')' matching the '(' at open_at, or -1 (depth scan)."""
    depth = 0
    for i in range(open_at, len(text)):
        if text[i] == '"':  # skip string literals (best effort)
            i += 1
            while i < len(text) and text[i] != '"':
                i += 1
            continue
        if text[i] == '(':
            depth += 1
        elif text[i] == ')':
            depth -= 1
            if depth == 0:
                return i
    return -1


def expr_end_of(frontier_end, tail, line_text):
    """Byte offset (within the fire source) where the frontier expression ends."""
    if tail == "call":
        # '(...)' following the identifier: extend to the call group.
        i = frontier_end
        while i < len(line_text) and line_text[i] in " \t":
            i += 1
        if i < len(line_text) and line_text[i] == '(':
            close = find_matching_close(line_text, i)
            if close >= 0:
                return close + 1
            return len(line_text)  # open call extends to the fire point
        return frontier_end
    if tail == "member":
        # ".member" or ".member(...)" following the identifier.
        i = frontier_end
        while i < len(line_text) and line_text[i] in " \t":
            i += 1
        if i < len(line_text) and line_text[i] == '.':
            j = i + 1
            while j < len(line_text) and (line_text[j].isalnum() or line_text[j] == '_'):
                j += 1
            k = j
            while k < len(line_text) and line_text[k] in " \t":
                k += 1
            if k < len(line_text) and line_text[k] == '(':
                close = find_matching_close(line_text, k)
                if close >= 0:
                    return close + 1
            return j
        return frontier_end
    return frontier_end

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
ORACLE = TOOLS_DIR / "oracle_check.py"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--trace", required=True, help="fire trace JSON array (trace_fires.py output)")
    p.add_argument("--root", required=True, help="official-reference dir (wrong/ wrong2/)")
    p.add_argument("--solver", default=None, help="this project's checker binary (self cross-check)")
    p.add_argument("--outdir", default="work/patch3_rebuilds", help="rebuilt programs output dir")
    args = p.parse_args()

    root = Path(args.root).resolve()
    outdir = Path(args.outdir).resolve()
    outdir.mkdir(parents=True, exist_ok=True)

    with open(args.trace, encoding="utf-8") as f:
        fires = json.load(f)

    pkg_dir = (root / "typechecker").resolve()  # contains the typechecker/ package
    env = dict(os.environ)
    env["PYTHONPATH"] = str(pkg_dir) + os.pathsep + env.get("PYTHONPATH", "")
    env["CANGJIE_TYPECHECKER_CONTEXT"] = "final"

    rows = []
    skipped = 0
    for rec in fires:
        if rec.get("event") == "stats":
            continue
        name = rec["prog"]
        src = rec.get("src", "")
        suffix = rec.get("witness_suffix", "")
        if not rec.get("witness") or not suffix:
            continue
        if "…" in suffix:  # non-production placeholder suffix
            skipped += 1
            rows.append((name, rec.get("folder"), suffix, "skipped", "", ""))
            continue
        orig = (root / rec["folder"] / f"{name}.cj").read_text(encoding="utf-8")
        assert orig.startswith(src), f"{name}: src not a prefix"
        # Insert the postfix at the end of the frontier expression, not at
        # the fire cursor: mid-expression fires ("if (v", "n[") leave the
        # frontier identifier inside a group that continues past the cursor.
        fs, fe = rec.get("frontier_start", 0), rec.get("frontier_end", 0)
        if fe > len(src):
            fe, fs = len(src), 0
        line_text = src[fs:]  # walked-up line inside the streamed source
        rel = expr_end_of(fe - fs, str(rec.get("tail", "")).lower(), line_text)
        cut = fs + rel
        rebuilt = src[:cut] + suffix + src[cut:] + orig[len(src):]
        out_path = outdir / f"{name}.rebuilt.cj"
        out_path.write_text(rebuilt, encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(ORACLE), str(out_path)],
            capture_output=True, text=True, env=env, timeout=120,
        )
        verdict = "ACCEPT" if r.stdout.strip().startswith("ACCEPT") else "REJECT"
        detail = r.stdout.strip() if verdict == "REJECT" else ""
        self_ok = solver_accepts(args.solver, rebuilt) if args.solver else None
        if self_ok and verdict == "REJECT":
            verdict = "SELF-OK"  # witness fixes the fire; package strict elsewhere
        rows.append((name, rec.get("folder"), suffix, verdict, rec.get("witness_target", ""), detail, self_ok))

    accepted = sum(1 for r in rows if r[3] == "ACCEPT")
    self_ok = sum(1 for r in rows if r[3] == "SELF-OK")
    rejected = sum(1 for r in rows if r[3] == "REJECT")
    print(f"production witnesses: {accepted + rejected + self_ok}  "
          f"oracle-ACCEPT {accepted}  witness-OK(judge-aligned) {self_ok}  "
          f"disabled {rejected}  skipped(non-production) {skipped}")
    print(f"{'program':36s} {'folder':7s} {'verdict':9s} {'target':14s} suffix")
    for name, folder, suffix, verdict, target, detail, _ in rows:
        print(f"{name:36s} {folder:7s} {verdict:9s} {str(target):14s} {suffix}")
    for name, folder, suffix, verdict, target, detail, _ in rows:
        if verdict == "REJECT" and detail:
            print(f"  {name}: {detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
