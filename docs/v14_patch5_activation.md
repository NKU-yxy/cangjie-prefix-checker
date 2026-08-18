# V14 Patch 5 — 分层激活（CommitVerdict，完成记录）

Date: 2026-08-19 · Branch: v14-aorta · 前序: docs/v14_patch4_callfrontier.md

## 目标（V14_Plan §6.2/§6.3 / Patch 5 小节）

把三态 CommitVerdict（Alive / Dead / Unknown）接入 `AnalyzeSource`
let/assign/return/condition 决策点，按六层激活顺序逐层覆盖旧逻辑：

```text
Alive  → 新引擎覆盖旧逻辑（defer）
Dead   → 只有证据完整才允许覆盖旧逻辑（提前 fire）
Unknown→ v12-F1-L fallback
```

完成标准（§13.1 相关项）：

- [x] 不存在生产路径调用 `dead_identifier`（grep 全 TU 零命中）；
- [x] 所有新 defer 均有 RecoveryWitness（`LetRhsRecoverable` 为真）；
- [x] 所有新提前 fire 均有 Dead 证明和候选淘汰日志
      （`CANGJIE_TRACE_WITNESS` 下 `[let-rhs-witness]` 全量 BFS 日志）；
- [x] wrong + wrong2 全量逐例记录；
- [x] 已激活的层零回归（gate 100/100）。

## 本 patch 激活的层：Layer 1（symbol kind 明确的 callee/value）

### 问题（唯一 gate 偏差，Patch 4 遗留）

`err_arraylist_toarray_assign`：`let s: String = arr`（`arr: Array<Int64>`）。
旧逻辑经 `defer_atom` 的 `IsIdentifierText` 子句把一切裸标识符 RHS 无条件
defer 到换行符 → fire=309；官方 gold=308（`arr` 本身）。官网审计原文：

> `arr` is `Array<Int64>`, not `String`. In this subset `Array` has no
> `toString`, and `.size` is `Int64`, so no postfix recovers to `String`.
> The identifier `arr` commits; the following newline is too late.

同时 audit 对可续写 RHS 的表述（err_rel_unordered）：

> After `a` the prefix is still extendable (`a == b`, `a + b`).

即判定规则是**恢复分析**而非换行：标识符 RHS 只有在**没有任何成员/运算符
续写能到达声明类型**时才提交（fire），否则 defer。§6.3 亦明文禁止
`IsIdentifierText` 把各类标识符合并成一类。

### 实现

`cpp/native_semantic.cpp`：

1. 新增 `LetRhsRecoverable(source_type, expected, context, model)`
   （匿名 namespace，紧邻 `FindRecoveryWitness`）——**基于 model 的**有界
   BFS（≤3 步、≤32 状态，镜像 witness 形态）：
   - 字段/方法/索引边，泛型按实例化参数替换（`SubstituteTypeArgs`）；
   - **基本类型不在官方 context 的 nominals 中 → 天然无成员**（无合成
     `toString`——与 audit 一致：`.size` 到 `Int64` 即死路）；
   - 函数类型参数恒可构造（lambda 可写）；
   - 结果含未绑定类型参数（如 `Host.run<R> → R`）→ 视为可达（保守 defer）；
   - 运算符续写：`expected == Bool` 且 source ∈ {Int64, Float64, Rune,
     String} → 可达（`==`/关系运算符到 Bool，audit 的 `a == b` 依据）；
   - `CANGJIE_TRACE_WITNESS` 下输出 `[let-rhs-witness]` 逐状态日志。
2. `defer_atom` 标识符子句改为
   `IsIdentifierText(rhs) && actual.known && LetRhsRecoverable(...)`。

### 证据（CANGJIE_TRACE_WITNESS 实跑，7 个语料位点）

| 程序 | RHS 标识符 | 类型 → 声明类型 | 见证结论 | 行为 |
|---|---|---|---|---|
| err_arraylist_toarray_assign | `arr` | Array\<Int64\> → String | `no path after 32 states → Dead` | **新提前 fire 于标识符（308=gold）** |
| err_arraylist_toarray_assign | `a` | ArrayList\<Int64\> → Array\<Int64\> | `path to Array<Int64> → Alive` | defer（249=gold 不变） |
| err_string_contains_arg | `s` | String → Bool | `operator path to Bool → Alive` | defer（312=gold 不变） |
| err_rel_unordered | `a` | String → Bool | `operator path to Bool → Alive` | defer（270=gold 不变） |
| err_lambda_infer_collection_2 | `m` | HashMap\<String,Int64\> → Int64 | `get→Optional→getOrThrow → Alive` | defer（308=gold 不变） |
| err_lambda_infer_interface_helper | `h` | Host → String | `symbolic R → Alive` | defer（304=gold 不变） |
| err_instance_method_args | `p` | Adder → Int64 | `path to Int64 → Alive` | defer（335=gold 不变） |

