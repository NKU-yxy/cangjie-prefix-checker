#!/usr/bin/env python3
"""Repeatable cold-process benchmark for the 50 public official samples.

Each trial starts a fresh solution process, sends cl100k_base token IDs one by
one, validates every response through the official first-error token, and
records startup, detection, and complete process wall-clock latency.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def percentile(values: list[float], fraction: float) -> float:
    """Return a nearest-rank percentile."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def git_value(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def read_mem_total_kib() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1])
    except (FileNotFoundError, ValueError):
        pass
    return None


def run_case(
    command: list[str],
    token_ids: list[int],
    target: int,
    env: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    started_ns = time.perf_counter_ns()
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

    first_response_ns: int | None = None
    detection_ns: int | None = None
    error = ""
    try:
        for index, token_id in enumerate(token_ids[: target + 1]):
            proc.stdin.write(f"{token_id}\n")
            proc.stdin.flush()
            response = proc.stdout.readline().strip()
            now_ns = time.perf_counter_ns()
            if first_response_ns is None:
                first_response_ns = now_ns
            expected = "1" if index == target else "0"
            if response != expected:
                error = f"token {index}: expected {expected}, got {response!r}"
                break
            if index == target:
                detection_ns = now_ns
    except (BrokenPipeError, OSError) as exc:
        error = f"protocol I/O failed: {exc}"
    finally:
        try:
            proc.stdin.close()
        except OSError:
            pass

    try:
        returncode = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        returncode = proc.wait()
        error = error or f"process did not exit within {timeout:.1f}s"
    completed_ns = time.perf_counter_ns()

    stderr = proc.stderr.read().strip() if proc.stderr is not None else ""
    if returncode != 0:
        error = error or f"process exited with status {returncode}"
    if detection_ns is None:
        error = error or "did not reach the expected first-error token"
    if error and stderr:
        error = f"{error}; stderr={stderr[:400]}"

    to_ms = lambda value: (value - started_ns) / 1_000_000
    return {
        "ok": not error,
        "first_response_ms": to_ms(first_response_ns or completed_ns),
        "detection_ms": to_ms(detection_ns or completed_ns),
        "process_total_ms": to_ms(completed_ns),
        "error": error,
    }


def stats(values: list[float]) -> dict[str, float]:
    return {
        "min": round(min(values), 3),
        "median": round(statistics.median(values), 3),
        "p95": round(percentile(values, 0.95), 3),
        "max": round(max(values), 3),
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    metadata = report["metadata"]
    lines = [
        "# 官方 50 个公开样例本地性能 Baseline",
        "",
        f"- 结果：**{summary['passed']}/{summary['cases']} PASSED**",
        f"- 计时：每例 {metadata['warmups']} 次预热 + {metadata['repetitions']} 次冷进程测量，表中以总耗时中位数排序",
        f"- 总耗时中位数（跨样例）：**{summary['case_total_median_ms']:.3f} ms**",
        f"- 总耗时 P95（跨样例）：**{summary['case_total_p95_ms']:.3f} ms**",
        f"- 最慢样例中位数：**{summary['slowest_case']} / {summary['slowest_case_median_ms']:.3f} ms**",
        f"- 项目提交：`{metadata['project_commit']}`",
        f"- 官方样例提交：`{metadata['official_commit']}`",
        f"- 环境：{metadata['platform']}，{metadata['cpu_count']} CPU，MemTotal={metadata['memory_total_kib']} KiB",
        f"- 镜像：`{metadata['docker_image']}`",
        "",
        "口径：`首响应` 从启动进程到第 1 个 token 的回复；`检测` 从启动进程到精确首错 token 的回复；`总耗时` 还包括进程正常退出。单位均为 ms。",
        "",
        "| 样例 | 检测 token 数 | 首响应中位数 | 检测中位数 | 总耗时中位数 | 总耗时最小 | 总耗时 P95 | 总耗时最大 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for case in sorted(
        report["cases"],
        key=lambda item: item["process_total_ms"]["median"],
        reverse=True,
    ):
        lines.append(
            f"| {case['name']} | {case['tokens_to_error']} | "
            f"{case['first_response_ms']['median']:.3f} | "
            f"{case['detection_ms']['median']:.3f} | "
            f"{case['process_total_ms']['median']:.3f} | "
            f"{case['process_total_ms']['min']:.3f} | "
            f"{case['process_total_ms']['p95']:.3f} | "
            f"{case['process_total_ms']['max']:.3f} |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-root", type=Path, required=True)
    parser.add_argument("--solution", type=Path, default=ROOT / "solution")
    parser.add_argument("--repetitions", type=int, default=9)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260811)
    parser.add_argument("--timeout", type=float, default=2.0)
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=ROOT / "baseline_results" / "official_50_baseline",
    )
    args = parser.parse_args()
    if args.repetitions < 1 or args.warmups < 0:
        parser.error("repetitions must be >= 1 and warmups must be >= 0")

    official = args.official_root.resolve()
    solution = args.solution.resolve()
    registry_path = official / "wrong_error_positions.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))["wrong_examples"]

    cache_dir = official / "tiktoken_cache"
    env = dict(os.environ)
    env.setdefault("TIKTOKEN_CACHE_DIR", str(cache_dir))
    import tiktoken  # pylint: disable=import-outside-toplevel

    encoding = tiktoken.get_encoding("cl100k_base")
    cases: list[dict[str, Any]] = []
    for item in registry:
        name = item["name"]
        target = int(item["first_error_token_index"])
        source = (official / "wrong" / f"{name}.cj").read_text(encoding="utf-8")
        token_ids = encoding.encode(source)
        if not 0 <= target < len(token_ids):
            raise SystemExit(f"{name}: target token {target} is out of range")
        cases.append({"name": name, "target": target, "token_ids": token_ids, "runs": []})

    command = [str(solution)]
    rng = random.Random(args.seed)
    failures: list[str] = []
    for round_index in range(args.warmups + args.repetitions):
        order = list(range(len(cases)))
        rng.shuffle(order)
        measured = round_index >= args.warmups
        label = f"measure {round_index - args.warmups + 1}/{args.repetitions}" if measured else f"warmup {round_index + 1}/{args.warmups}"
        print(label, flush=True)
        for case_index in order:
            case = cases[case_index]
            result = run_case(
                command,
                case["token_ids"],
                case["target"],
                env,
                args.timeout,
            )
            if not result["ok"]:
                failures.append(f"{case['name']} ({label}): {result['error']}")
            if measured:
                case["runs"].append(result)

    case_reports: list[dict[str, Any]] = []
    for case in cases:
        runs = case["runs"]
        case_reports.append(
            {
                "name": case["name"],
                "first_error_token_index": case["target"],
                "tokens_to_error": case["target"] + 1,
                "passed": all(run["ok"] for run in runs),
                "first_response_ms": stats([run["first_response_ms"] for run in runs]),
                "detection_ms": stats([run["detection_ms"] for run in runs]),
                "process_total_ms": stats([run["process_total_ms"] for run in runs]),
                "runs": runs,
            }
        )

    medians = [item["process_total_ms"]["median"] for item in case_reports]
    slowest = max(case_reports, key=lambda item: item["process_total_ms"]["median"])
    report = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "timer": "time.perf_counter_ns",
            "protocol": "fresh process per trial; token-by-token stdin/stdout; exact official first-error index",
            "warmups": args.warmups,
            "repetitions": args.repetitions,
            "seed": args.seed,
            "project_root": str(ROOT),
            "project_commit": git_value(ROOT, "rev-parse", "HEAD"),
            "project_status": git_value(ROOT, "status", "--short"),
            "official_root": str(official),
            "official_commit": git_value(official, "rev-parse", "HEAD"),
            "registry_sha256": hashlib.sha256(registry_path.read_bytes()).hexdigest(),
            "solution_sha256": hashlib.sha256(solution.read_bytes()).hexdigest(),
            "docker_image": os.environ.get("OFFICIAL_DOCKER_IMAGE", "unknown"),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python": platform.python_version(),
            "cpu_count": os.cpu_count(),
            "memory_total_kib": read_mem_total_kib(),
        },
        "summary": {
            "cases": len(case_reports),
            "passed": sum(1 for item in case_reports if item["passed"]),
            "failed_trials": len(failures),
            "case_total_median_ms": round(statistics.median(medians), 3),
            "case_total_p95_ms": round(percentile(medians, 0.95), 3),
            "case_total_max_ms": round(max(medians), 3),
            "slowest_case": slowest["name"],
            "slowest_case_median_ms": slowest["process_total_ms"]["median"],
        },
        "cases": case_reports,
        "failures": failures,
    }

    prefix = args.output_prefix.resolve()
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    csv_path = prefix.with_suffix(".csv")
    md_path = prefix.with_suffix(".md")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(
            [
                "name",
                "first_error_token_index",
                "tokens_to_error",
                "passed",
                "first_response_median_ms",
                "detection_median_ms",
                "process_total_min_ms",
                "process_total_median_ms",
                "process_total_p95_ms",
                "process_total_max_ms",
            ]
        )
        for case in case_reports:
            writer.writerow(
                [
                    case["name"],
                    case["first_error_token_index"],
                    case["tokens_to_error"],
                    case["passed"],
                    case["first_response_ms"]["median"],
                    case["detection_ms"]["median"],
                    case["process_total_ms"]["min"],
                    case["process_total_ms"]["median"],
                    case["process_total_ms"]["p95"],
                    case["process_total_ms"]["max"],
                ]
            )

    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"JSON: {json_path}")
    print(f"CSV:  {csv_path}")
    print(f"MD:   {md_path}")
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
