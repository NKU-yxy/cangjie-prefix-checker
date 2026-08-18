# V14 Patch 4 — CallFrontier（shadow，完成记录）

Date: 2026-08-19 · Branch: v14-aorta · 前序: docs/v14_patch3_witness.md

## 目标（V14_Plan §8 / Patch 4 小节）

对每次 fire 的调用位前沿（callee + '('）做 **per-overload** 的 shadow 分类：
每个 overload 独立状态（Alive / WaitingForMoreInput / Dead），已键入参数
逐位兼容检查，`)` 做最终 arity/default 检查；任何淘汰都携带具体 reason。
不触碰 checker 判定路径（激活在 Patch 5）。

完成标准（§8 完成标准节）：

1. 所有调用可打印 alive candidate 数量 —— **27 个 call-tail fire 中 24 个
   解析出 overload 并打印 `cf_alive/cf_total`；3 个不可解析（关键字 `while`、
   域遮蔽名 `f`、未入作用域名 `ratio`），正确跳过**；
2. 所有淘汰有 reason —— **17 个 Dead candidate，16 个 arg-mismatch +
   1 个 arity-short-at-close，0 个无原因**；
3. 暂不影响输出 —— **gate 与基线逐字节一致**。

## 交付物

| 文件 | 改动 |
|---|---|
| `cpp/call_frontier.h`（新） | `CandidateState`（Alive/WaitingForMoreInput/Dead）、`EliminationReason`（None/ArityExceeded/ArgTypeMismatch/ArityShortAtClose/ExpectedReturnOnly）、`CallCandidate`、`CallFrontierResult`（callee/resolved/overload_count/alive_count/call_closed/candidates/reasons）、`OverloadView`（param_types 已按 receiver 替换 / result_type / type_params / required）、`CallFrontierClassifier::Classify`（compat 谓词由调用方注入，TU 自包含） |
| `cpp/call_frontier.cpp`（新） | `HasUnboundTypeParam`（symbolic 参数永不因 mismatch 淘汰）、`Classify` 实现（§8.2 规则 1-6） |
| `cpp/native_semantic.cpp` | `ComputeCallFrontier`（匿名 namespace，接 `ArgTextType`/`OpenCallTypedArgs`/`ExpectedFromLine`/`CallStillOpen`/`Compatible`/`SubstituteTypeArgs`/`FunctionTypeParts`）：Method/StaticMember→nominal.methods（回退 static_methods）、Function→functions、Type→constructors、Local/Global→函数值类型分解；Impl 增 `last_call_frontier_` + accessor；Probe 失败钩子 |
| `cpp/native_semantic.h` | `#include "call_frontier.h"`；`LastCallFrontier()` 引擎 + checker 转发 |
| `cpp/solution.cpp` | fire trace 增 `cf_resolved/cf_total/cf_alive/cf_closed/cf_candidates`（per-candidate 状态 + reason 摘要） |
| `build.sh` | TU 列表增 `cpp/call_frontier.cpp` |

## §8.2 规则实现对照

1. **per-overload 独立状态** —— 每个 overload 一个 `CallCandidate`，独立
   `next_param/accepts_more/can_close_now/state/reason`。
2. **无合法后缀可兼容才淘汰** —— 已键入参数与**非 symbolic** 参数不兼容才
   Dead(ArgTypeMismatch)；`ArgTextType` 无法判型的参数（lambda 体、数组、
   未知名）`""` → **永不 veto**（err_lambda_* 家族 7 个 fire 全部保守 alive）。
3. **逗号提交参数、元数不提前裁决** —— `matched` 只累计已出现参数；开放的
   调用中参数不足是 `WaitingForMoreInput`，不是 Dead。
4. **`)` 做最终 arity/default 检查** —— `call_closed && matched < required`
   → Dead(ArityShortAtClose)（err_arity `add(1)` vs `add(Int64, Int64)` 唯一一例）。
5. **expected-return 只记录不淘汰** —— `ExpectedReturnOnly` 仅出现在
   reason 文本，永不改 state（激活时由 witness 机制回答可达性）。
