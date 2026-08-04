#!/usr/bin/env python3
"""Cold-process benchmark for the actual competition protocol.

Unlike ``benchmark.py``, this runner starts a new solution process per case,
sends cl100k token IDs round by round, verifies the exact first-error index,
and includes imports, initialization, decoding, flushing, and IPC in latency.
It prints results only and never rewrites a tracked report.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * fraction))))
    return ordered[index]


def _solution_command(path: Path, mode: str) -> list[str]:
    command = [sys.executable, str(path)] if path.suffix == ".py" else [str(path)]
    command.extend(["--semantic-mode", mode])
    return command


def _run_case(
    command: list[str],
    token_ids: list[int],
    target: int,
    env: dict[str, str],
) -> tuple[bool, float, float, str]:
    started = time.perf_counter()
    proc = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None
    first_response = 0.0
    error = ""
    ok = True
    try:
        for index, token_id in enumerate(token_ids[: target + 1]):
            proc.stdin.write(f"{token_id}\n")
            proc.stdin.flush()
            response = proc.stdout.readline().strip()
            if not first_response:
                first_response = time.perf_counter() - started
            expected = "1" if index == target else "0"
            if response != expected:
                ok = False
                error = f"token {index}: expected {expected}, got {response!r}"
                break
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        if not ok and proc.stderr is not None:
            stderr = proc.stderr.read().strip()
            if stderr:
                error = f"{error}; stderr={stderr[:300]}"
    return ok, first_response, time.perf_counter() - started, error


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--official-root",
        type=Path,
        default=ROOT.parent / "cangjie-fragment-checker",
    )
    parser.add_argument("--solution", type=Path, default=ROOT / "solution.py")
    parser.add_argument(
        "--mode",
        choices=("fast", "checkpoint", "legacy"),
        default="fast",
    )
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    official = args.official_root.resolve()
    registry = json.loads((official / "wrong_error_positions.json").read_text())[
        "wrong_examples"
    ]
    if args.limit > 0:
        registry = registry[: args.limit]

    cache_dir = official / "tiktoken_cache"
    env = dict(os.environ)
    env.setdefault("TIKTOKEN_CACHE_DIR", str(cache_dir))
    import tiktoken  # pylint: disable=import-outside-toplevel

    encoding = tiktoken.get_encoding("cl100k_base")
    command = _solution_command(args.solution.resolve(), args.mode)
    first_times: list[float] = []
    total_times: list[float] = []
    failures: list[str] = []
    for item in registry:
        name = item["name"]
        target = int(item["first_error_token_index"])
        source = (official / "wrong" / f"{name}.cj").read_text()
        token_ids = encoding.encode(source)
        ok, first, total, error = _run_case(command, token_ids, target, env)
        first_times.append(first)
        total_times.append(total)
        marker = "OK" if ok else "FAIL"
        print(
            f"{name:42s} {marker:4s} tokens={target + 1:3d} "
            f"first={first * 1000:7.1f}ms total={total * 1000:7.1f}ms"
        )
        if not ok:
            failures.append(f"{name}: {error}")

    summary = {
        "mode": args.mode,
        "cases": len(registry),
        "passed": len(registry) - len(failures),
        "first_response_p50_ms": round(statistics.median(first_times) * 1000, 2),
        "total_p50_ms": round(statistics.median(total_times) * 1000, 2),
        "total_p95_ms": round(_percentile(total_times, 0.95) * 1000, 2),
        "total_max_ms": round(max(total_times, default=0.0) * 1000, 2),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
