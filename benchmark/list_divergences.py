#!/usr/bin/env python3
"""List divergence details from an explicitly selected JSON report."""

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="Differential failure JSON report")
    args = parser.parse_args()

    try:
        data = json.loads(args.report.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        parser.error(f"cannot read {args.report}: {error}")

    items = data if isinstance(data, list) else data.get("divergences", [])
    for item in items:
        source = item["source"]
        lines = [
            line.strip()
            for line in source.splitlines()
            if line.strip()
            and not line.strip().startswith(("func ", "}", "{", "main"))
        ]
        statement = lines[-1] if lines else "?"
        print(
            "{} gt={:<4d} sol={} | {} | {}".format(
                item["kind"][:14],
                item["gt"],
                item["solution"],
                item["desc"][:26],
                statement[:75],
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
