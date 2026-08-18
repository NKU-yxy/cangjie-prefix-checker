# V14 Patch 2 — SymbolKind / TailKind / BoundaryKind 前沿（shadow，完成记录）

Date: 2026-08-19 · Branch: v14-aorta · 前序: docs/v14_patch1_context_ir.md

## 目标（V14_Plan §5.2 / Patch 2 小节）

引入 SymbolKind / TailKind / BoundaryKind 三种分类，对**每次 fire**（Probe 失败）
在 shadow 侧记录前沿状态；不改变任何判定输出。完成标准：

1. 所有标识符 fire 都能打印 symbol_kind / tail / boundary；
2. 没有 UnknownSymbol 被直接判 Dead；
3. 确认 abs、helper、deque、obj.get、obj.get() 不再被混为同类。

## 交付物

| 文件 | 改动 |
|---|---|
| `cpp/native_semantic.h` | `enum class SymbolKind/TailKind/BoundaryKind/FrontierVerdict`、`FrontierInfo`、4 个名称函数声明、`IncrementalSemanticEngine::LastFrontier()`、`NativeSemanticChecker::LastFrontier()` 转发 |
| `cpp/native_semantic.cpp` | 4 个名称函数（文件尾部、外部链接）；匿名 namespace 内 shadow 分类器：`MaskQuotedAndComments`、`FindFrontierIdentifier`（含 `<T...>` 型参外走）、`SkipTypeArgumentList`、`ClassifyTail`、`ClassifyBoundary`、`ResolveBareSymbol`、`ResolveMemberKind`、`MemberVerdict`、`ClassifyFrontier`；Probe 失败时记录 `last_frontier_` |
| `cpp/solution.cpp` | fire trace 扩展：`symbol/symbol_kind/tail/boundary/receiver/shadow_verdict/line` 字段（`line` = fire 时刻源码最后一行，供后续 patch 观测） |

## 分类器语义

- **前沿** = fire 时刻源码最后一行的最后一个标识符（掩掉字符串/注释后）；
  若它是型参（`ArrayDeque<Int64>`），外走取外层名字，tail 从匹配 `>` 之后算。
- **行选择**：fire 落在语句终结符（`}` 行 / 空行）时向上走到语句行 ——
  `abs wrong ret` 在 `}` 处 fire，前沿 = `abs`。
- **TailKind**：Call（后随 `(`，含型参之后）、Member（后随 `.`）、Type（`:`,`<`,`,` 后、
  类型位置）、Value。
- **BoundaryKind**：Statement / AssignRhs / Return / Condition / LoopHead / CallArg /
  MemberSel / Decl。
- **SymbolKind 判定**（成员选择）：receiver 按 局部→全局→类型名 解析，再查
  nominal：field > method > static（R2 字段优先）；类型名作 receiver → StaticMember
  （D1：参考 checker 无静态访问，shadow 判 Unknown）。
- **Verdict 真值表**（R1-R3 + D1，仅 shadow）：

  | SymbolKind | Tail | Verdict |
  |---|---|---|
  | Method | Call | Alive |
  | Method | Value（零参 overload 存在） | Alive（函数引用，R3） |
  | Method | Value（全 overload 有参） | Dead（完整证据） |
  | Field | Call | Dead（R2 字段不可调用） |
  | Field | Value | Alive |
  | StaticMember | 任意 | Unknown（D1） |
  | Function/Local/Global/Type | Call | Alive |
  | Unknown / Primitive | 任意 | **Unknown（硬不变量：永不判 Dead）** |
  | Type / Primitive（值位） | Value | Unknown |

## 验证

### 回归 gate（§13.1）—— 与基线逐字节一致

```
wrong:  49/50   （唯一差异仍为 err_arraylist_toarray_assign: gold=308 fire=309）
wrong2: 50/50
```

### 100 个真实 fire 全量断言

- 非空行 fire 全部带 symbol_kind/tail/boundary：0 缺失
- UnknownSymbol → Dead：0
- verdict 分布：Unknown 51 / Alive 43 / none 6（非标识符 fire）
- kind 分布：unknown 28 / function 18 / local 16 / primitive 12 / method 8 /
  type 7 / static 5 / none 6

### 五个计划命名模式（合成探针，fire 时刻区分）

| 探针 | symbol | kind | tail | boundary | verdict |
|---|---|---|---|---|---|
| `abs(1)` 错误返回位 | abs | function | call | assign_rhs | **Alive** |
| `helper` 未声明 | helper | unknown | value | statement | **Unknown** |
| `ArrayList.of(1, 2)`（deque 族静态） | of | static | call | member_sel | **Unknown**（D1） |
| `m.get`（无括号，方法有参） | get | method | value | member_sel | **Dead**（R3 完整证据） |
| `m.get("k")` 返回错型 | get | method | call | member_sel | **Alive** |

另外 `m.size`（字段）→ field/value → Alive、`m.size()` → field/call → Dead 语义已
按 R2 实现（wrong/wrong2 当前无此 fire，探针验证通过）。

## 附带发现（供 Patch 3-6 使用）

- **fire 的两种落点**：mid-identifier（可扩展失败前瞻，如 `s1` 在 `s` 处 fire
  "undefined identifier"）与语句终结符（`}`/空行，此时分类器上走到语句行）。
  前者正是 dead-identifier 生产路径（Patch 5 目标）。
- **`m.get("k")` 单独成句在 runtime 不 fire**（R4 分歧：参考 checker 要求表达式
  语句为 Unit，runtime 更宽容）→ wrong/wrong2 无此样本；若隐藏集含此类，runtime
  会漏 fire/迟 fire。列入 Patch 5 裁决表。
- lambda 族 fire（run/eval/bad/tri/inner/wrap/echo/takeInt）已能按 kind 区分
  （function vs static vs method），是 Patch 6 LambdaFrontier 的输入。
- trace 新增 `line` 字段：每个 fire 都有 fire 时刻的源码最后一行，后续 patch 的
  观测工具直接可用。

## 提交

- 本 patch 不触碰 checker 判定路径（纯 shadow 观测）。
- git commit：Patch 2 单独提交；context.bin 未变，无 §5.4 影响。
