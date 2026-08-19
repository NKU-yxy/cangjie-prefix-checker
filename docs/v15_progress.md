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

## Patch 0：恢复 63 分生产行为 — ✅ 完成（2026-08-19）

- 分支：`v15-proof-frontier`，自 `v14-aorta` HEAD 分出后 reset 到 `v12-F1-L` (09abd7c)
- cherry-pick v14 infra 提交（不含 Patch 5 activation 的生产 Dead）：
  `35e9623` trace → `0cc4dee` context IR → `b8f25ee` frontier shadow →
  `b946958` witness shadow → `b6f25ed` call_frontier shadow
- 完成标准达成：与 v12-F1-L 在所有现有测试逐 token 一致：
  - wrong **49/50**（唯一差异 err_arraylist_toarray_assign：gold fire=308 vs 实际 309，
    与 v12-F1-L 完全相同的刻意偏离）
  - wrong2 **50/50**
- 提交：`35e9623`（Patch 0）→ `b6f25ed`（infra 收尾）

---

## Patch 1：Decision Ledger（决策台账） — ✅ 完成（2026-08-19）

- 新增 `cpp/continuation.h/.cpp`：`ContinuationState{Alive,Dead,Unknown}`、
  `ProofKind{None,ValidSuffix,OfficialAudit,ClosedWorldExhaustive}`、
  `ContinuationProof{state,proof,rule_id,printable_suffix,transition_set_complete,eliminated_candidates}`、
  `DecisionContext{site,prefix,baseline_reject,symbol_kind,tail_kind,boundary,expected_type,actual_type,candidate_count,call_closed}`、
  `DecisionLedgerEntry{decision_id,site,prefix,baseline,frontier,proof_kind,symbol_kind,tail_kind,boundary,candidate_count,expected_type,actual_type,overridden}`
- 单点包装（V15 架构决策，不逐 site 埋点）：`Probe()` 在 AnalyzeSource 结果上统一包
  `DecideWithProof()`；`MakeDecisionContext()` 从错误消息反向推导 decision site
  （initializer → assignment → condition → **lambda** → return → iterable → argument/parameter →
  candidate/overload → member → callable → type → generic），`ComputeProof()` 暂为
  `{Unknown, None, "v15-stub"}` 桩——只记录不改判定
- Override 逻辑（§五）：`Alive+ValidSuffix → Continuable`；`Dead+OfficialAudit/ClosedWorldExhaustive → Error`；
  其余回退 baseline——当前桩下全部回退 baseline，生产行为零变化
- 台账 trace：`CANGJIE_TRACE_LEDGER=1` 输出 JSONL（decision_id/site/baseline/frontier/
  proof_kind/symbol_kind/tail/boundary/candidate_count/expected/actual/overridden/prefix）
- 验证：
  - gate 复验：wrong **49/50**（仅 toarray_assign 刻意偏离）+ wrong2 **50/50**，与 Patch 0 逐字节一致
  - `err_lambda_tick_callback` 台账冒烟：`return_1` 条目 `{site: return, baseline: dead,
    frontier: unknown, proof_kind: none}` 正确记录
  - `SiteFromMessage` 顺序 bug 修复：lambda 检查移到 return 之前（tick_callback 的 lambda 类型
    不匹配错误此前被误分类为 site=return）
- 提交：`64e1134`
