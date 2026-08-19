# V15-PROOF-FRONTIER 进度（单文件持续更新）

起始：2026-08-19 · 依据：V15_Plan.md · 分支：v15-proof-frontier

## 总纲（V15_Plan 一句话）

> 下一版只允许「有合法续写证明时推迟报错」和「在硬提交点全部候选被完整淘汰时提前报错」；
> 除此之外全部回退到 63 分基线（v12-F1-L）。

- 开放表达式（裸标识符/成员前缀/未闭合调用索引 lambda/二元中间态）：搜索到合法续写 → Alive；
  搜索不到 → **Unknown**（禁止 Dead）。
- 硬提交边界（`)` `]` lambda `}` 函数/块 `}` 已提交参数分隔 明确提交类型运算符 下一条语句首 token）：
  所有候选确实被淘汰 → 才允许 Dead。
- Proof-Carrying Override：baseline = v12-F1-L 决策；Alive+ValidSuffix → Continuable；
  Dead+OfficialAudit/ClosedWorldExhaustive → Error；其余回退 baseline。
- 不做的：开放表达式 Dead、LetRhsRecoverable 无路径即 Dead、不完整 BFS 负证明、
  无 suffix 的 recovery override、canonical JSON diff 冒充行为验证、shadow 数量冒充输出差异。

---

## Patch 0：恢复 63 分生产行为

（进度：执行中）

- 分支：`v15-proof-frontier`，自 `v12-F1-L` (09abd7c) 分出
- cherry-pick v14 infra 提交（不含 Patch 5 activation 的生产 Dead）：
  `a49159b` trace → `6c9ac70` context IR → `528727a` frontier shadow →
  `185c800` witness shadow → `ab78d50` call_frontier shadow
- 完成标准：与 v12-F1-L 在所有现有测试逐 token 一致（wrong 49/50 + wrong2 50/50）
