# 固定综合测试语料

本目录包含一套可重复生成、可人工阅读的仓颉前缀检查器回归语料。当前固定语料共有
`377` 例和 `350` 个强制覆盖目标，覆盖三类期望：

- `valid/`：完整且合法，所有 token 前缀都应继续接受；
- `invalid/`：包含已经提交、无法由后续输入修复的错误，应在错误之后拒绝且不能提前拒绝；
- `prefix/`：有意截断但仍可补全的前缀，检查器必须接受。这类用例专门防止把“源码尚未输入完”误判为错误。

`manifest.json` 使用 schema v3，记录每例的名称、覆盖族、期望、错误阶段、源码
路径、覆盖标签、源码字节数、已知安全前缀字节数，以及源码/安全前缀 SHA-256。
顶层 `integrity` 还锁定
整个语料的聚合 SHA-256，以及生成器、grammar、context 和仓库内 vendored
reference-derived 类型 oracle 的
依赖文件 SHA-256。语料包含：

- 全部基础字面量、整数/浮点后缀和原始标识符；
- 一元、二元、range、pipeline 及全部复合赋值运算符；
- 数组、可空、元组、函数及嵌套泛型类型；
- 全部语句和顶层声明产生式，包括异常、模式匹配、结构体、枚举、扩展和运算符声明；
- `context.json` 中每个全局函数、接口方法、构造器重载、字段、实例/静态方法和可迭代类型；
- 语法负例、语义负例和 39 种可继续补全的输入前缀；
- 多行调用、嵌套 lambda、重载、泛型接口继承及作用域隔离等随机程序；
- 深嵌套、长标识符、大数组、迟发错误和大量声明等规模压力场景。

完整的机器可校验覆盖表见 [`COVERAGE.md`](COVERAGE.md)。生成器发现任一强制目标
未被样例标记覆盖时会直接失败。

当前 `338` 个完整程序中有 `227` 个由仓库内 vendored reference-derived 类型 oracle
辅助复核。它不是赛事服务端判题器。其余完整例
不会默默跳过：每例都必须在 `oracle_skip_reason` 中保存机器可读原因。当前使用的
原因码为：

- `vendored_oracle_rejects_supported_source`：oracle 不支持该完整合法源码中的语法或上下文；
- `vendored_oracle_not_authoritative_for_rejection`：oracle 不能在目标错误上给出可靠的拒绝；
- `incomplete_prefix_not_supported_by_complete_oracle`：该例本来就是可补全前缀，不送入完整程序 oracle。

## 证据层级与门禁效力

377 例按证据强度分成三个互斥层级：

| 层级 | 数量 | 定义 | 正式效力 |
|---|---:|---|---|
| `authoritative` | 219 | `oracle=true` 且不属于 `scale_stress` | manifest 标签是硬门禁 |
| `diagnostic_spec_pending` | 149 | 非规模，但标签尚缺独立赛事规范/oracle 证明 | 差异必须记录，不单独否决 |
| `diagnostic_scale` | 9 | 全部 `scale_stress`，无论 oracle 标记 | 只诊断规模、超时与非线性增长 |

生产 grammar 层只证明样例标签与当前生产 grammar 一致，不是独立语法 oracle。竞赛
配套仓库也明确将其 Lark checker 定位为 subset typechecker。因此不能因为某个
`oracle=false` 样例被项目 grammar 接受，就把它自动提升为赛事服务端硬规范。

官方公开 50 例精确首错仍是最高优先级门禁。新增综合语料不得覆盖或放宽官方结果。
对于性能候选，authoritative 必须 `219/219`；同时，全部 368 个非规模样例必须与最近
一个已接受 control 严格逐 token 等价。后者用于锁定既有行为，不代表把 149 个
spec-pending 标签升级为 authoritative。

## 一键运行

先构建原生入口。默认 `all` 策略适合完整诊断，会把所有 manifest 标签差异作为失败：

```bash
./build.sh
python3 tools/run_comprehensive_cases.py --solution ./solution
```

正式非规模门禁使用分层策略，并同时验证赛题文字中的翻转输出协议：

```bash
python3 tools/run_comprehensive_cases.py \
  --solution ./solution \
  --check-competition-output \
  --expectation-policy oracle-backed \
  --skip-family scale_stress \
  --timeout 30 \
  --json /tmp/comprehensive-report.json
```

完整运行默认还检查 13 种协议输入边界，包括空行、非十进制、负数、溢出、越界 ID、
首个错误后立即停止和正负协议翻转。

全量 377 例双协议诊断会执行 `754` 次完整源码、`240` 次独立安全前缀和
`26` 次输入边界，单个 solution 共 `1020` 个新进程。上述正式非规模门禁对
368 例执行 `736 + 238 + 26 = 1000` 个进程；带 reference control 时 candidate 与
control 各运行一遍，合计 `2000` 个。每个 reject 的
`source[:safe_prefix_bytes]` 都会被独立重新编码并要求全程接受；默认与 competition
transcript 必须逐项互补，首次拒绝 token 和字节位置必须相同。

对行为保持不变的性能候选，还应同时提供最近一个已接受 control：

