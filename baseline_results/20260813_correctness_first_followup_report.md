# 2026-08-13 正确率优先的后续优化报告

## 结论

本轮已完成“先修正确性，再按门槛测性能”的计划：

1. 修复 lambda/IIFE 前缀和 call/member/index 链的两处通用过早拒绝；
2. authoritative 从 `217/219` 恢复为 `219/219`；
3. 官方 50 例仍为精确首错 `50/50`；
4. 完成 624 例细粒度 AArch64 画像；
5. 快速退出和控制流索引在实施前因理论上限不足而停止；
6. DeclarationSnapshot 候选完成全正确性门禁和三轮正式 A/B/A，但收益
   未达 5%，已回退；
7. 两个 scale 超时已定位到 XGrammar/grammar 状态膨胀，本轮不修改锁定
   grammar。

当前生产逻辑与 `68d780d` 一致；`68d780d` 中新增的画像代码在正式构建中
完全关闭。本轮只保存在本地 Git，未推送远程。

## 正确性修复

### `6382994` - lambda/IIFE 前缀

- 只有顶层换行、分号或真正的函数体闭合才是语义提交点；
- lambda 内层 block 的 `}` 不再误当成外层声明完成；
- 可继续追加 IIFE 调用后缀时，不提前用 lambda 类型拒绝外层变量声明；
- lambda 内部已确定的参数、arity 和返回类型错误仍即时报告。

### `c35afae` - call/member/index 链

- 未闭合调用保留已推导信息，但不用它触发外层类型不匹配；
- call、array、member 和 index 成功结果标记为仍可被后缀改变；
- 已确定的调用参数类型、arity、未知成员和索引类型错误仍即时报告；
- 新增 4 个通用合法链和 8 个已提交确定错误，均覆盖
  whole/byte/random/line/cl100k。

最终 AArch64 门禁：

- unittest `57/57`；
- native fragment `66 x 4`；
- native context `7/7`；
- hidden fuzz：seed `20260805`，`144 x 5`，零失败；
- official/oracle/project：`50/50` / `45/45` / `57/57`；
- non-scale comprehensive：`364/364`，authoritative `219/219`；
- ASan/UBSan 全过。

## AArch64 画像与候选判断

画像提交为 `68d780d`，覆盖 official 50、project 57、fuzz 144 和
comprehensive 373，共 624 例；622 例完成画像，只有两个既知 scale
超时。原始文件为 `20260813_correctness_control_arm64_profile_624.json`，
SHA-256：`deb9329d73bce92ff8edd6f4d4c773e20d5e6413061dd1ecbdd88c997f8f1db1`。

### 候选 A：首错后快速退出

official 50 例中对 syntax、TokenTable 和 semantic 对象析构的进程内计时总和仅
`16.552 ms`，约占正式同轮 control SUM 的 `1.1%`。这远低于计划规定的
6% 实施门槛，因此没有在生产代码中加入 `std::_Exit`。此外它会跳过画像输出、
LSan 和静态析构，不符合正确率优先的可诊断性要求。

### 候选 B：DeclarationSnapshot 单次候选扫描

`735a52e` 使用一次原始字节候选定位，再从每个可能起点运行原有 8 族
regex。它保留了每族独立的匹配语言、非重叠顺序、捕获组、offset、
optional close、single/multiline 行为，也保留注释和字符串中的旧 regex 行为。

官方 Linux AArch64 的 production、独立旧 regex shadow 和 ASan/UBSan+shadow 全部通过。
它与 `68d780d` 在 364 个非规模样例的 728 次协议、238 次安全前缀和
26 次边界输入上严格一致。

性能结果：

| 轮次 | Control SUM | Candidate SUM | 改善 | 漂移 | WIN/LOSS |
|---|---:|---:|---:|---:|---:|
| 1+9 | 1534.476 | 1469.590 | 4.229% | 0.478% | 32/0 |
| 1+21 R1 | 1551.804 | 1481.171 | 4.552% | 1.858% | 36/0 |
| 1+21 R2 | 1579.640 | 1504.180 | 4.777% | 0.427% | 36/0 |

两轮扩展验证均未达 `SUM >= 5%`，因此最终为
**PROVISIONAL（扩展后未升格）**，不能成为 accepted control。`75e9702` 已回退
生产代码。完整结论和 7,650 次原始实测见本目录的
`20260813_snapshot_candidate_index_*`。

### 候选 C：commit 级控制流索引

official 50 的画像中：

- `CheckRangeSteps` regex：`46.610 ms`；
- `CheckIfBranchJoins` regex：`57.115 ms`；
- 刻意放大的完全消除上限：`103.725 ms`。

按正式同轮 control SUM 计算，这个上限只占约 `6.6%-6.8%`，低于计划
预先锁定的 7% 进入门槛，而且还没有扣除新索引和 anchored regex 的成本。
因此本轮不实施，也不与上一个未升格候选叠加。

## Scale 超时诊断

### 4KB identifier

- 4,135 字节，527 个 cl100k token；
- 纯 native semantic 处理全部前缀约 `12.8 ms`；
- 完整 solution 45 秒只回复 101/527 token；
- identifier 长度 128/256/512 时，syntax 约为
  `237 / 1702 / 13378 ms`，semantic 仅 `0.43 / 0.75 / 1.21 ms`；
- syntax 增长接近 `O(n^3)`。

### 300 locals

| locals | syntax | semantic | 总耗时 |
|---:|---:|---:|---:|
| 100 | 0.878 s | 0.066 s | 0.962 s |
| 150 | 3.071 s | 0.143 s | 3.237 s |
| 200 | 7.926 s | 0.252 s | 8.206 s |
| 250 | 15.470 s | 0.377 s | 15.873 s |
| 300 | 28.054 s | 0.557 s | 28.652 s |

syntax 经验拟合约 `O(n^3.10)`，300 locals 中占 syntax+semantic 的 `98.05%`。
大量块内 statements 才会触发；单个长表达式和 150 个顶层函数均很快。

根因是当前 grammar 的高歧义增量状态，尤其是：

```gbnf
statements ::= statement (ws statements)?
```

与可空 `ws`、可选分号、声明/赋值/表达式的共同标识符前缀组合后，
XGrammar 的增量状态出现病态膨胀。

仅在 `/private/tmp` 的机制实验中把上述右递归改为：

```gbnf
statements ::= statement (ws statement)*
```

300 locals 的 syntax 从 `28.054 s` 降至 `0.191 s`，完整耗时从 `28.652 s`
降至 `0.752 s`。这只是根因证据，不是已证明的前缀语言等价变更。

本轮明确锁定 grammar 和 grammar hash，因此不实施这项改写。如果后续单独
立项，必须对旧/新 matcher 在官方 50、非规模 364、fuzz 及全部
byte/random/line/cl100k/whole 前缀做 shadow，再建立新的 grammar baseline
系列。禁止加入“长 identifier 直接放行”或“局部变量超过某数时切换路径”
等样例特化。

## 当前本地 Git 链

- `6382994` - lambda/IIFE 正确性修复；
- `c35afae` - postfix 链正确性修复；
- `68d780d` - 细粒度画像，正式构建关闭；
- `735a52e` - DeclarationSnapshot 候选；
- `75e9702` - 回退未升格候选；
- `3579e9b` - 候选结论与汇总证据；
- `353608c` - 7,650 次原始性能 trial 归档。

当前 accepted 生产逻辑为 `68d780d`。后续任何性能候选都必须在同轮重新测这个
control，不得直接与本报告的历史绝对数相减。