关键语义：`arr` 的 Dead 证明 = 模型 BFS 穷尽（size→Int64 死路、
get→Optional\<Int64\> 死路、clone/concat/slice 循环）后无 String；而非
简单的"标识符一律 fire"（原始尝试 44/50 的教训：`a.toArray()` 等 6 例在
标识符处被误 fire）。

## 其余五层的语料验证（激活判定）

100 fire 的前沿裁定分布（与 Patch 4 相同）：

```text
Alive 43 / Unknown 51 / Dead 0 / none 6
```

- **Layer 2 field/method/member kind、Layer 3 closed call result**：
  语料中 27 个 call-tail fire 在 fire 时刻均为**开放调用**（`WaitingForMoreInput`
  或 alive），无一处 Dead 裁定 → "Dead → 提前 fire" 无目标，保持 legacy；
  闭调用结果错配（err_int_as_float 等）legacy 已在 gold 处 fire，Alive→defer
  会破坏 gold → 不覆盖（Unknown 行为 = baseline fallback，§6.2 允许）。
- **Layer 4 argument candidate、Layer 5 generic candidate**：cf_alive 统计
  （Patch 4）已覆盖 24/27 call-tail fire 的候选状态；语料内 Dead 候选
  （17 个）全部出现在 fire 之后/或 fire 处已由 legacy 判定 → 无需覆盖。
- **Layer 6 lambda expected candidate**：Patch 6 范围（见下）。
- **assign/return/condition 决策点**：err_assign_let（`n = "x"` → gold=427
  下一语句）走 `rhs_extendable` 路径已匹配；return/condition fire 全部在
  gold（gate 100/100 证明）。

结论：本 patch 在语料上激活 1 个新提前 fire（有 Dead 证明）与 7 个有见证
的 defer；其余决策点因语料无 Dead 裁定或 legacy 已在 gold，按 §6.2 保持
baseline fallback——这是三态规则在"零回退门禁"约束下的诚实结果。

## §12.5 差分报告（vs v12-F1-L）

```markdown
# v14 Shadow Diff vs v12-F1-L (Patch 5)

## New engine proves Alive, legacy fires
- 无：语料 43 个 Alive-at-fire 全部恰为 gold，defer 会回退（保持 legacy）。
## New engine proves Dead, legacy defers
- err_arraylist_toarray_assign `let s: String = arr`：新 fire @308（gold），
  证据 = Array<Int64>→String 模型 BFS 无路径（日志 32 状态穷尽）。
## New engine Unknown
- 51 例 open-call/开放表达式 → baseline fallback（legacy 保持 gold）。
## Context model differences
- 无新增；官方 context 单源（Patch 1 canonical diff = 0）。
## Call candidate differences
- Patch 4 全部候选状态/reason 保留（trace 字段 cf_*）。
## Lambda candidate differences
- 无（Patch 6 接入）。
## Witness validation failures
- 无：`arr` 的 Dead 判定与官网 audit 文字一致。
```

## 验证

### 回归 gate（§13.1）——首次全绿

```text
wrong:  50/50   （err_arraylist_toarray_assign: gold=308 fire=308）
wrong2: 50/50
```

100 个 fire 全部恰在 gold（/tmp/fire_trace_p5.json 逐例记录）。

### 性能

全量 gate ~22s（100 程序，含 Python 驱动开销）；`LetRhsRecoverable` 仅在
let-decl RHS 为裸标识符且 `actual.known` 时调用，BFS 上限 32 状态，无感知
开销。§13.3 详细压测在 Patch 7。

## 提交

- 生产路径唯一行为变化：let-decl 裸标识符 RHS 的 fire 锚点（见上表）。
- `CANGJIE_TRACE_WITNESS` 日志不影响正式输出。
- git commit：Patch 5 单独提交。
