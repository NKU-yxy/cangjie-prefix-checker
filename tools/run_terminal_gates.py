#!/usr/bin/env python3
"""v12 ablation gates: official harness over wrong/ and wrong2/ with the
official-reference registry (new golds, post-040fbbc), per-case timing.

Usage:
    python3 tools/run_terminal_gates.py [--solution path] [--root path]

The official registry lives in official-reference/ (new golds: 427/20/308/298/285
for the v10 anchor-fix family).  local-testset/wrong_error_positions.json is the
pre-040fbbc registry and must NOT be used for grading decisions.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

HARNESS = "token_interaction_test.py"


def run_dataset(root: Path, harness: Path, solution: Path, ds_name: str,
                cj_dir: Path, registry: Path) -> None:
    files = sorted(cj_dir.glob("*.cj"))
    data = json.loads(registry.read_text(encoding="utf-8"))
    names = {e["name"] for e in data["wrong_examples"]}
    missing = names - {f.stem for f in files}
    assert not missing, f"registry names missing files: {missing}"

    passed, failed, times = [], [], {}
    for f in files:
        t0 = time.monotonic()
        proc = subprocess.run(
            [sys.executable, str(harness), str(f), "--error-json", str(registry),
             "--cmd", str(solution)],
            capture_output=True, text=True, timeout=180,
        )
        dt = time.monotonic() - t0
        ok = proc.returncode == 0 and proc.stdout.strip().endswith("PASSED")
        (passed if ok else failed).append(f.stem)
        times[f.stem] = dt

    ts = sorted(times.values())
    n = len(ts)
    print(f"[{ds_name}] {len(passed)}/{len(files)} PASSED")
    if failed:
        for name in failed:
            print(f"  FAIL {name} ({times[name]:.3f}s)")
    if n:
        print(f"  times: sum={sum(ts):.3f}s mean={sum(ts)/n:.3f}s "
              f"median={statistics.median(ts):.3f}s "
              f"p95={ts[int(n*0.95)-1]:.3f}s max={max(ts):.3f}s")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solution", type=Path,
                        default=Path(__file__).resolve().parent.parent / "solution")
    parser.add_argument("--root", type=Path,
                        default=Path(__file__).resolve().parent.parent)
    args = parser.parse_args()

    root = args.root.resolve()
    solution = args.solution.resolve()
    harness = root / "official-reference" / "scripts" / HARNESS
    assert solution.is_file(), f"missing solution: {solution}"
    assert harness.is_file(), f"missing harness: {harness}"

    run_dataset(root, harness, solution, "wrong",
                root / "official-reference" / "wrong",
                root / "official-reference" / "wrong_error_positions.json")
    run_dataset(root, harness, solution, "wrong2",
                root / "official-reference" / "wrong2",
                root / "official-reference" / "wrong2_error_positions.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
