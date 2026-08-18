#!/usr/bin/env python3
"""Run token_interaction_test.py on all wrong samples in wrong_error_positions.json."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def run_harness(root: Path, stem: str, solver_cmd: list[str]) -> str:
    cj = root / "wrong" / f"{stem}.cj"
    cmd = [
        sys.executable,
        str(root / "scripts" / "token_interaction_test.py"),
        str(cj),
        "--cmd",
        *solver_cmd,
    ]
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    out = (proc.stdout or "").strip()
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"{stem}: harness exit {proc.returncode}\n{proc.stderr}")
    return out


def main() -> int:
    root = repo_root()
    error_json = root / "wrong_error_positions.json"
    stems = [item["name"] for item in json.loads(error_json.read_text())["wrong_examples"]]

    ref_failures: list[str] = []
    faulty_passes: list[str] = []

    for stem in stems:
        cj_arg = f"wrong/{stem}.cj"
        ref_cmd = [
            sys.executable,
            str(root / "scripts" / "reference_solver.py"),
            "--cangjie-file",
            cj_arg,
        ]
        result = run_harness(root, stem, ref_cmd)
        if result != "PASSED":
            ref_failures.append(f"{stem}: {result}")

        for mode in ("never", "always", "early", "late"):
            bad_cmd = [
                sys.executable,
                str(root / "scripts" / "faulty_solver.py"),
                "--cangjie-file",
                cj_arg,
                "--mode",
                mode,
            ]
            bad_result = run_harness(root, stem, bad_cmd)
            if bad_result == "PASSED":
                faulty_passes.append(f"{stem}/{mode}")

    print(f"wrong samples: {len(stems)}")
    print(f"reference_solver PASSED: {len(stems) - len(ref_failures)}/{len(stems)}")
    if ref_failures:
        print("reference_solver failures:")
        for line in ref_failures:
            print(f"  {line}")
    print(f"faulty_solver should FAIL: {len(stems) * 4 - len(faulty_passes)}/{len(stems) * 4} modes rejected")
    if faulty_passes:
        print("unexpected faulty_solver PASSED:")
        for line in faulty_passes:
            print(f"  {line}")

    ok = not ref_failures and not faulty_passes
    print("OVERALL:", "PASSED" if ok else "FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
