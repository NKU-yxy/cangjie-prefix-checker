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

---

## Patch 2：Behavioral Context Extractor — ✅ 提取器完成（2026-08-19，diff=0 留待 Patch 4-7）

### 工具：`tools/behavioral_context_audit.py`

- 对官方 FINAL context 全部 **106 个成员**（11 nominal 的字段/静态字段/方法/静态方法 + 6 interface 方法 + 8 全局函数，overload 逐签名展开）生成 §6.1 四类探针：
  - A `let value: R = x.member`（值读）；B `let value: R = x.member(<args>)`（调用）；
    C `let f: (P...) -> R = x.member`（函数引用）；D 返回值后缀（方法先调用再 postfix）
- 双裁决：官方 typechecker（`CANGJIE_TYPECHECKER_CONTEXT=final`）+ v15 solution 二进制（cl100k token 流，记录 fire 索引）
- 分类表（§6.1）：A ok+B not-callable+C fail→field；A fail+B ok+C ok→method；A ok+B ok→callable_field；全 fail→error
- 产物：`results/official_behavioral_context.json`（106 成员 × 探针裁决 + official_behavior_kind）、
  `results/runtime_behavioral_context.json`（运行时模型 kind + 探针 fire）、
  `results/behavioral_context_diff.md`（差异全表 + receiver-shape 维度 + 门禁判定）

### 校准发现（探针构造本身，非运行时偏差）

- **官方 checker 的 `_CONTEXT_PATH` monkeypatch 无效** —— 必须用 `CANGJIE_TYPECHECKER_CONTEXT=final` 环境变量（此前 probe_v10 跑的是 preliminary context）
- **探针程序不能带 println 后缀**：Optional/函数类型无 toString 时错误会转移到 println 调用点
- **D 探针方法必须先调用**：`recv.hashCode.toString()` 链在函数值上恒报 no member（第一版 43 个 mismatch 中 12 个为此类污染，修复后消除）
- **运行时无法解析非标识符接收者**：`[1,2,3].size` 的 receiver 抓到 "3" → 成员解析失败（v14 已知限制，receiver-shape 维度单独记录）
- Optional 无构造函数，唯一合法接收者是 `.first` 读取 → 两段绑定（`let a: Array<Int64> = Array<Int64>(1, 0)` + `let recv: Optional<Int64> = a.first`）

### 发现清单（门禁：raw JSON 与官方行为不一致项全部列出 — 23 处）

| owner | member | raw JSON | 官方行为 | 说明 |
|---|---|---|---|---|
| Array | first/last | method | **field** | 自动应用属性（F1 已在 project context 中实现 ✓） |
| HashMap/HashSet | size/capacity | field+method | **field** | 同名双注册时官方字段优先 |
| Collection | size | method | **field** | interface 方法按属性处理 |
| String | empty | static_field | **callable_field** | `String.empty` 值读与 `String.empty()` 调用官方都接受 |
| String | fromUtf8 | static_method | method | 参数检查宽松（`Array<Rune>` 位接受 `[1]`） |
| ArrayList | of | static_method | **error** | 官方 checker 未实现 `ArrayList.of`（no member） |
| 全局 | println/print/eprintln/eprint/abs/clamp | function | method | 与直觉一致 |
| 全局 | min/max | function | error | 泛型 `T` 官方不可推断 → 所有调用/引用全拒 |

### 运行时 vs 官方：21 处 mismatch（diff=0 门禁未达，修复归属见下）

| 族 | 成员 | 官方 | 运行时 | 计数 | 修复归属 |
|---|---|---|---|---|---|
| A 字段+方法同名 | HashMap/HashSet size/capacity | `m.size()` REJECT not-callable（字段优先） | ACCEPT（调用路径走方法） | 14 | Patch 6 Core Semantic |
| B 方法引用 | ArrayList.add / HashMap.add / HashMap.remove / HashSet.add / HashSet.remove | `let f: (T) -> Unit = recv.add` ACCEPT | 语句结束 fire（无函数类型注解支持） | 5 | Patch 7 Lambda/Infer |
| C 泛型全局 | min/max | `min(1, 2, [3])` REJECT（T 不可推断） | ACCEPT（过度泛型推断） | 2 | Patch 6/7 |

- receiver-shape 维度：11 个探针中 2 个 GAP（数组字面量 receiver、成员链 receiver），其余调用表达式 receiver 运行时均能解析
- **结论**：diff=0 是 §十二放行标准（"Behavioral Context 非 F1 偏差：发现则必须全部修复"），由 Patch 4-7 逐族修复后回验；Patch 2 阶段不改判定路径
- gate 复验：wrong 49/50（仅 toarray_assign 刻意偏离）+ wrong2 50/50，与 Patch 0/1 逐字节一致
- 提交：`c2f8dcd`