6. **unbound 类型变量保持 symbolic** —— `HasUnboundTypeParam` 覆盖
   `T`/`Array<T>` 整词匹配；infer 家族（pair/echo/inner/wrap/takeInt 的
   `T` 参数）不被 arg-mismatch 淘汰。
7. **receiver/args/expected 联合约束** —— receiver 类型（含泛型实例）参与
   方法 overload 的参数替换；expected 参与 ExpectedReturnOnly 记录。
8. **方法值 vs 调用是不同状态** —— Local/Global 的函数值调用按
   `FunctionTypeParts` 分解出单 overload；与方法调用独立。

## 实现要点（含一次关键修正）

- **receiver 已是 TypeHead**：Patch 2 的 `frontier.receiver` 是接收者**类型
  头**（如 `Adder`/`ArrayList`），`frontier.receiver_type` 才是完整实例化
  （如 `HashSet<Int64>`）。初版 shim 误把它当标识符二次 `ResolveMemberKind`，
  导致 16 个实例方法调用（add/get/contains）全部解析失败
  `cf_total=0`——改为直接 `model.nominals.find(frontier.receiver)` +
  `TypeArgs(frontier.receiver_type)` 替换。
- **静态访问**（`Foo.make(`、`Foo.eval(`，kind=StaticMember）：回退到
  `static_methods`（无则 `methods`），与 D1 的 Unknown 裁定不冲突（shadow
  只观察）。**构造器调用**（`Array(`，kind=Type）走 `constructors`。
- **元数与类型分离**：初版把「类型未知的参数」在 `matched` 计数前
  `continue`，导致 `run({…})` 这类 1 参但类型不可判的调用被误判
  ArityShortAtClose——修正为**先计 matched（参数存在即算），再判兼容**。

## 验证

### 回归 gate（§13.1）——与基线逐字节一致

```
wrong:  49/50   （唯一差异仍为 err_arraylist_toarray_assign: gold=308 fire=309）
wrong2: 50/50
```

### 100 fire 分类统计

- call-tail fire 27（26%），解析 24，不可解析 3。
- 候选状态：dead 17 / alive 12 / waiting 2；淘汰原因：arg-mismatch 16 /
  arity-short-at-close 1（0 个无原因）。
- 无解析的 3 个：`while`（关键字）、`f`（域遮蔽函数名，变量类型非函数值）、
  `ratio`（fire 时刻不在作用域）——均不应解析。

### §8.4 回归家族覆盖

| 家族 | 程序 | 分类结果 |
|---|---|---|
| 元数 | err_arity | `add(Int64, Int64)` DEAD arity-short-at-close |
| 方法参数 | err_instance_method_args / err_arraylist_add_type / err_static_method_args / err_string_contains_arg / err_array_fill_type | 各自唯一/全部 overload DEAD arg-mismatch（`"x"`→Int64 等） |
| HashMap | err_hashmap_key_type | `add(String, Int64)` + `add(Array<…>)` 双 DEAD（`add(1, 2)`） |
| infer 家族 | err_infer_constraint | `takeInt(Int64)` DEAD arg-mismatch |
| | err_infer_lower_conflict / synth_arg / check_arg / nested_conflict | `T`/`U` symbolic → alive（规则 6） |
| infer 歧义 | err_lambda_infer_ambiguous_1/2 | waiting(next=2/3)，开放调用 |
| lambda 集合 | err_lambda_infer_collection_1/2 | `s.add(1)`/`d.get(1)` 对 String 参数 DEAD arg-mismatch |
| lambda HOF | err_lambda_* 其余 7 个 | `()->R` 参数 body 不可判 → alive（规则 2 保守） |
| 构造器 | err_ctor_call_mismatch | 1 DEAD arg-mismatch / 2 alive（`Array(Int64,T)` 与另两个 ctor） |

所有淘汰均有 reason、无盲目消除；与 F1-L 检查语义无矛盾（Patch 5 激活时
`Dead` 可作为新 fire 的 shadow 证据）。

## 提交

- 本 patch 不触碰 checker 判定路径（纯 shadow 观测 + trace 字段）。
- git commit：Patch 4 单独提交；context.bin 未变。
- `cf_candidates` 字段随 CANGJIE_TRACE_FIRE 条件打印，正式 zip 无影响。
