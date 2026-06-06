#!/usr/bin/env python3
"""Competition stdin/stdout entry point."""

from __future__ import annotations

import argparse
import os
import sys


def _project_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _runtime_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return _project_root()


def _bootstrap_path() -> None:
    root = _project_root()
    if root not in sys.path:
        sys.path.insert(0, root)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--context", default=None, help="Optional context.json path")
    parser.add_argument("--grammar", default=None, help="Optional token-level GBNF path")
    return parser.parse_args(argv)


def _fail() -> int:
    print(0, flush=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _bootstrap_path()

    try:
        import tiktoken
        from src.context_loader import find_context_path, load_context
        from src.stream_checker import CangjieStreamChecker
    except Exception as exc:
        print(f"startup error: {exc}", file=sys.stderr)
        return 1

    try:
        encoding = tiktoken.get_encoding("cl100k_base")
        context_path = find_context_path(args.context, runtime_dir=_runtime_dir())
        context = load_context(context_path)
        checker = CangjieStreamChecker(grammar_path=args.grammar, preload_context=context)
    except Exception as exc:
        print(f"initialization error: {exc}", file=sys.stderr)
        return 1

    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            return _fail()
        try:
            token_id = int(raw)
            decoded = encoding.decode([token_id])
        except Exception:
            return _fail()

        status = checker.feed_text(decoded)
        if not status.ok:
            return _fail()
        print(1, flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
