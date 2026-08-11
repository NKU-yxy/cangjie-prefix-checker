# 通用 LTO 候选验收报告

- 优化名称：在编译和链接阶段启用通用 `-flto`
- 目标瓶颈：跨 `solution.cpp` / `native_semantic.cpp` 翻译单元优化
- 对照提交：`7efeff4693024f2f9e12f78679b125a7c4f126ad`
- 候选提交：`c43420987dd0e6ba2dd94c936081c847ac2a6b0c`
- 是否改变语义：否
- 是否改变依赖或编译参数：是；仅新增通用 `-flto`，无 `-march=native`、`-mcpu`或 Apple 参数

## 正确性与可移植性

- 官方镜像产物：ELF64 / AArch64
- 官方 50 例精确首错：50/50；所有正式 trial 零失败
- 单元测试：34/34
- native fragment differential：66/66 语义例 × 4 种分片
- native context differential：7/7
- 固定 seed hidden semantic fuzz：144 例、5 种分片、零失败
- 官方语义语料：45/45；项目语料：57/57
- ARM64 可移植性检查：PASS
- 公开样例特化检查：PASS

## A1 → B → A2

三阶段在同一个锁定 Linux AArch64 官方镜像容器中运行，每阶段每例 1 次预热 + 9 次实测。

| 指标 | A1 | B | A2 | 逐例 A1/A2 平均对照 |
|---|---:|---:|---:|---:|
| SUM (ms) | 1931.781 | 1987.470 | 1960.781 | 1946.281 |
| MEDIAN (ms) | 39.937 | 40.912 | 40.146 | 40.041 |
| P95 (ms) | 51.113 | 52.732 | 51.978 | 51.546 |
| MAX (ms) | 56.743 | 58.137 | 56.964 | 56.854 |

- A1/A2 SUM 漂移：1.501%
- B 相对正式对照 SUM 变化：**+2.116%**（回退）
- WIN / LOSS：0 / 5
- 同时超过 2 ms 和 8% 的单例：0
- 最严重百分比回退：`err_return_type_mismatch`，+0.476 ms / +4.159%
- 最大绝对回退：`err_array_fill_type`，+1.502 ms / +3.378%

## 最终判定

`REJECTED`。SUM 明确回退 2.116%，MEDIAN 和 P95 也回退，且有 5 个单例越过噪声阈值。不进入 21 次复测，不将 `-flto` 保留在后续对照中。

原始数据为同名 `A1` / `B` / `A2` 的 JSON、CSV 和 Markdown 文件。
