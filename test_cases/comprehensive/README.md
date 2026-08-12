# 固定综合测试语料

本目录包含一套可重复生成、可人工阅读的仓颉前缀检查器回归语料。当前语料覆盖三类期望：

- `valid/`：完整且合法，所有 token 前缀都应继续接受；
- `invalid/`：包含已经提交、无法由后续输入修复的错误，应在错误之后拒绝且不能提前拒绝；
- `prefix/`：有意截断但仍可补全的前缀，检查器必须接受。这类用例专门防止把“源码尚未输入完”误判为错误。

`manifest.json` 记录每例的名称、覆盖族、期望、源码路径和已知安全前缀字节数。语料包含手工边界样例，以及固定种子生成的多行调用、嵌套 lambda、重载、泛型接口继承、作用域隔离等隐藏样例式程序。

## 一键运行

先构建原生入口，再运行：

```bash
./build.sh
python3 tools/run_comprehensive_cases.py --solution ./solution
```

同时验证赛题文字中的翻转输出协议：

```bash
python3 tools/run_comprehensive_cases.py \
  --solution ./solution \
  --check-competition-output
```

按覆盖族或名称筛选，适合定位失败：

```bash
python3 tools/run_comprehensive_cases.py --list
python3 tools/run_comprehensive_cases.py --family collections
python3 tools/run_comprehensive_cases.py --name interface
```

输出 JSON 报告供 CI 或后续脚本消费：

```bash
python3 tools/run_comprehensive_cases.py --json /tmp/comprehensive-report.json
```

运行器默认做两层检查：先用仓库内的官方类型检查器确认完整程序标签，再通过 `cl100k_base` 编码逐 token 驱动真实 `solution`，检查输出值、输出数量、首次拒绝、拒绝后立即停止及安全前缀不被提前拒绝。`--skip-oracle` 可用于只测生产协议。

## 重新生成与一致性检查

语料由确定性脚本生成，固定随机种子，不依赖当前时间：

```bash
python3 tools/generate_comprehensive_cases.py
python3 tools/generate_comprehensive_cases.py --check
```

新增测试时应修改生成器并重新生成，避免直接修改派生的 `.cj` 或 `manifest.json`。
