#!/usr/bin/env python3
"""Tokenize a file with tiktoken.

This script sets TIKTOKEN_CACHE_DIR to tiktoken_cache/ by default, so
the *internal* tiktoken encoding cache is stored under the repo root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def build_cache_path(repo_root: Path, source_file: Path, encoding_name: str) -> Path:
    """Create a stable output path under token_cache/."""
    token_cache_dir = repo_root / "token_cache"
    token_cache_dir.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256()
    digest.update(str(source_file.resolve()).encode("utf-8"))
    digest.update(str(source_file.stat().st_mtime_ns).encode("utf-8"))
    digest.update(str(source_file.stat().st_size).encode("utf-8"))
    digest.update(encoding_name.encode("utf-8"))
    key = digest.hexdigest()[:16]

    return token_cache_dir / f"{source_file.stem}.{encoding_name}.{key}.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Tokenize a file with tiktoken. Internal tiktoken cache is written "
            "under tiktoken_cache/."
        )
    )
    parser.add_argument("file", help="Path to input file.")
    parser.add_argument(
        "--encoding",
        default="cl100k_base",
        help="tiktoken encoding name (default: cl100k_base).",
    )
    parser.add_argument(
        "--print-tokens",
        action="store_true",
        help="Print token ID list to stdout.",
    )
    parser.add_argument(
        "--save-token-ids",
        action="store_true",
        help="Also save token IDs JSON under token_cache/ (off by default).",
    )
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent
    tiktoken_cache_dir = repo_root / "tiktoken_cache"
    tiktoken_cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(tiktoken_cache_dir))

    # Import after setting TIKTOKEN_CACHE_DIR so first-time downloads use tiktoken_cache/.
    import tiktoken  # pylint: disable=import-outside-toplevel

    source_file = Path(args.file).resolve()

    if not source_file.exists() or not source_file.is_file():
        raise SystemExit(f"Input file not found: {source_file}")

    text = source_file.read_text(encoding="utf-8")
    encoding = tiktoken.get_encoding(args.encoding)
    token_ids = encoding.encode(text)

    print(f"source: {source_file}")
    print(f"encoding: {args.encoding}")
    print(f"token_count: {len(token_ids)}")
    print(f"tiktoken_cache_dir: {tiktoken_cache_dir}")
    if args.save_token_ids:
        cache_path = build_cache_path(repo_root, source_file, args.encoding)
        payload = {
            "source_file": str(source_file),
            "encoding": args.encoding,
            "token_count": len(token_ids),
            "token_ids": token_ids,
        }
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"token_ids_cache_file: {cache_path}")
    if args.print_tokens:
        print(token_ids)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
