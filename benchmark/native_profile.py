#!/usr/bin/env python3
"""Collect native semantic work counters across public, project, and fuzz corpora."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from differential_check import _project_programs
from hidden_semantic_fuzz import generate_cases


def run_source(
    solution: Path,
    source: str,
    token_ids: list[int],
    expected_valid: bool,
    exact_error: int | None,
    env: dict[str, str],
) -> dict[str, int]:
    proc = subprocess.run(
        [str(solution)],
        cwd=ROOT,
        env=env,
        input="".join(f"{token_id}\n" for token_id in token_ids),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=10,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"solution exited with {proc.returncode}: {proc.stderr[:400]}")
    answers = proc.stdout.splitlines()
    first_error = next((index for index, value in enumerate(answers) if value == "1"), None)
    if any(value not in {"0", "1"} for value in answers):
        raise RuntimeError(f"invalid protocol output: {answers[:20]}")
    if exact_error is not None and first_error != exact_error:
        raise RuntimeError(f"expected exact error {exact_error}, got {first_error}")
    if exact_error is None:
        actual_valid = first_error is None and len(answers) == len(token_ids)
        if actual_valid != expected_valid:
            raise RuntimeError(
                f"expected valid={expected_valid}, got first_error={first_error}, "
                f"responses={len(answers)}/{len(token_ids)}"
            )

    marker = "CANGJIE_PROFILE "
    payloads = [line[len(marker) :] for line in proc.stderr.splitlines() if line.startswith(marker)]
    if len(payloads) != 1:
        raise RuntimeError(f"expected one profile payload, got {len(payloads)}: {proc.stderr[:400]}")
    counters = json.loads(payloads[0])
    phase_marker = "CANGJIE_PHASE_PROFILE "
    phase_payloads = [
        line[len(phase_marker) :]
        for line in proc.stderr.splitlines()
        if line.startswith(phase_marker)
    ]
    if len(phase_payloads) != 1:
        raise RuntimeError(
            f"expected one phase profile payload, got {len(phase_payloads)}: "
            f"{proc.stderr[:400]}"
        )
    for key, value in json.loads(phase_payloads[0]).items():
        counters[f"phase_{key}"] = int(value)
    counters["source_bytes"] = len(source.encode("utf-8"))
    counters["token_count"] = len(token_ids)
    return counters


def add_corpus(
    corpus: str,
    cases: Iterable[tuple[str, str, bool, int | None]],
    solution: Path,
    encoding: object,
    env: dict[str, str],
    output: list[dict[str, object]],
) -> None:
    for name, source, expected_valid, exact_error in cases:
        token_ids = encoding.encode(source)
        counters = run_source(
            solution, source, token_ids, expected_valid, exact_error, env
        )
        output.append({"corpus": corpus, "name": name, "counters": counters})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--official-root", type=Path, required=True)
    parser.add_argument("--solution", type=Path, default=ROOT / "solution")
    parser.add_argument("--seed", type=int, default=20260805)
    parser.add_argument("--cases-per-family", type=int, default=12)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    official = args.official_root.resolve()
    solution = args.solution.resolve()
    env = dict(os.environ)
    env["CANGJIE_PROFILE"] = "1"
    env.setdefault("TIKTOKEN_CACHE_DIR", str(official / "tiktoken_cache"))

    import tiktoken

    encoding = tiktoken.get_encoding("cl100k_base")
    registry = json.loads(
        (official / "wrong_error_positions.json").read_text(encoding="utf-8")
    )["wrong_examples"]
    official_cases = (
        (
            item["name"],
            (official / "wrong" / f"{item['name']}.cj").read_text(encoding="utf-8"),
            False,
            int(item["first_error_token_index"]),
        )
        for item in registry
    )
    project_cases = (
        (name, source, expected, None)
        for name, source, expected in _project_programs(ROOT / "main.py")
    )
    fuzz_cases = (
        (case.name, case.source, case.expected_valid, None)
        for case in generate_cases(args.seed, args.cases_per_family)
    )

    records: list[dict[str, object]] = []
    add_corpus("official", official_cases, solution, encoding, env, records)
    add_corpus("project", project_cases, solution, encoding, env, records)
    add_corpus("fuzz", fuzz_cases, solution, encoding, env, records)

    aggregate: dict[str, int] = {}
    counts: dict[str, int] = {}
    for record in records:
        corpus = str(record["corpus"])
        counts[corpus] = counts.get(corpus, 0) + 1
        for key, value in record["counters"].items():
            aggregate[key] = aggregate.get(key, 0) + int(value)

    report = {
        "seed": args.seed,
        "cases_per_family": args.cases_per_family,
        "corpora": counts,
        "total_cases": len(records),
        "aggregate": aggregate,
        "cases": records,
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
        print(json.dumps({key: report[key] for key in ("corpora", "total_cases", "aggregate")}, ensure_ascii=False, indent=2))
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
