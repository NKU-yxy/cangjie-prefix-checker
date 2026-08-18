#!/usr/bin/env python3
"""Intentionally wrong solver for exercising `token_interaction_test.py`.

Uses the same stdin/stdout protocol as `reference_solver.py`. Modes:

- ``never`` — always ``"0"`` (never report an error).
- ``always`` — always ``"1"`` (report error on every round).
- ``early`` — ``"1"`` one token before ``first_error_token_index`` (if any).
- ``late`` — ``"1"`` one token after ``first_error_token_index`` (if any).
- ``off_by_one_high`` — alias for ``late``.
- ``off_by_one_low`` — alias for ``early``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_first_error_token_indices(json_path: Path) -> dict[str, int]:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    out: dict[str, int] = {}
    for item in data.get("wrong_examples", []):
        out[item["name"]] = int(item["first_error_token_index"])
    return out


def resolve_cj_file(root: Path, user_arg: str) -> Path:
    p = Path(user_arg)
    if p.exists():
        return p.resolve()

    rel = user_arg
    if rel.startswith("samples/"):
        rel = rel[len("samples/") :]

    for candidate in (
        root / rel,
        root / "wrong" / rel,
        root / "wrong" / Path(rel).name,
        root / Path(rel).name,
    ):
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError(f"Cangjie file not found: {user_arg}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Faulty solver for harness regression tests.")
    parser.add_argument("--cangjie-file", required=True)
    parser.add_argument("--encoding", default="cl100k_base")
    parser.add_argument("--error-json", default=None)
    parser.add_argument(
        "--mode",
        choices=("never", "always", "early", "late", "off_by_one_low", "off_by_one_high"),
        default="never",
    )
    args = parser.parse_args()

    root = repo_root()
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(root / "tiktoken_cache"))

    import tiktoken  # pylint: disable=import-outside-toplevel

    error_json = (
        Path(args.error_json).resolve()
        if args.error_json
        else (root / "wrong_error_positions.json")
    )
    error_map = load_first_error_token_indices(error_json)
    cj_file = resolve_cj_file(root, args.cangjie_file)
    enc = tiktoken.get_encoding(args.encoding)
    token_count = len(enc.encode(cj_file.read_text(encoding="utf-8")))

    stem = cj_file.stem
    target_idx: int | None = error_map.get(stem)
    mode = args.mode
    if mode == "off_by_one_low":
        mode = "early"
    elif mode == "off_by_one_high":
        mode = "late"

    round_idx = 0
    for _line in sys.stdin:
        if mode == "never":
            ans = "0"
        elif mode == "always":
            ans = "1"
        elif mode == "early":
            ans = "1" if target_idx is not None and round_idx == target_idx - 1 else "0"
        elif mode == "late":
            ans = "1" if target_idx is not None and round_idx == target_idx + 1 else "0"
        else:
            ans = "0"
        print(ans, flush=True)
        round_idx += 1
        if ans == "1" and mode in ("always", "early", "late"):
            if mode != "always":
                break

    _ = token_count
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
