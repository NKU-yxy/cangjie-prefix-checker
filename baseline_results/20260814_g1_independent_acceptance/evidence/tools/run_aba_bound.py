#!/usr/bin/env python3
"""Run provenance-bound official-50 A1/B/A2 inside the locked audit container."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from typing import Any


AUDIT = Path("/audit")
OFFICIAL = AUDIT / "official"
RESULTS = AUDIT / "results"
PROVENANCE = RESULTS / "aba_bound_provenance.json"

LOCKED = {
    "control": "68d780d54c25883b4e05c3f3562b315750b38af0",
    "candidate": "499c9c787fdbd8140307c5b5f472e9aee0c9342c",
    "official": "88336c400e7a4a671424e3e6c46c0866c8c0af93",
    "registry_sha256": "2425e64184d69dd392f6cdec52dc20d42d0977cbe84be744a0ffbd1dfad374f2",
    "image_tag": "docker.educg.net/compiler_system_challenge/cjchecker:20260522",
    "image_digest": "sha256:980dd9f2ede4f0132e9c71c71c1d6553cafd5de7cf1977c2ffe97a5ab34b8c90",
}

STAGES = [
    ("A1", Path("/control"), RESULTS / "aba_bound_A1"),
    ("B", Path("/candidate"), RESULTS / "aba_bound_B"),
    ("A2", Path("/control"), RESULTS / "aba_bound_A2"),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def file_record(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    return {
        "path": str(path),
        "realpath": str(resolved),
        "size_bytes": resolved.stat().st_size,
        "sha256": sha256(resolved),
    }


def root_record(root: Path) -> dict[str, Any]:
    return {
        "root": str(root),
        "realpath": str(root.resolve(strict=True)),
        "head": git(root, "rev-parse", "HEAD"),
        "status_short": git(root, "status", "--short"),
        "objects_realpath": str((root / ".git" / "objects").resolve(strict=True)),
        "alternates_exists": (root / ".git" / "objects" / "info" / "alternates").exists(),
        "runner": file_record(root / "baseline_results" / "run_official_baseline.py"),
        "solution": file_record(root / "solution"),
        "grammar_raw": file_record(root / "grammar" / "cangjie.gbnf"),
        "grammar_token": file_record(root / "grammar" / "cangjie_token.gbnf"),
        "context_json": file_record(root / "context.json"),
        "generated_context": file_record(root / "generated" / "context.bin"),
        "generated_tokenizer": file_record(root / "generated" / "cl100k_base.bin"),
    }


def atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def fail(message: str) -> None:
    raise RuntimeError(message)


def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    roots = {"control": root_record(Path("/control")), "candidate": root_record(Path("/candidate"))}
    official = {
        "root": str(OFFICIAL.resolve(strict=True)),
        "head": git(OFFICIAL, "rev-parse", "HEAD"),
        "registry": file_record(OFFICIAL / "wrong_error_positions.json"),
    }
    if roots["control"]["head"] != LOCKED["control"]:
        fail("control HEAD is not locked")
    if roots["candidate"]["head"] != LOCKED["candidate"]:
        fail("candidate HEAD is not locked")
    if official["head"] != LOCKED["official"]:
        fail("official HEAD is not locked")
    if official["registry"]["sha256"] != LOCKED["registry_sha256"]:
        fail("official registry SHA-256 is not locked")
    if roots["control"]["runner"]["sha256"] != roots["candidate"]["runner"]["sha256"]:
        fail("A/B runner bytes differ")
    if roots["control"]["objects_realpath"] == roots["candidate"]["objects_realpath"]:
        fail("control and candidate share object directory")
    if roots["control"]["alternates_exists"] or roots["candidate"]["alternates_exists"]:
        fail("git alternates present")

    report: dict[str, Any] = {
        "schema": "g1-aba-bound-provenance-v1",
        "contract": {
            "order": ["A1", "B", "A2"],
            "warmups": 1,
            "repetitions": 9,
            "seed": 20260811,
            "exit_timeout_seconds": 2,
            "fresh_process": True,
            "token_by_token_immediate": True,
            "parallel_benchmarks": False,
            "supersedes_unbound_prefixes": ["aba_A1", "aba_B", "aba_A2"],
        },
        "locked": LOCKED,
        "environment": {
            "container_id": platform.node(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "cpu_count": os.cpu_count(),
            "python": platform.python_version(),
            "profile_shadow_env_removed": [
                "CANGJIE_PROFILE",
                "CANGJIE_PHASE_PROFILE",
                "CANGJIE_GRAMMAR_SHADOW_BUILD",
                "CANGJIE_ENABLE_GRAMMAR_SHADOW",
            ],
        },
        "official": official,
        "roots": roots,
        "stages": [],
        "status": "running",
    }
    atomic_json(PROVENANCE, report)

    env = dict(os.environ)
    for name in report["environment"]["profile_shadow_env_removed"]:
        env.pop(name, None)
    env["OFFICIAL_DOCKER_IMAGE"] = LOCKED["image_tag"]

    previous_finished_ns: int | None = None
    for label, root, output_prefix in STAGES:
        runner = root / "baseline_results" / "run_official_baseline.py"
        solution = root / "solution"
        argv = [
            sys.executable,
            str(runner),
            "--official-root",
            str(OFFICIAL),
            "--solution",
            str(solution),
            "--warmups",
            "1",
            "--repetitions",
            "9",
            "--seed",
            "20260811",
            "--timeout",
            "2",
            "--output-prefix",
            str(output_prefix),
        ]
        started_wall = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        started_ns = time.time_ns()
        if previous_finished_ns is not None and started_ns < previous_finished_ns:
            fail("non-monotonic stage order")
        completed = subprocess.run(argv, env=env, capture_output=True, text=True, check=False)
        finished_ns = time.time_ns()
        previous_finished_ns = finished_ns
        stdout_path = output_prefix.with_suffix(".runner.stdout")
        stderr_path = output_prefix.with_suffix(".runner.stderr")
        stdout_path.write_text(completed.stdout, encoding="utf-8")
        stderr_path.write_text(completed.stderr, encoding="utf-8")
        json_path = output_prefix.with_suffix(".json")
        if not json_path.is_file():
            fail(f"{label}: missing runner JSON")
        raw = json.loads(json_path.read_text(encoding="utf-8"))
        measured_runs = [run for case in raw["cases"] for run in case["runs"]]
        expected_commit = LOCKED["candidate"] if label == "B" else LOCKED["control"]
        checks = {
            "returncode_zero": completed.returncode == 0,
            "runner_project_root_bound": Path(raw["metadata"]["project_root"]).resolve() == root.resolve(),
            "runner_project_commit_bound": raw["metadata"]["project_commit"] == expected_commit,
            "solution_sha_bound": raw["metadata"]["solution_sha256"] == sha256(solution),
            "official_commit_bound": raw["metadata"]["official_commit"] == LOCKED["official"],
            "registry_sha_bound": raw["metadata"]["registry_sha256"] == LOCKED["registry_sha256"],
            "warmups_bound": raw["metadata"]["warmups"] == 1,
            "repetitions_bound": raw["metadata"]["repetitions"] == 9,
            "seed_bound": raw["metadata"]["seed"] == 20260811,
            "machine_aarch64": raw["metadata"]["machine"] == "aarch64",
            "summary_50_of_50": raw["summary"]["passed"] == 50 and raw["summary"]["cases"] == 50,
            "failed_trials_zero": raw["summary"]["failed_trials"] == 0,
            "measured_run_count_450": len(measured_runs) == 450,
            "all_measured_runs_ok": all(run["ok"] for run in measured_runs),
            "stderr_log_empty": completed.stderr == "",
        }
        stage = {
            "label": label,
            "root": str(root.resolve()),
            "root_head": git(root, "rev-parse", "HEAD"),
            "argv": argv,
            "runner": file_record(runner),
            "solution": file_record(solution),
            "grammar_raw": file_record(root / "grammar" / "cangjie.gbnf"),
            "grammar_token": file_record(root / "grammar" / "cangjie_token.gbnf"),
            "context_json": file_record(root / "context.json"),
            "started_wall": started_wall,
            "started_unix_ns": started_ns,
            "finished_unix_ns": finished_ns,
            "duration_ns": finished_ns - started_ns,
            "returncode": completed.returncode,
            "stdout_log": file_record(stdout_path),
            "stderr_log": file_record(stderr_path),
            "outputs": {
                suffix: file_record(output_prefix.with_suffix(suffix))
                for suffix in (".json", ".csv", ".md")
            },
            "raw_summary": raw["summary"],
            "checks": checks,
            "all_checks_pass": all(checks.values()),
        }
        report["stages"].append(stage)
        atomic_json(PROVENANCE, report)
        if not stage["all_checks_pass"]:
            fail(f"{label}: provenance or correctness check failed: {checks}")

    report["status"] = "complete"
    report["all_stage_checks_pass"] = all(stage["all_checks_pass"] for stage in report["stages"])
    report["completed_unix_ns"] = time.time_ns()
    atomic_json(PROVENANCE, report)
    print(f"bound A/B/A complete: {PROVENANCE}")
    for stage in report["stages"]:
        print(stage["label"], stage["outputs"][".json"]["sha256"], stage["raw_summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
