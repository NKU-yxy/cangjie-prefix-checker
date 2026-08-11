# 增量源码事实候选验收报告

- 优化名称：从稳定 lexer event 维护 brace/结构位置和 partial 字符串/注释状态
- 目标瓶颈：消除 `Probe` 每 token brace 全源码扫描与顶层 `HasUnclosedString(source)` 扫描
- 对照提交：`fb16bfcfe9d38f4a45e3def6de5a14cf430a7908`
- 候选提交：`69656aa0d2e5dadc722224093681fdce1f8cb1c8`
- 是否改变语义规则：否；仅更换语法事实来源，字符串、反引号标识符、行注释和嵌套块注释内的 brace 被忽略
- 位置安全：所有状态位置为字节索引，未跨调用保存 `source_` 指针或 `string_view`
- 是否改变依赖或编译参数：否；shadow 扫描仅在 `CANGJIE_INCREMENTAL_SHADOW_BUILD=1` 测试构建中编译

## 画像

251 例画像（官方 50 + 项目 57 + 固定 fuzz 144）：

| 计数 | 对照 | 候选 |
|---|---:|---:|
| brace 全源码扫描字节 | 9,039,945 | 0 |
| 顶层未闭合字符串扫描字节 | 8,593,641 | 0 |
| context 重建次数 | 4,684 | 4,684 |
| model 重建次数 | 4,012 | 4,009 |

## 正确性与 shadow

- 默认二进制不包含 profile/shadow 诊断代码
- 官方 50 例精确首错：50/50；所有正式 trial 零失败
- 单元测试：36/36
- native fragment differential：71/71 语义例 × 4 种分片
- 新增通用语料覆盖：字符串 brace、行注释 brace、CRLF 注释、嵌套块注释、转义引号后 brace
- native context differential：7/7
- 固定 seed hidden semantic fuzz：144 例、5 种分片、零失败
- 官方语义语料：45/45；项目语料：57/57
- shadow：上述分片、fuzz 和官方/项目语料每个前缀的增量状态与忽略字符串/注释的参考扫描完全一致
- ASan/UBSan + shadow：PASS，无索引、生命周期或未定义行为报告
- ARM64 可移植性检查：PASS
- 公开样例特化检查：PASS；事件转移只依赖通用 token kind/text 与字节位置

## A1 → B → A2

三阶段在同一个锁定 Linux AArch64 官方镜像容器中运行，每阶段每例 1 次预热 + 9 次实测。

| 指标 | A1 | B | A2 | 逐例 A1/A2 平均对照 |
|---|---:|---:|---:|---:|
| SUM (ms) | 1939.066 | 1953.847 | 1957.228 | 1948.147 |
| MEDIAN (ms) | 39.934 | 40.040 | 40.478 | 40.202 |
| P95 (ms) | 50.952 | 51.906 | 51.884 | 51.418 |
| MAX (ms) | 56.019 | 56.929 | 57.950 | 56.985 |

- A1/A2 SUM 漂移：0.937%
- B 相对正式对照 SUM 变化：**+0.293%**（回退）
- WIN / LOSS：0 / 0
- 最严重单例回退：`err_interface_sig_mismatch`，+0.437 ms / +3.512%，未越过 1 ms 噪声阈值
- 同时超过 2 ms 和 8% 的单例：0

## 最终判定

`NO PROVEN GAIN`。目标扫描已完全消除，但当前语料规模下这些字节扫描不是足够大的 CPU 瓶颈，整体 SUM 未改善。按条约不宣称性能提升，不将候选叠加到后续改动。

原始数据为同名 `A1` / `B` / `A2` 的 JSON、CSV 和 Markdown，以及 `profile_20260812_incremental_lexical_facts_candidate.json`。
