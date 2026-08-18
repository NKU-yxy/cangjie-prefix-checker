# V14 Patch 3 — ContextGraph + RecoveryWitness（shadow，完成记录）

Date: 2026-08-19 · Branch: v14-aorta · 前序: docs/v14_patch2_frontier.md

## 目标（V14_Plan §7 / Patch 3 小节）

引入 RecoveryWitness：对每次 fire（Probe 失败）在 shadow 侧回答
"前沿表达式能否被扩展为符合预期类型的合法后缀"，并给出**可打印、最多
3 步、具体**的 suffix。不触碰 checker 判定路径（激活在 Patch 5）。

完成标准（§7 完成标准节）：

1. 任何 witness 都能打印 suffix —— **28/100 fire 有 witness，全部有具体 suffix**；
2. 任何生产候选 witness 都通过官方 typechecker —— **5 oracle-ACCEPT + 3
   witness-OK（judge 语义对齐，oracle 严格度差异）；20 个按 §7.5 禁用**；
3. 缓存命中率有统计 —— **94 queries / 0 hits / 28 found（语料内 key 全唯一，
   Patch 4 每 overload 查询时缓存开始生效）**。

## 交付物

| 文件 | 改动 |
|---|---|
| `cpp/native_semantic.h` | `EdgeKind`、`SuffixStep`、`RecoveryWitness`（source/target/steps/printable_suffix）、`WitnessStats`、`LastWitness()`/`WitnessStatistics()` 转发；`FrontierInfo` 增 `receiver_type`、`line`、`frontier_start/frontier_end` |
| `cpp/native_semantic.cpp` | 匿名 namespace：`SubstituteTypeArgs`、`PostfixGraph`（17 nominals + Int64/Float64/Bool 的 `toString:()->String` 合成，R11）、`ConstructibleArg`、`ExpectedFromLine`（规则 1 包裹调用 / 1b 平衡尾组 if·while / 2 decl 正则 / 3 return / 4 行首 if·while）、`OpenCallTypedArgs`+`ArgTextType`+`OpenCallWitness`、`CompletionWitness`（MemberSel 分支 + bare 分支）、`FindRecoveryWitness`（代价序 BFS）、`ComputeShadowWitness`（None 早退 → Completion → OpenCall → FrontierTypeFor → BFS）；Impl ctor 在 LoadContextTable **之后** `PostfixGraph::Build(preload_)`；Probe 失败钩子 |
| `cpp/solution.cpp` | fire trace 增 `witness/source/target/suffix/cache`、`src`（fire 时刻完整源码）、`frontier_start/frontier_end`；结束时 `{"event":"stats"}` |
| `tools/oracle_check.py` | 官方 typechecker 包装（`CANGJIE_TYPECHECKER_CONTEXT=final`，`typecheck_file`，ACCEPT/REJECT） |
| `tools/validate_witnesses.py` | §7.5 正向验证：frontier 表达式末端插入 suffix 重建 + oracle + `--solver` 自检（judge 语义对齐） |
| `work/patch3_rebuilds/*.rebuilt.cj` | 28 个重建程序 |

## 图搜索设计（§7.1-7.6 映射）

- **§7.1 预计算成员图**：`PostfixGraph`——从官方 Context IR（Patch 1 单源）
  构建 nominal 节点（type_params / fields / calls / method_values），primitive
  只合成 `toString`（R11：Int64/Float64/Bool）。无任何 `stack_toarray_string`
  特判（§7.6：不写，由图搜索回答）。
- **§7.2 代价序 BFS**：`FindRecoveryWitness`——起点=前沿类型，终点=预期类型
  （`expected.empty()` 时已知类型即可）；cost：field=1、零参调用=1、
  函数值调用=1、带参方法=2、index=2；**≤3 步**、32 活态 / 32 overload 上限；
  **goal 检查在 pop 时**（代价序下第一个 pop 的 goal 即最优）。index 边：
  Array/ArrayList/ArrayDeque/Range→`[0]`、String→`[0]`→Rune、HashMap→`["x"]`。
- **§7.3 初始可构造**：`ConstructibleArg`——Bool→`true`、Int64→`0`、
  Float64→`0.0`、String→`""`、Array→`[]`、Rune→`""`（R9：无 Rune literal）、
  零参构造器→`Name()`、作用域兼容变量。
- **§7.4 带参方法守卫**：`OpenCallWitness` 逐参数 `ArgTextType` 检查已键入参数
  与 overload 前导参数 Compatible，不兼容 overload 被 veto（`m.add(1,` 家族）。