```bash
python3 tools/run_comprehensive_cases.py \
  --solution /candidate/solution \
  --reference-solution /control/solution \
  --check-competition-output \
  --expectation-policy oracle-backed \
  --skip-family scale_stress \
  --timeout 30 \
  --json /tmp/comprehensive-reference-diff.json
```

该模式对全部 368 个非规模样例严格比较完整源码、安全前缀和输入边界的逐 token
stdout、首次拒绝位置、退出状态、stderr 与进程异常。正确性修复本来就需要改变旧行为
时，不应把已知错误的旧 control 当成等价标准；修复应先独立达到 authoritative
`219/219`，再建立新的性能 control。

## 快速回归与压力测试

`scale_stress` 故意包含可能很慢的输入。日常回归与专项压力检测可以分开运行：

```bash
# 排除规模压力例，其余固定语料全部运行
python3 tools/run_comprehensive_cases.py \
  --solution ./solution \
  --expectation-policy oracle-backed \
  --skip-family scale_stress

# 只运行规模压力例；单例最多允许 30 秒
python3 tools/run_comprehensive_cases.py \
  --solution ./solution \
  --family scale_stress \
  --expectation-policy oracle-backed \
  --timeout 30
```

运行器不会为了“全绿”自动删除或改写样例。默认 `--expectation-policy all` 会把所有
标签差异作为失败，适合语料研发；正式优化使用 `oracle-backed`，只让 authoritative
标签差异进入失败，同时把 spec-pending 与 scale 差异保留在 JSON diagnostics 中。

按覆盖族或名称筛选，适合定位失败：

```bash
python3 tools/run_comprehensive_cases.py --list
python3 tools/run_comprehensive_cases.py --family collections
python3 tools/run_comprehensive_cases.py --skip-family scale_stress
python3 tools/run_comprehensive_cases.py --name interface
```

输出 JSON 报告供 CI 或后续脚本消费：

```bash
python3 tools/run_comprehensive_cases.py --json /tmp/comprehensive-report.json
```

运行器默认做三层检查：生产 grammar 确认完整/截断/语法错误标签，仓库内 vendored
类型 oracle 辅助复核其支持的完整程序，再通过 `cl100k_base` 编码逐 token 驱动真实
`solution`。grammar 层属于锁定生产语法的一致性检查，不是独立语法 oracle。
生产协议层检查输出值、输出数量、首次拒绝、拒绝后立即停止、安全前缀不被提前拒绝，
以及非法 token ID 输入。可分别使用 `--skip-grammar`、`--skip-oracle` 或
`--skip-protocol` 关闭某一层；这些 skip 选项只用于定位，不得用于正式门禁。

## 重新生成与一致性检查

语料由确定性脚本生成，固定随机种子，不依赖当前时间：

```bash
python3 tools/generate_comprehensive_cases.py
python3 tools/generate_comprehensive_cases.py --check
```

新增测试时应修改生成器并重新生成，避免直接修改派生的 `.cj` 或 `manifest.json`。
为避免误删或覆盖，`--output` 只允许指向空/尚未存在的目录，或同时通过 ownership
marker、schema、逐文件哈希与聚合哈希校验的语料目录。未知、陈旧或与当前目标同路径但
字节不同的 `.cj` 都会在写入前整体拒绝，生成器不会自动删除或覆盖它们。

默认种子固定为 `20260805`，因此仓库回归语料可稳定复现。若希望每次获得不同的随机
语义程序，可运行：

```bash
# 未传 --seed 时，每次自动选择并打印新的随机种子
python3 tools/run_fresh_comprehensive_cases.py \
  --solution ./solution \
  --quick

# 指定种子可精确复现一次随机失败，并可保留全部源码
python3 tools/run_fresh_comprehensive_cases.py \
  --solution ./solution \
  --seed 123456 \
  --cases-per-family 30 \
  --output /tmp/cangjie-seed-123456 \
  --json /tmp/cangjie-seed-123456.json
```

随机运行器只在临时目录生成测试数据；未指定 `--output` 时退出后自动清理，不修改生产
代码、语法或上下文。

## 当前生产版本状态

以下结果仅对应 2026-08-13 的旧 373 例语料快照，不代表当前 377 例语料的复验结果。
当时在官方 Linux AArch64 镜像测试生产逻辑 `58f03c7`（仓库锚点
`3d745b6`）：静态 grammar `364/364`、vendored oracle `227/227`、原有官方
`50/50` 精确首错、原 oracle 语料 `45/45` 和项目语料 `57/57` 均通过。最终
`oracle-backed` 运行摘要为 `371/373`，其中：

- authoritative：`217/219`，2 个明确 false reject；
- diagnostic_spec_pending：145 例中有 40 个标签差异；
- diagnostic_scale：9 例中有 2 个 30 秒超时。

若统一按全部 manifest 标签观察，原始匹配数为 `329/373`，但不能据此把全部标签当作
赛事规范。恢复性能优化只需先修复两个 authoritative 缺陷并建立 `219/219` control；
40 个规范待确认差异和 2 个规模超时继续保留诊断，不要求通过修改实现凑成
`373/373`。禁止删除样例、篡改证据层级、放宽安全前缀或按样例特化。旧版结果报告已
作为参赛资料归档，不再由公开仓库承载。
