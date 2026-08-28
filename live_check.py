#!/usr/bin/env python3
"""实时检查器:输入一段仓颉源码,输出逐 token 的 0/1(0=可续写,1=首错)。

用法:
    python3 live_check.py                # 交互模式:多行输入,空行结束
    python3 live_check.py "源码"         # 直接传一段源码
    python3 live_check.py < file.cj      # 或从文件读入
"""

import subprocess
import sys

import tiktoken

enc = tiktoken.get_encoding("cl100k_base")


def check(source: str) -> None:
    ids = enc.encode(source)
    if not ids:
        print("(空源码)")
        return
    # 把每个 token ID 还原成文本,输出时和 0/1 一一对应
    texts = [
        enc.decode_single_token_bytes(t).decode("utf-8", errors="replace")
        for t in ids
    ]
    # 启动 solution,逐 token 交互(和官方 harness 的喂法一致)
    proc = subprocess.Popen(
        ["./solution"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        text=True, bufsize=1,
    )
    assert proc.stdin is not None and proc.stdout is not None

    # 逐 token 交互并输出(0=可续写,1=首错;首错后 checker 立即退出,不再判定)
    width = len(str(len(ids) - 1))
    tokw = max(len(repr(t)) for t in texts)
    print(f"共 {len(ids)} 个 token:")
    first_err = -1
    for i, tid in enumerate(ids):
        proc.stdin.write(f"{tid}\n")
        proc.stdin.flush()
        s = proc.stdout.readline().strip()
        print(f"  第 {i:>{width}} 轮 | {texts[i]!r:<{tokw}} | {s}{'  ← 首错' if s == '1' else ''}")
        if s == "1":
            first_err = i
            break
    proc.terminate()

    if first_err >= 0:
        print(f"→ 首错在第 {first_err} 轮,该 token 为 {texts[first_err]!r};")
        print(f"  (首错后 checker 立即退出,后续 {len(ids) - first_err - 1} 个 token 不再判定)")
    else:
        print("→ 合法:全程可续写")


def main() -> None:
    args = sys.argv[1:]
    if args:
        check(" ".join(args))
        return
    if not sys.stdin.isatty():
        # 管道/文件输入:直接读全部内容检查一次
        check(sys.stdin.read())
        return

    print("输入仓颉源码(多行输入,空行结束;Ctrl+C 退出)")
    while True:
        try:
            lines: list[str] = []
            while True:
                line = input()
                if line == "":
                    break
                lines.append(line)
            if not lines:
                continue
            check("\n".join(lines) + "\n")
            print()
        except (KeyboardInterrupt, EOFError):
            print("\nbye")
            return


if __name__ == "__main__":
    main()