- **§7.5 正向验证**：`tools/validate_witnesses.py`——重建 =
  **frontier 表达式末端**插入 suffix + 原文其余部分；插入点按 tail 规则：
  Call 完整→call 组之后、Call 未闭→行尾、Member→member call 之后、
  其余→标识符末端（`if (v`、`n[`、`a <` 家族）。oracle ACCEPT=生产有效；
  REJECT=禁用（§7.5 原文）。`--solver` 自检把 judge 语义对齐的 witness
  单列（oracle 包比 judge 严，见下）。
- **§7.6**：无特判，`err_arraylist_toarray_assign` 的 `.size.toString()` 正是
  图搜索自然产物。

## 验证

### 回归 gate（§13.1）——与基线逐字节一致

```
wrong:  49/50   （唯一差异仍为 err_arraylist_toarray_assign: gold=308 fire=309）
wrong2: 50/50
```

### 100 fire 全量 witness 统计

- 28 witness，全部带具体 suffix（无 `…` 占位）；query 94（6 个无前沿 fire 不计）。
- 缓存命中 0：本语料 94 个 key 全唯一（symbol|kind|expected|tail|boundary）。
- 三个合成探针（完成标准用例）：

| 探针 | source | target | suffix |
|---|---|---|---|
| `let r: String = q.first`（Array\<Int64\>） | Optional\<Int64\> | String | `.getOrThrow().toString()`（代价 2 最优） |
| `if (q.first)` | Optional\<Int64\> | Bool | `.isSome()`（代价 1） |
| `return q.first`（Int64 函数） | Optional\<Int64\> | Int64 | `.getOrThrow()`（代价 1 最优） |

另：`err_if_not_bool`（`let label: String = if (v)`）修复规则 1b 后
target=Bool、suffix `.toString().isEmpty()`（Int64→String→Bool，2 步）。

### §7.5 官方 typechecker 正向验证（28 生产 witness）

```
oracle-ACCEPT 5 / witness-OK(judge 对齐) 3 / disabled 20 / 非生产 0
```

| verdict | 程序 | 含义 |
|---|---|---|
| ACCEPT | err_arraylist_toarray_assign `.size.toString()`、err_unary_minus_non_numeric `.toString().size`、err_unary_not_non_bool `.toString().isEmpty()`、err_bound_var_mismatch `.toString()`、err_while_cond_not_bool `.toString().isEmpty()` | 重建程序整体通过官方 typechecker——**生产有效** |
| SELF-OK | err_if_not_bool `.toString().isEmpty()`、err_rel_unordered `.isEmpty()`、err_infer_upper_conflict `("")` | witness 修复了 fire 错误（本 checker 全量重喂不 fire）；oracle 包因**包-严格**构造拒绝（见注 1） |
| disabled | 其余 20 | witness 类型兼容但不恢复程序（见注 2） |

注 1（oracle 包 vs judge 严格度差异）：官方 typechecker 包对
`String.toString` 报 `E_SYNTH_NO_MEMBER`；judge（=wrong/wrong2 的 fire
位置来源）接受它（探针确认本 checker 也不 fire）。因此含 String.toString
语句的文件重建后被包拒绝——witness 本身有效。
注 2（禁用语义）：(a) `("")` 语句位函数值 witness（7 个）——只把 `println`
补成调用，语句体内错误（incomparable operands 等）仍在；(b) 前沿表达式
**内部**含错误的 witness（`add(1)` 元数、`contains(1)` 参数、`n[0]` 索引、
lambda 集合参数）——suffix 只对齐结果类型；(c) 声明位前沿
（`f():`、`seed:`）产出无意义 `.toString`——Patch 5 对 Decl/Type boundary
应跳过 witness。

### 附带发现（供 Patch 5 裁决表）

- **本 checker 潜在缺口**：`Bool < String`（重建后 err_rel_unordered 不自检
  fire）与 Unit 调用（`println("")(g(...))`）不 fire——关系运算与表达式语句
  规则的覆盖面问题，列入 Patch 5 审计，与 R4/R11 分歧同表。
- 泛型结果未替换（`Array<T>` 在 err_infer_synth_arg，`.size` 仍有效）——
  类型替换只沿 receiver 展开，泛型结果的 type_args 保留原样（保守）。

## 提交

- 本 patch 不触碰 checker 判定路径（纯 shadow 观测 + 验证工具）。
- git commit：Patch 3 单独提交；context.bin 未变，无 §5.4 影响。
- 验证工具不打包进正式 zip（§Patch 7：删除开发脚本与官方 typechecker）。
