#!/usr/bin/env python3
"""Competition stdin/stdout entry point."""

from __future__ import annotations

import argparse
import os
import sys

os.environ["TVM_FFI_BUILD_DOCS"] = "1"


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
    parser.add_argument("--cangjie-file", default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--competition-output",
        action="store_true",
        help="Use problem statement convention: 1=continuable, 0=error. Default matches public harness.",
    )
    args, _unknown = parser.parse_known_args(argv)
    return args


def _emit(ok: bool, *, competition_output: bool) -> None:
    if competition_output:
        print(1 if ok else 0, flush=True)
    else:
        print(0 if ok else 1, flush=True)


def _fail(args: argparse.Namespace) -> int:
    _emit(False, competition_output=args.competition_output)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _bootstrap_path()

    try:
        import tiktoken
        from src.context_loader import find_context_path
        from src.stream_checker import CangjieStreamChecker
    except Exception as exc:
        print(f"startup error: {exc}", file=sys.stderr)
        return 1

    try:
        encoding = tiktoken.get_encoding("cl100k_base")
        context_path = find_context_path(args.context, runtime_dir=_runtime_dir())
        checker = CangjieStreamChecker(grammar_path=args.grammar, context_path=context_path)
    except Exception as exc:
        print(f"initialization error: {exc}", file=sys.stderr)
        return 1

    for line in sys.stdin:
        raw = line.strip()
        if not raw:
            return _fail(args)
        try:
            token_id = int(raw)
            decoded = encoding.decode([token_id])
        except Exception:
            return _fail(args)

        status = checker.feed_text(decoded)
        if not status.ok:
            return _fail(args)
        _emit(True, competition_output=args.competition_output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
