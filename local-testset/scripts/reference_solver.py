#!/usr/bin/env python3
"""Dummy reference solver for `token_interaction_test.py`.

Reads one token ID per line from stdin; prints one line per round: "0" or "1"
using the **same** convention as the harness (not the competition PDF):
- ``"1"`` exactly on the round whose index equals ``first_error_token_index`` for
  stems listed in ``wrong_error_positions.json``; ``"0"`` before that.
- For other files, always ``"0"``.

Must be given the same ``--cangjie-file`` (and optional ``--encoding``, ``--error-json``)
as used by the harness for that test.

Example (from repo root):

  python3 scripts/token_interaction_test.py err_arity.cj \\
    --cmd python3 scripts/reference_solver.py --cangjie-file wrong/err_arity.cj
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
        name = item["name"]
        if "first_error_token_index" not in item:
            raise ValueError(
                f"{json_path}: entry {name!r} missing first_error_token_index."
            )
        out[name] = int(item["first_error_token_index"])
    return out


def resolve_cj_file(root: Path, user_arg: str) -> Path:
    p = Path(user_arg)
    if p.exists():
        return p.resolve()

    rel = user_arg
    if rel.startswith("samples/"):
        rel = rel[len("samples/") :]

    candidates = [
        root / rel,
        root / "wrong" / rel,
        root / "wrong" / Path(rel).name,
        root / Path(rel).name,
    ]
    for c in candidates:
        if c.exists():
            return c.resolve()
    raise FileNotFoundError(f"Cangjie file not found: {user_arg}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Reference stdin/stdout solver for token interaction tests.")
    parser.add_argument(
        "--cangjie-file",
        required=True,
        help="Path to the .cj file (same logical file as the harness tokenizes).",
    )
    parser.add_argument("--encoding", default="cl100k_base", help="tiktoken encoding (default: cl100k_base).")
    parser.add_argument(
        "--error-json",
        default=None,
        help="Path to wrong_error_positions.json (default: wrong_error_positions.json).",
    )
    args = parser.parse_args()

    root = repo_root()

    tiktoken_cache_dir = root / "tiktoken_cache"
    tiktoken_cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(tiktoken_cache_dir))

    import tiktoken  # pylint: disable=import-outside-toplevel

    error_json = (
        Path(args.error_json).resolve()
        if args.error_json
        else (root / "wrong_error_positions.json")
    )
    error_map = load_first_error_token_indices(error_json)

    cj_file = resolve_cj_file(root, args.cangjie_file)
    text = cj_file.read_text(encoding="utf-8")
    enc = tiktoken.get_encoding(args.encoding)
    token_ids = enc.encode(text)

    stem = cj_file.stem
    target_idx: int | None = error_map.get(stem)

    round_idx = 0
    for line in sys.stdin:
        line = line.strip()
        if line == "":
            continue
        received = int(line)
        if round_idx < len(token_ids) and received != token_ids[round_idx]:
            print(f"mismatch at round {round_idx}: expected {token_ids[round_idx]}, got {received}", file=sys.stderr)

        if target_idx is not None and round_idx == target_idx:
            print("1", flush=True)
        else:
            print("0", flush=True)
        round_idx += 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
