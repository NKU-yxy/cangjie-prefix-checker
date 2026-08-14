#!/usr/bin/env python3
"""Independently recompute an official A1/B/A2 benchmark from raw runs.

The input files must be JSON reports emitted by run_official_baseline.py.  No
stored summary or per-case summary is trusted: every median in this report is
recomputed from cases[].runs[].  Failed measured runs remain in the timing
samples and also fail the 50/50 correctness gate.

Exit status is 0 for a passing A/B/A gate, 1 for a rejected/invalid gate, and 2
for malformed or incomplete input.  This is only the official-50 A/B/A guard;
PASS is not, by itself, an overall competition acceptance verdict.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
import statistics
import sys
from typing import Any, Mapping, Sequence


METRICS = ("process_total_ms", "first_response_ms", "detection_ms")
METRIC_LABELS = {
    "process_total_ms": "process total",
    "first_response_ms": "first response",
    "detection_ms": "detection",
}
AGGREGATES = ("SUM", "MEDIAN", "P95", "MAX")


class InputError(ValueError):
    """Raised when a report cannot support an independent recomputation."""


@dataclass(frozen=True)
class StageData:
    label: str
    path: str
    sha256: str
    metadata: Mapping[str, Any]
    case_order: tuple[str, ...]
    medians: Mapping[str, Mapping[str, float]]
    run_ok: Mapping[str, tuple[bool, ...]]
    run_errors: Mapping[str, tuple[str, ...]]
    trial_passes: tuple[int, ...]


def nearest_rank(values: Sequence[float], fraction: float) -> float:
    """Return the nearest-rank percentile (rank = ceil(fraction * n))."""
    if not values:
        raise InputError("cannot calculate a percentile of an empty sequence")
    if not 0.0 < fraction <= 1.0:
        raise ValueError("fraction must be in (0, 1]")
    ordered = sorted(values)
    return ordered[math.ceil(fraction * len(ordered)) - 1]


def aggregate(values: Sequence[float]) -> dict[str, float]:
    if not values:
        raise InputError("cannot aggregate an empty sequence")
    return {
        "SUM": math.fsum(values),
        "MEDIAN": statistics.median(values),
        "P95": nearest_rank(values, 0.95),
        "MAX": max(values),
    }


def symmetric_change_pct(left: float, right: float) -> float:
    """Signed symmetric percent change from left to right."""
    midpoint = (left + right) / 2.0
    if midpoint <= 0.0:
        raise InputError("symmetric percent change requires a positive midpoint")
    return 100.0 * (right - left) / midpoint


def relative_change_pct(control: float, candidate: float) -> float:
    """Candidate change where a positive value means a regression."""
    if control <= 0.0:
        raise InputError("relative change requires a positive control")
    return 100.0 * (candidate - control) / control


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise InputError(f"{location}: expected JSON object")
    return value


def _positive_number(value: Any, location: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{location}: expected a numeric millisecond value")
    result = float(value)
    if not math.isfinite(result) or result <= 0.0:
        raise InputError(f"{location}: expected a finite value greater than zero")
    return result


def parse_document(
    document: Any,
    *,
    label: str,
    path: str,
    sha256: str,
    expected_cases: int,
    expected_repetitions: int,
) -> StageData:
    root = _mapping(document, f"{label} root")
    metadata_value = root.get("metadata", {})
    metadata = _mapping(metadata_value, f"{label}.metadata")
    metadata_repetitions = metadata.get("repetitions")
    if metadata_repetitions is not None:
        if isinstance(metadata_repetitions, bool) or not isinstance(
            metadata_repetitions, int
        ):
            raise InputError(f"{label}.metadata.repetitions: expected integer")
        if metadata_repetitions != expected_repetitions:
            raise InputError(
                f"{label}.metadata.repetitions={metadata_repetitions}, expected "
                f"{expected_repetitions}"
            )

    cases_value = root.get("cases")
    if not isinstance(cases_value, list):
        raise InputError(f"{label}.cases: expected array")
    if len(cases_value) != expected_cases:
        raise InputError(
            f"{label}.cases: found {len(cases_value)}, expected {expected_cases}"
        )

    order: list[str] = []
    medians: dict[str, dict[str, float]] = {}
    run_ok: dict[str, tuple[bool, ...]] = {}
    run_errors: dict[str, tuple[str, ...]] = {}

    for case_index, case_value in enumerate(cases_value):
        case = _mapping(case_value, f"{label}.cases[{case_index}]")
        name = case.get("name")
        if not isinstance(name, str) or not name:
            raise InputError(f"{label}.cases[{case_index}].name: expected nonempty string")
        if name in medians:
            raise InputError(f"{label}: duplicate case name {name!r}")

        runs = case.get("runs")
        if not isinstance(runs, list):
            raise InputError(f"{label}.{name}.runs: expected array")
        if len(runs) != expected_repetitions:
            raise InputError(
                f"{label}.{name}.runs: found {len(runs)}, expected "
                f"{expected_repetitions}"
            )

        raw_values = {metric: [] for metric in METRICS}
        oks: list[bool] = []
        errors: list[str] = []
        for run_index, run_value in enumerate(runs, start=1):
            location = f"{label}.{name}.runs[{run_index - 1}]"
            run = _mapping(run_value, location)
            ok = run.get("ok")
            if not isinstance(ok, bool):
                raise InputError(f"{location}.ok: expected boolean")
            values = {
                metric: _positive_number(run.get(metric), f"{location}.{metric}")
                for metric in METRICS
            }
            if values["first_response_ms"] > values["detection_ms"]:
                raise InputError(f"{location}: first response occurs after detection")
            if values["detection_ms"] > values["process_total_ms"]:
                raise InputError(f"{location}: detection occurs after process exit")
            for metric in METRICS:
                raw_values[metric].append(values[metric])
            error = run.get("error", "")
            errors.append(error if isinstance(error, str) else repr(error))
            oks.append(ok)

        # Deliberately use only raw run values.  Stored case statistics and the
        # top-level summary are neither read nor compared.
        medians[name] = {
            metric: statistics.median(raw_values[metric]) for metric in METRICS
        }
        run_ok[name] = tuple(oks)
        run_errors[name] = tuple(errors)
        order.append(name)

    trial_passes = tuple(
        sum(1 for name in order if run_ok[name][trial_index])
        for trial_index in range(expected_repetitions)
    )
    return StageData(
        label=label,
        path=path,
        sha256=sha256,
        metadata=metadata,
        case_order=tuple(order),
        medians=medians,
        run_ok=run_ok,
        run_errors=run_errors,
        trial_passes=trial_passes,
    )


def load_stage(
    path: Path,
    *,
    label: str,
    expected_cases: int,
    expected_repetitions: int,
) -> StageData:
    try:
        payload = path.read_bytes()
    except OSError as exc:
        raise InputError(f"{label}: cannot read {path}: {exc}") from exc
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"{label}: invalid UTF-8 JSON in {path}: {exc}") from exc
    return parse_document(
        document,
        label=label,
        path=str(path.resolve()),
        sha256=hashlib.sha256(payload).hexdigest(),
        expected_cases=expected_cases,
        expected_repetitions=expected_repetitions,
    )


def analyze(
    a1: StageData,
    candidate: StageData,
    a2: StageData,
    *,
    expected_cases: int,
    expected_repetitions: int,
) -> dict[str, Any]:
    stages = (a1, candidate, a2)
    expected_names = set(a1.case_order)
    for stage in stages[1:]:
        names = set(stage.case_order)
        if names != expected_names:
            missing = sorted(expected_names - names)
            extra = sorted(names - expected_names)
            raise InputError(
                f"{stage.label}: case set differs from A1; missing={missing}, extra={extra}"
            )

    rows: list[dict[str, Any]] = []
    for name in a1.case_order:
        metrics: dict[str, dict[str, float]] = {}
        for metric in METRICS:
            a1_value = a1.medians[name][metric]
            b_value = candidate.medians[name][metric]
            a2_value = a2.medians[name][metric]
            control = (a1_value + a2_value) / 2.0
            metrics[metric] = {
                "A1": a1_value,
                "B": b_value,
                "A2": a2_value,
                "CONTROL": control,
                "candidate_delta_ms": b_value - control,
                "candidate_change_pct": relative_change_pct(control, b_value),
            }

        total = metrics["process_total_ms"]
        noise = max(1.0, 0.03 * total["CONTROL"])
        if total["B"] <= total["CONTROL"] - noise:
            classification = "WIN"
        elif total["B"] >= total["CONTROL"] + noise:
            classification = "LOSS"
        else:
            classification = "NEUTRAL"
        severe = (
            total["candidate_delta_ms"] > 2.0
            and total["candidate_change_pct"] > 8.0
        )
        rows.append(
            {
                "name": name,
                "metrics": metrics,
                "noise_threshold_ms": noise,
                "classification": classification,
                "severe_regression": severe,
            }
        )

    metric_summary: dict[str, Any] = {}
    for metric in METRICS:
        series = {
            "A1": [row["metrics"][metric]["A1"] for row in rows],
            "B": [row["metrics"][metric]["B"] for row in rows],
            "A2": [row["metrics"][metric]["A2"] for row in rows],
            "CONTROL": [row["metrics"][metric]["CONTROL"] for row in rows],
        }
        summaries = {label: aggregate(values) for label, values in series.items()}
        changes = {
            statistic: relative_change_pct(
                summaries["CONTROL"][statistic], summaries["B"][statistic]
            )
            for statistic in AGGREGATES
        }
        drift_signed = {
            statistic: symmetric_change_pct(
                summaries["A1"][statistic], summaries["A2"][statistic]
            )
            for statistic in ("SUM", "MEDIAN")
        }
        metric_summary[metric] = {
            "stages": summaries,
            "candidate_change_pct": changes,
            "a1_to_a2_symmetric_change_pct": drift_signed,
            "a1_a2_symmetric_drift_pct": {
                key: abs(value) for key, value in drift_signed.items()
            },
        }

    trial_details: dict[str, Any] = {}
    all_trials_correct = True
    for stage in stages:
        failures = []
        for name in a1.case_order:
            for trial_index, ok in enumerate(stage.run_ok[name], start=1):
                if not ok:
                    failures.append(
                        {
                            "case": name,
                            "trial": trial_index,
                            "error": stage.run_errors[name][trial_index - 1],
                        }
                    )
        stage_ok = all(count == expected_cases for count in stage.trial_passes)
        all_trials_correct = all_trials_correct and stage_ok
        trial_details[stage.label] = {
            "passes_by_trial": list(stage.trial_passes),
            "expected_per_trial": expected_cases,
            "passed_runs": sum(stage.trial_passes),
            "total_runs": expected_cases * expected_repetitions,
            "all_trials_50_of_50": stage_ok,
            "failures": failures,
        }

    total_summary = metric_summary["process_total_ms"]
    total_drift = total_summary["a1_a2_symmetric_drift_pct"]
    total_change = total_summary["candidate_change_pct"]
    severe_rows = [row for row in rows if row["severe_regression"]]

    checks = [
        {
            "id": "all_measured_trials_50_of_50",
            "observed": "all pass" if all_trials_correct else "one or more failures",
            "rule": f"each of {expected_repetitions} trials in A1/B/A2 is {expected_cases}/{expected_cases}",
            "passed": all_trials_correct,
            "failure_verdict": "REJECTED",
        },
        {
            "id": "a1_a2_sum_symmetric_drift",
            "observed": total_drift["SUM"],
            "rule": "<= 3%",
            "passed": total_drift["SUM"] <= 3.0,
            "failure_verdict": "INVALID",
        },
        {
            "id": "a1_a2_median_symmetric_drift",
            "observed": total_drift["MEDIAN"],
            "rule": "<= 3%",
            "passed": total_drift["MEDIAN"] <= 3.0,
            "failure_verdict": "INVALID",
        },
        {
            "id": "candidate_sum_regression",
            "observed": total_change["SUM"],
            "rule": "<= 1% regression",
            "passed": total_change["SUM"] <= 1.0,
            "failure_verdict": "REJECTED",
        },
        {
            "id": "candidate_median_regression",
            "observed": total_change["MEDIAN"],
            "rule": "<= 1% regression",
            "passed": total_change["MEDIAN"] <= 1.0,
            "failure_verdict": "REJECTED",
        },
        {
            "id": "candidate_p95_regression",
            "observed": total_change["P95"],
            "rule": "<= 3% regression",
            "passed": total_change["P95"] <= 3.0,
            "failure_verdict": "REJECTED",
        },
        {
            "id": "no_case_over_2ms_and_8pct_regression",
            "observed": [row["name"] for row in severe_rows],
            "rule": "no case is simultaneously >2 ms and >8% slower",
            "passed": not severe_rows,
            "failure_verdict": "REJECTED",
        },
    ]

    failed = [check for check in checks if not check["passed"]]
    # Correctness is a hard rejection.  Otherwise, an unstable control makes
    # the round INVALID before performance regression checks are interpreted.
    correctness_failed = any(
        check["id"] == "all_measured_trials_50_of_50" and not check["passed"]
        for check in checks
    )
    invalid = any(
        check["failure_verdict"] == "INVALID" and not check["passed"]
        for check in checks
    )
    rejected = any(
        check["failure_verdict"] == "REJECTED" and not check["passed"]
        for check in checks
    )
    if correctness_failed:
        gate = "REJECTED"
    elif invalid:
        gate = "INVALID"
    elif rejected:
        gate = "REJECTED"
    else:
        gate = "PASS"

    return {
        "analysis_policy": {
            "source": "cases[].runs[] only; stored summaries ignored",
            "case_control": "(median(A1 raw runs) + median(A2 raw runs)) / 2",
            "p95": "nearest rank: sorted[ceil(0.95*n)-1]",
            "candidate_change_sign": "positive means regression; negative means improvement",
            "symmetric_drift": "abs(A2-A1) / ((A1+A2)/2) * 100",
            "failed_run_timing": "included (no trial deletion)",
        },
        "inputs": {
            stage.label: {"path": stage.path, "sha256": stage.sha256}
            for stage in stages
        },
        "expected_cases": expected_cases,
        "expected_repetitions": expected_repetitions,
        "trial_correctness": trial_details,
        "metrics": metric_summary,
        "win_loss": {
            "WIN": sum(row["classification"] == "WIN" for row in rows),
            "LOSS": sum(row["classification"] == "LOSS" for row in rows),
            "NEUTRAL": sum(row["classification"] == "NEUTRAL" for row in rows),
            "noise_rule": "N_i=max(1 ms, 3% * Control_i)",
        },
        "case_rows": rows,
        "threshold_checks": checks,
        "gate": gate,
        "gate_failure_ids": [check["id"] for check in failed],
    }


def _signed(value: float, digits: int = 3) -> str:
    return f"{value:+.{digits}f}"


def _escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render_markdown(result: Mapping[str, Any], worst_count: int) -> str:
    lines = [
        "# Independent official-50 A/B/A raw recomputation",
        "",
        f"**A/B/A gate: {result['gate']}**",
        "",
        "This gate covers only the official-50 A/B/A protection test; PASS is not an overall acceptance verdict.",
        "All timing medians below were recomputed from `cases[].runs[]`. Stored JSON summaries were ignored, and failed runs were not removed from timing samples.",
        "Candidate change is signed: positive means slower (regression), negative means faster (improvement).",
        "",
        "## Inputs",
        "",
        "| Stage | JSON | SHA-256 |",
        "|---|---|---|",
    ]
    for label in ("A1", "B", "A2"):
        item = result["inputs"][label]
        lines.append(
            f"| {label} | `{_escape(item['path'])}` | `{item['sha256']}` |"
        )

    lines.extend(
        [
            "",
            "## Trial correctness reconstructed from raw runs",
            "",
            "| Stage | Passes in measured trials | Passed raw runs | Status |",
            "|---|---|---:|---|",
        ]
    )
    for label in ("A1", "B", "A2"):
        trial = result["trial_correctness"][label]
        expected = trial["expected_per_trial"]
        counts = ", ".join(f"{count}/{expected}" for count in trial["passes_by_trial"])
        status = "PASS" if trial["all_trials_50_of_50"] else "FAIL"
        lines.append(
            f"| {label} | {counts} | {trial['passed_runs']}/{trial['total_runs']} | {status} |"
        )
    failures = [
        (label, failure)
        for label in ("A1", "B", "A2")
        for failure in result["trial_correctness"][label]["failures"]
    ]
    if failures:
        lines.extend(["", "Raw failed runs:", ""])
        for label, failure in failures:
            error = _escape(failure["error"] or "(empty error field)")
            lines.append(
                f"- {label} / `{_escape(failure['case'])}` / trial {failure['trial']}: {error}"
            )

    lines.extend(
        [
            "",
            "## Recomputed aggregate timings",
            "",
            "Control is formed per case first, then aggregated. P95 is nearest-rank.",
            "",
            "| Timing | Aggregate | A1 (ms) | Control (ms) | B (ms) | A2 (ms) | B change | A1/A2 symmetric drift |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for metric in METRICS:
        summary = result["metrics"][metric]
        for statistic in AGGREGATES:
            drift = summary["a1_a2_symmetric_drift_pct"].get(statistic)
            drift_text = f"{drift:.3f}%" if drift is not None else "—"
            lines.append(
                f"| {METRIC_LABELS[metric]} | {statistic} | "
                f"{summary['stages']['A1'][statistic]:.6f} | "
                f"{summary['stages']['CONTROL'][statistic]:.6f} | "
                f"{summary['stages']['B'][statistic]:.6f} | "
                f"{summary['stages']['A2'][statistic]:.6f} | "
                f"{_signed(summary['candidate_change_pct'][statistic])}% | "
                f"{drift_text} |"
            )

    win_loss = result["win_loss"]
    lines.extend(
        [
            "",
            "## Process-total protection decisions",
            "",
            f"WIN / LOSS / NEUTRAL = **{win_loss['WIN']} / {win_loss['LOSS']} / {win_loss['NEUTRAL']}**, with `N_i=max(1 ms, 3% * Control_i)`.",
            "",
            "| Check | Observed | Required | Status | Failure result |",
            "|---|---:|---|---|---|",
        ]
    )
    for check in result["threshold_checks"]:
        observed = check["observed"]
        if isinstance(observed, float):
            observed_text = f"{observed:.6f}%"
        elif isinstance(observed, list):
            observed_text = ", ".join(f"`{_escape(item)}`" for item in observed) or "none"
        else:
            observed_text = str(observed)
        lines.append(
            f"| `{check['id']}` | {observed_text} | {check['rule']} | "
            f"{'PASS' if check['passed'] else 'FAIL'} | {check['failure_verdict']} |"
        )

    regressions = sorted(
        (
            row
            for row in result["case_rows"]
            if row["metrics"]["process_total_ms"]["candidate_delta_ms"] > 0.0
        ),
        key=lambda row: row["metrics"]["process_total_ms"]["candidate_delta_ms"],
        reverse=True,
    )
    lines.extend(["", "## Worst process-total regressions", ""])
    if not regressions:
        lines.append("No case has a positive process-total regression.")
    else:
        lines.extend(
            [
                "| Case | Control (ms) | B (ms) | Delta (ms) | Change | N (ms) | Class | Severe >2ms & >8% |",
                "|---|---:|---:|---:|---:|---:|---|---|",
            ]
        )
        for row in regressions[:worst_count]:
            total = row["metrics"]["process_total_ms"]
            lines.append(
                f"| `{_escape(row['name'])}` | {total['CONTROL']:.6f} | "
                f"{total['B']:.6f} | {_signed(total['candidate_delta_ms'], 6)} | "
                f"{_signed(total['candidate_change_pct'])}% | "
                f"{row['noise_threshold_ms']:.6f} | {row['classification']} | "
                f"{'YES' if row['severe_regression'] else 'no'} |"
            )

    lines.extend(
        [
            "",
            "## Per-case raw-median recomputation",
            "",
            "| Case | A1 total | A2 total | Control total | B total | Delta total | B total change | N | Class | Severe | Control first | B first | B first change | Control detect | B detect | B detect change |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in result["case_rows"]:
        total = row["metrics"]["process_total_ms"]
        first = row["metrics"]["first_response_ms"]
        detection = row["metrics"]["detection_ms"]
        lines.append(
            f"| `{_escape(row['name'])}` | {total['A1']:.6f} | {total['A2']:.6f} | "
            f"{total['CONTROL']:.6f} | {total['B']:.6f} | "
            f"{_signed(total['candidate_delta_ms'], 6)} | "
            f"{_signed(total['candidate_change_pct'])}% | "
            f"{row['noise_threshold_ms']:.6f} | {row['classification']} | "
            f"{'YES' if row['severe_regression'] else 'no'} | "
            f"{first['CONTROL']:.6f} | {first['B']:.6f} | "
            f"{_signed(first['candidate_change_pct'])}% | "
            f"{detection['CONTROL']:.6f} | {detection['B']:.6f} | "
            f"{_signed(detection['candidate_change_pct'])}% |"
        )

    if result["gate_failure_ids"]:
        lines.extend(
            [
                "",
                "Failed checks: "
                + ", ".join(f"`{item}`" for item in result["gate_failure_ids"])
                + ".",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _synthetic_document(multiplier: float = 1.0) -> dict[str, Any]:
    cases = []
    offsets = (-0.04, -0.03, -0.02, -0.01, 0.0, 0.01, 0.02, 0.03, 0.04)
    for index in range(50):
        total_base = 20.0 + index
        detection_base = 15.0 + index * 0.1
        first_base = 5.0 + index * 0.01
        runs = []
        for offset in offsets:
            runs.append(
                {
                    "ok": True,
                    "first_response_ms": first_base * multiplier + offset / 10.0,
                    "detection_ms": detection_base * multiplier + offset / 2.0,
                    "process_total_ms": total_base * multiplier + offset,
                    "error": "",
                }
            )
        cases.append(
            {
                "name": f"case_{index:02d}",
                "passed": False,
                "first_response_ms": {"median": 999999.0},
                "detection_ms": {"median": 999999.0},
                "process_total_ms": {"median": 999999.0},
                "runs": runs,
            }
        )
    return {
        "metadata": {"repetitions": 9},
        "summary": {"cases": 0, "passed": 0, "case_total_median_ms": 999999.0},
        "cases": cases,
    }


def _synthetic_stage(document: Any, label: str) -> StageData:
    return parse_document(
        document,
        label=label,
        path=f"{label}.synthetic.json",
        sha256="synthetic",
        expected_cases=50,
        expected_repetitions=9,
    )


def self_test() -> None:
    if nearest_rank(list(range(1, 21)), 0.95) != 19:
        raise AssertionError("nearest-rank P95 test failed")

    a1_doc = _synthetic_document(1.0)
    b_doc = _synthetic_document(0.9)
    a2_doc = _synthetic_document(1.0)
    passing = analyze(
        _synthetic_stage(a1_doc, "A1"),
        _synthetic_stage(b_doc, "B"),
        _synthetic_stage(a2_doc, "A2"),
        expected_cases=50,
        expected_repetitions=9,
    )
    expected_sum = math.fsum(20.0 + index for index in range(50))
    actual_sum = passing["metrics"]["process_total_ms"]["stages"]["A1"]["SUM"]
    if not math.isclose(actual_sum, expected_sum, rel_tol=0.0, abs_tol=1e-12):
        raise AssertionError("raw median recomputation ignored/rounded values incorrectly")
    if passing["gate"] != "PASS" or passing["win_loss"]["WIN"] != 50:
        raise AssertionError("passing/WIN synthetic scenario failed")
    if "A/B/A gate: PASS" not in render_markdown(passing, worst_count=10):
        raise AssertionError("Markdown rendering test failed")
    json.dumps(passing, allow_nan=False)

    drifting = analyze(
        _synthetic_stage(a1_doc, "A1"),
        _synthetic_stage(_synthetic_document(1.02), "B"),
        _synthetic_stage(_synthetic_document(1.04), "A2"),
        expected_cases=50,
        expected_repetitions=9,
    )
    if drifting["gate"] != "INVALID":
        raise AssertionError("symmetric control drift scenario was not INVALID")

    failed_doc = copy.deepcopy(_synthetic_document(1.0))
    failed_doc["cases"][0]["runs"][0]["ok"] = False
    failed_doc["cases"][0]["runs"][0]["error"] = "synthetic first-error mismatch"
    failed = analyze(
        _synthetic_stage(a1_doc, "A1"),
        _synthetic_stage(failed_doc, "B"),
        _synthetic_stage(a2_doc, "A2"),
        expected_cases=50,
        expected_repetitions=9,
    )
    if failed["gate"] != "REJECTED":
        raise AssertionError("failed raw trial scenario was not REJECTED")
    if failed["trial_correctness"]["B"]["passes_by_trial"][0] != 49:
        raise AssertionError("trial 50/50 reconstruction failed")

    severe_doc = copy.deepcopy(_synthetic_document(1.0))
    for run in severe_doc["cases"][0]["runs"]:
        run["process_total_ms"] += 10.0
    severe = analyze(
        _synthetic_stage(a1_doc, "A1"),
        _synthetic_stage(severe_doc, "B"),
        _synthetic_stage(a2_doc, "A2"),
        expected_cases=50,
        expected_repetitions=9,
    )
    if severe["gate"] != "REJECTED" or not severe["case_rows"][0]["severe_regression"]:
        raise AssertionError("per-case >2 ms and >8% regression scenario failed")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recompute official A1/B/A2 statistics strictly from raw runs."
    )
    parser.add_argument("a1", nargs="?", type=Path, help="A1 control JSON")
    parser.add_argument("candidate", nargs="?", type=Path, help="candidate B JSON")
    parser.add_argument("a2", nargs="?", type=Path, help="A2 control JSON")
    parser.add_argument(
        "--format", choices=("markdown", "json"), default="markdown"
    )
    parser.add_argument("--expected-cases", type=int, default=50)
    parser.add_argument("--expected-repetitions", type=int, default=9)
    parser.add_argument(
        "--worst-count",
        type=int,
        default=10,
        help="maximum regressions in the dedicated worst-regression table",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run deterministic in-memory tests; do not read benchmark files",
    )
    args = parser.parse_args(argv)
    if args.expected_cases <= 0 or args.expected_repetitions <= 0:
        parser.error("expected counts must be positive")
    if args.worst_count < 0:
        parser.error("--worst-count must be nonnegative")
    if not args.self_test and (args.a1 is None or args.candidate is None or args.a2 is None):
        parser.error("A1, candidate, and A2 JSON paths are required")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.self_test:
        self_test()
        print(
            "SELF-TEST PASS: raw medians, nearest-rank P95, symmetric drift, "
            "50/50 reconstruction, and regression gates"
        )
        return 0

    assert args.a1 is not None and args.candidate is not None and args.a2 is not None
    try:
        result = analyze(
            load_stage(
                args.a1,
                label="A1",
                expected_cases=args.expected_cases,
                expected_repetitions=args.expected_repetitions,
            ),
            load_stage(
                args.candidate,
                label="B",
                expected_cases=args.expected_cases,
                expected_repetitions=args.expected_repetitions,
            ),
            load_stage(
                args.a2,
                label="A2",
                expected_cases=args.expected_cases,
                expected_repetitions=args.expected_repetitions,
            ),
            expected_cases=args.expected_cases,
            expected_repetitions=args.expected_repetitions,
        )
    except InputError as exc:
        print(f"INPUT ERROR: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False))
    else:
        print(render_markdown(result, args.worst_count), end="")
    return 0 if result["gate"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
