#!/usr/bin/env python3
"""交互式逐 token 演示:输入一句仓颉代码,实时看每一轮的 0/1 输出。

用法:
    python3 demo_interactive.py                 # 菜单选择内置示例
    python3 demo_interactive.py "源码字符串"     # 直接演示自定义源码
    python3 demo_interactive.py --sel 6         # 直接跑第 6 个内置示例
"""

import subprocess
import sys

import tiktoken

# (标题, 讲解, 源码)
EXAMPLES = [
    ("合法程序:每个前缀都能续写 → 全程 0",
     "没有任何错误,每轮都可续写。",
     'main(): Unit {\n    let x: Int64 = 42\n    println(x)\n}\n'),
    ("循环外 break → break 出现的那一轮报 1",
     "第 5 轮 token=' break' 到达即报错:之后无论输入什么,新循环都包不住已经出现的 break。",
     'main(): Unit {\n    break\n}\n'),
    ("给 let 变量赋值 → 在下一语句边界才报 1",
     "注意:x = 2 出现时先不报,到第 20 轮(下一个语句提交点,最后的 '}\\n')才锁存——这就是'提交边界'。",
     'main(): Unit {\n    let x: Int64 = 1\n    x = 2\n}\n'),
    ("if 条件不是 Bool → 条件闭合的 ')' 那一轮报 1",
     "第 8 轮 token=')' 到达才报:条件没闭合前,可能继续写 || true 把它变成 Bool。",
     'main(): Unit {\n    if (1) {\n    }\n}\n'),
    ("使用未定义变量 → 名字提交的那一轮报 1",
     "第 8 轮 token=' z' 到达即报:标识符已经写完,名字定死了,找不到这个变量。",
     'main(): Unit {\n    let y = z\n}\n'),
    ("数组元素类型错 → 延迟到 ']' 闭合才报(Alive 延迟的活例子)",
     "输入到 '\"x' 时不报(数组还没闭合,元素还可以续写,Alive/延迟);到第 15 轮 '\"]\\n' 闭合才报。",
     'main(): Unit {\n    let a: Array<Int64> = ["x"]\n}\n'),
    ("合法 if:全程 0",
     "条件本身就是 Bool,无错误。",
     'main(): Unit {\n    let b = true\n    if (b) {\n        println(1)\n    }\n}\n'),
]

RED = "\033[31m"
GREEN = "\033[32m"
BOLD = "\033[1m"
RESET = "\033[0m"


def run_one(source: str, explain: str = "") -> None:
    enc = tiktoken.get_encoding("cl100k_base")
    ids = enc.encode(source)
    texts = [
        enc.decode_single_token_bytes(t).decode("utf-8", errors="replace")
        for t in ids
    ]

    proc = subprocess.Popen(
        ["./solution"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        text=True, bufsize=1,
    )
    assert proc.stdin is not None and proc.stdout is not None

    prefix = ""
    print()
    print(f"{BOLD}源码(编码前){RESET}: {source!r}")
    print(f"共 {len(ids)} 个 cl100k token,逐轮输入 → solution 实时回答 0/1:")
    print("-" * 78)
    for i, tid in enumerate(ids):
        proc.stdin.write(f"{tid}\n")
        proc.stdin.flush()
        line = proc.stdout.readline().strip()
        prefix += texts[i]
        tail = prefix[-52:].replace("\n", "⏎")
        if line == "1":
            mark = f" {RED}◀ 首错!此轮之后不再可续写{RESET}"
            print(f"第{i:>3}轮 | token={texts[i]!r:<16} | {RED}输出 1{RESET} | {tail}{mark}")
            break
        print(f"第{i:>3}轮 | token={texts[i]!r:<16} | {GREEN}输出 0{RESET} | {tail}")
    else:
        print(f"{GREEN}→ 全程 0:每个前缀都能续写成合法程序 ✅{RESET}")
    print("-" * 78)
    if explain:
        print(f"{BOLD}讲解:{RESET} {explain}")
    print()


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "--sel":
        idx = int(args[1]) - 1
        title, explain, src = EXAMPLES[idx]
        print(f"== 示例 {idx + 1}:{title} ==")
        run_one(src, explain)
        return 0
    if args:
        run_one(" ".join(args))
        return 0

    print("== 仓颉前缀检查器 · 交互式逐 token 演示 ==")
    print("选择内置示例(演示时推荐):")
    for i, (title, _, _) in enumerate(EXAMPLES, 1):
        print(f"  {i}. {title}")
    print("  0. 自定义输入(多行,空行结束)")
    choice = input("> ").strip()
    if choice == "0":
        print("输入仓颉代码(空行结束):")
        lines = []
        while True:
            line = input()
            if line == "":
                break
            lines.append(line)
        run_one("\n".join(lines) + "\n")
        return 0
    idx = int(choice) - 1
    if not (0 <= idx < len(EXAMPLES)):
        print("无效选择")
        return 1
    title, explain, src = EXAMPLES[idx]
    print(f"== 示例 {choice}:{title} ==")
    run_one(src, explain)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
