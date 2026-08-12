#!/usr/bin/env python3
"""Generate and run a fresh seeded comprehensive suite in a temporary folder."""

from __future__ import annotations

import argparse
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Combine the fixed grammar/context matrix with newly generated "
            "semantic programs. A random seed is chosen unless --seed is supplied."
        )
    )
    parser.add_argument("--solution", type=Path, default=ROOT / "solution")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--cases-per-family", type=int, default=20)
    parser.add_argument("--output", type=Path, help="Keep the generated corpus here.")
    parser.add_argument("--json", type=Path, help="Write the validation report here.")
    parser.add_argument("--check-competition-output", action="store_true")
    parser.add_argument("--skip-oracle", action="store_true")
    parser.add_argument("--skip-grammar", action="store_true")
    parser.add_argument("--skip-protocol", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Exclude the deliberately slow scale_stress family.",
    )
    args = parser.parse_args()
    if args.cases_per_family < 0:
        parser.error("--cases-per-family must be non-negative")

    seed = args.seed if args.seed is not None else secrets.randbits(63)
    print(f"fresh comprehensive seed: {seed}", flush=True)

    temporary: tempfile.TemporaryDirectory[str] | None = None
    if args.output:
        output = args.output.resolve()
    else:
        temporary = tempfile.TemporaryDirectory(prefix="cangjie-comprehensive-")
        output = Path(temporary.name)

    generate = subprocess.run(
        [
            sys.executable,
            "tools/generate_comprehensive_cases.py",
            "--seed",
            str(seed),
            "--generated-cases-per-family",
            str(args.cases_per_family),
            "--output",
            str(output),
        ],
        cwd=ROOT,
        check=False,
    )
    if generate.returncode != 0:
        if temporary is not None:
            temporary.cleanup()
        return generate.returncode

    command = [
        sys.executable,
        "tools/run_comprehensive_cases.py",
        "--manifest",
        str(output / "manifest.json"),
        "--solution",
        str(args.solution.resolve()),
    ]
    for enabled, flag in (
        (args.check_competition_output, "--check-competition-output"),
        (args.skip_oracle, "--skip-oracle"),
        (args.skip_grammar, "--skip-grammar"),
        (args.skip_protocol, "--skip-protocol"),
        (args.fail_fast, "--fail-fast"),
    ):
        if enabled:
            command.append(flag)
    if args.json:
        command.extend(("--json", str(args.json.resolve())))
    if args.quick:
        command.extend(("--skip-family", "scale_stress"))
    validate = subprocess.run(command, cwd=ROOT, check=False)
    if temporary is not None:
        temporary.cleanup()
    elif args.output:
        print(f"generated corpus retained at: {output}")
    return validate.returncode


if __name__ == "__main__":
    raise SystemExit(main())
