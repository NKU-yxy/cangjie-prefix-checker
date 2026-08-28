#!/usr/bin/env bash
# 答辩演示脚本:一条命令跑完"构建 → 协议 → 精确首错 → 官方harness"
# 用法:
#   bash demo_defense.sh          # 默认:构建 + 合法程序 + 精确首错 + 官方harness
#   bash demo_defense.sh --full   # 再加:50 例全量锚点统计
set -euo pipefail
cd "$(dirname "$0")"

echo "================================================================"
echo " 仓颉前缀检查器 · 答辩演示"
echo "================================================================"

# ---------- 第 0 步:构建 ----------
echo
echo "[0/4] 检查/构建 solution"
if [[ ! -x ./solution ]]; then
    echo "  未找到 solution,执行 ./build.sh(生成 token 表 + 编译 C++)..."
    ./build.sh
fi
echo "  solution: $(file -b solution | cut -d, -f1,2)  ✅"

# ---------- 第 1 步:合法程序协议演示 ----------
echo
echo "[1/4] 协议演示:合法程序应全程输出 0(可续写)"
python3 - <<'PY'
import tiktoken
src = 'main(): Unit {\n    let value: Int64 = 42\n    println(value)\n}\n'
enc = tiktoken.get_encoding("cl100k_base")
ids = enc.encode(src)
with open("/tmp/demo_valid.tokens", "w") as f:
    for tid in ids:
        f.write(f"{tid}\n")
print(f"  源码: {src!r}")
print(f"  编码后共 {len(ids)} 个 cl100k token ID,逐行喂给 solution")
PY
echo -n "  solution 输出:"
./solution < /tmp/demo_valid.tokens | tr -d '\n' | sed 's/0/0 /g'
echo ""
if ./solution < /tmp/demo_valid.tokens | grep -q "1"; then
    echo "  ❌ 出现了 1(误报!)"
    exit 1
else
    echo "  ✅ 全程 0,合法程序零误报"
fi

# ---------- 第 2 步:错误样例精确首错 ----------
echo
echo "[2/4] 精确首错演示:官方样例 err_break.cj(循环外 break)"
python3 - <<'PY'
import json, tiktoken
src = open("local-testset/wrong/err_break.cj", encoding="utf-8").read()
enc = tiktoken.get_encoding("cl100k_base")
ids = enc.encode(src)
with open("/tmp/demo_break.tokens", "w") as f:
    for tid in ids:
        f.write(f"{tid}\n")
official = None
for it in json.load(open("local-testset/wrong_error_positions.json"))["wrong_examples"]:
    if it["name"] == "err_break":
        official = it["first_error_token_index"]
print(f"  样例共 {len(ids)} 个 token")
print(f"  官方标注首错位置: 第 {official} 轮(0-based)")
PY
./solution < /tmp/demo_break.tokens > /tmp/demo_break.out
python3 - <<'PY'
outs = open("/tmp/demo_break.out").read().split()
first_1 = outs.index("1") if "1" in outs else -1
official = 356
print(f"  我们报错在第 {first_1} 轮(前面 {first_1} 轮全部输出 0)")
if first_1 == official:
    print(f"  ✅ 与官方标注完全一致(第 {official} 轮 = ' break' 关键字出现的那一轮)")
else:
    print(f"  ❌ 期望 {official},实际 {first_1}")
PY

# ---------- 第 3 步:官方 harness ----------
echo
echo "[3/4] 官方交互 harness 判定(token_interaction_test.py)"
echo "  (逐 token 交互,期望:前 356 轮 0、第 356 轮 1 → 输出 PASSED/FAILED)"
python3 local-testset/scripts/token_interaction_test.py \
    local-testset/wrong/err_break.cj --cmd ./solution

# ---------- 第 4 步(可选):50 例全量统计 ----------
if [[ "${1:-}" == "--full" ]]; then
echo
echo "[4/4] 官方 50 个错误样例全量精确首错统计(--full)"
python3 - <<'PY'
import json, subprocess, tiktoken
enc = tiktoken.get_encoding("cl100k_base")
anchors = {it["name"]: it["first_error_token_index"]
           for it in json.load(open("local-testset/wrong_error_positions.json"))["wrong_examples"]}
passed = 0
diffs = []
for name, official in anchors.items():
    src = open(f"local-testset/wrong/{name}.cj", encoding="utf-8").read()
    ids = enc.encode(src)
    tok_in = "\n".join(map(str, ids)) + "\n"
    out = subprocess.run(["./solution"], input=tok_in, capture_output=True, text=True).stdout.split()
    first_1 = out.index("1") if "1" in out else -1
    if first_1 == official:
        passed += 1
    else:
        diffs.append((name, official, first_1))
print(f"  与仓库内锚点完全一致: {passed}/50")
if diffs:
    print("  其余样例与锚点差异(锚点/实际):")
    for name, official, got in diffs:
        print(f"    {name}: 锚点 {official},实际 {got}(差 {got-official:+d} 轮)")
    print("  说明:仓库内锚点为官方当时公开锚点(人工可续写性分析),")
    print("  答辩报告已注明其与决赛口径不同,不作为最终版本复验结论;")
    print("  当前版本的最终判定以决赛平台评分(63.00/WA)为准。")
else:
    print("  ✅ 全部 50 例首错位置与官方标注一一对应")
PY
fi

echo
echo "================================================================"
echo " 演示结束"
echo "================================================================"
