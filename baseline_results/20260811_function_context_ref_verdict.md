# FunctionContext 去复制候选验收报告

- 优化名称：`AnalyzeSource` 只读引用缓存的 `FunctionContext`，当前函数体单独传递 `string_view`
- 目标瓶颈：消除每次 probe 对变量表、不可变集合和函数体的深拷贝
- 对照提交：`68fa783e2af27be29ffe68aa4526d0255d33f2d7`
- 候选提交：`f000cedc693558c1412136aed51f4e20d222006f`
- 是否改变语义：否；lambda 推导中的局部上下文复制未改变
- 是否改变依赖或编译参数：否

## 画像与正确性

- 251 例全语料画像中 `context_copy_payload_bytes`：2,694,864 → 0
- 其他语义检查族调用数与对照一致
- 官方 50 例精确首错：50/50；所有正式 trial 零失败
- 单元测试：34/34
- native fragment differential：66/66 语义例 × 4 种分片
- native context differential：7/7
- 固定 seed hidden semantic fuzz：144 例、5 种分片、零失败
- 官方语义语料：45/45；项目语料：57/57
- ASan/UBSan：PASS；消毒器下重跑 66×4 分片、144 fuzz、50 官方精确首错、45 官方语义与 57 项目语料，无报告

## A1 → B → A2

三阶段在同一个锁定 Linux AArch64 官方镜像容器中运行，每阶段每例 1 次预热 + 9 次实测。

| 指标 | A1 | B | A2 | 逐例 A1/A2 平均对照 |
|---|---:|---:|---:|---:|
| SUM (ms) | 1927.026 | 1944.413 | 1947.970 | 1937.498 |
| MEDIAN (ms) | 39.908 | 39.988 | 39.991 | 39.950 |
| P95 (ms) | 50.910 | 51.014 | 50.998 | 50.954 |
| MAX (ms) | 56.868 | 56.939 | 56.938 | 56.903 |

- A1/A2 SUM 漂移：1.087%
- B 相对正式对照 SUM 变化：**+0.357%**（回退）
- WIN / LOSS：0 / 0
- 最严重单例回退：`err_interface_sig_mismatch`，+0.832 ms / +6.916%，未越过 1 ms 噪声阈值
- 同时超过 2 ms 和 8% 的单例：0
- ARM64 可移植性检查：PASS
- 公开样例特化检查：PASS；改动仅涉及通用对象所有权和读取方式

## 最终判定

`NO PROVEN GAIN`。虽然画像证明已消除目标复制，但 SUM 未改善且变化小于 2% 阈值。按条约不宣称优化有效，不将候选叠加到后续改动。

原始数据为同名 `A1` / `B` / `A2` 的 JSON、CSV 和 Markdown，以及 `profile_20260811_function_context_ref_candidate.json`。
