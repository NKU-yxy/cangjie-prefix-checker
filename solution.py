#!/usr/bin/env python3
"""Competition stdin/stdout entry point."""

from __future__ import annotations

import argparse
import os
import sys

os.environ["TVM_FFI_BUILD_DOCS"] = "1"


# 返回项目根目录（本文件所在目录）
def _project_root() -> str:
    return os.path.dirname(os.path.abspath(__file__))


# 返回运行时目录（打包环境下为可执行文件所在目录，否则为项目根目录）
def _runtime_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return _project_root()


# 把项目根目录加入 sys.path，保证内部模块可导入
def _bootstrap_path() -> None:
    root = _project_root()
    if root not in sys.path:
        sys.path.insert(0, root)


# 解析命令行参数（--context / --grammar / --semantic-mode / --competition-output）
def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--context", default=None, help="Optional context.json path")
    parser.add_argument("--grammar", default=None, help="Optional token-level GBNF path")
    parser.add_argument(
        "--semantic-mode",
        choices=("checkpoint", "fast", "legacy"),
        default=None,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--cangjie-file", default=None, help=argparse.SUPPRESS)
    parser.add_argument(
        "--competition-output",
        action="store_true",
        help="Use problem statement convention: 1=continuable, 0=error. Default matches public harness.",
    )
    args, _unknown = parser.parse_known_args(argv)
    return args


# 按协议输出一个判断结果（默认 0=可继续/1=错误，--competition-output 翻转）
def _emit(ok: bool, *, competition_output: bool) -> None:
    if competition_output:
        print(1 if ok else 0, flush=True)
    else:
        print(0 if ok else 1, flush=True)


# 输出一次错误结果并返回退出码（输入非法时调用）
def _fail(args: argparse.Namespace) -> int:
    _emit(False, competition_output=args.competition_output)
    return 0


# 主流程：逐行读取 token ID，解码后交给流式检查器，逐 token 输出判断结果
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
        checker = CangjieStreamChecker(
            grammar_path=args.grammar,
            context_path=context_path,
            semantic_mode=args.semantic_mode,
        )
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
