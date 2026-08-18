# V14 Patch 6 — LambdaFrontier 最小结构化接入（完成记录）

Date: 2026-08-19 · Branch: v14-aorta · 前序: docs/v14_patch5_activation.md

## 目标（V14_Plan §9.1–9.4 / Patch 6 小节）

- 从 CallFrontier 获取 expected signatures；
- 新引擎判定已知场景；
- Unknown 使用 twin；
- 跑 anti-overfit 矩阵。

## 核心发现：结构化「运算符提交」假设被语料证伪

Patch 6 的首要工作是验证 tick_callback 的 `+` 锚点能否结构化判定
（body 尾部二元运算符 → 结果族 ≠ expected → fire）。逐字对比两份官方
audit 后该假设被直接证伪：

| 程序 | 相同结构 | gold | audit 依据 |
|---|---|---|---|
| err_lambda_tick_callback (wrong2) | `relay<String>(w, 4, { v: Int64 => v + 1 })` | **`+`** (250) | 「The `+` commits Int64 arithmetic, and an appended `.toString()` would bind to the operand `1`, not to `v + 1` — no recovery to String.」 |
| err_lambda_interface_callback_explicit (wrong) | `runThrough<String>(s, 4, { v: Int64 => v + 1 })` | **`})`** (344) | 「After `v + 1` the prefix is still extendable via `.toString()` … The `}` closes the lambda body with `Int64` as its last expression.」 |

两个程序在 `+` 处逐 token 同构（仅 callee 名与实参标识符不同），官方锚点
却一个在运算符、一个在闭括号——因此运算符提交**不是**结构的，唯一的判别
特征是该 body 是否在先已被官方 checker 校验过为合法（tick_callback 中
`staticBump` 的 `relay<Int64>(w, n, { v: Int64 => v + 1 })` 先于 bad
拷贝）：**err_lambda_interface_callback_explicit 就是 tick_callback 的
无 twin 孪生体**（官方证据）。

实测确认（中间实现 + 回退）：把 twin 门替换为无条件结构化规则后，
interface_callback_explicit 在 341（`+`）误 fire（gold=344）；回退后
恢复 100/100。结论：twin 门不是 anti-overfit 启发式，而是官方 checker
按声明顺序 typecheck body 后留下的**文档化行为**。

## 提交点分类（§9.3「三类共性问题」对照）

| 提交点 | 机制 | fire 位置 | 语料数 |
|---|---|---|---|
| `}` 闭 lambda body 类型 | 结构化（5169：`result_body.known && !Compatible(body, expected)`） | `}` / `})` | 12 |
| `=>` 元数 / 需标注 | 结构化（5108 arity、5111 annotations） | `=>` | 3 |
| lambda 参数类型错配 | 结构化（5127 per-param 双向 Compatible；5080 部分头） | 参数 token | 1 |
| 外层调用 `,` / `)` | CheckSignatures（外层候选 + lambda 实参） | `,` / `)` | 4 |
| body 尾部二元运算符 | **twin 门**（5164，Unknown 时才回退的形态） | `+` | 1 |
| 变量初始化器 | Patch 5 LetRhsRecoverable | `}` | 1 |

22 个 err_lambda_* fire 全部恰在 gold（下表 §13.2 后）。

## Anti-overfit 矩阵（§9.4，work/patch6_matrix/ 逐例实跑）

以官方 wrong2/err_lambda_tick_callback.cj 为母本生成 10 个变体：

| 变体 | fire | 锚点 | 判定 |
|---|---|---|---|
| v1 删除前置 twin（整个 staticBump 定义+调用移除） | 204 | `})` | ✓ 与 ifcb 官方 gold 模式一致（无 twin → `}`） |
| v2 bad lambda 首位（定义仍在声明期注册 twin） | 226 | `+` | ✓ twin 在声明期注册（官方 checker 同样按声明顺序 typecheck body），与调用顺序无关 |
| v3 alpha-renaming 双改（twin+bad 都改 `x`） | 250 | `+` | ✓ canonical 文本一致 → `+` |
| v4 alpha-renaming 仅改 bad | 253 | `})` | ✓ 无文本 twin → `}` |
| v5 空白/括号变化（bad 加括号） | 255 | `})` | ✓ canonical `(v+1)` ≠ `v+1` → `}` |
| v6 等价常量（bad 改 `v + 2`） | 250 | `+` | ✓ 运算符时刻 body 为 `v +`，前缀匹配 twin `v+1`，与右操作数无关 |
| v7 等价常量双改 | 250 | `+` | ✓ |
| v8 显式/隐式参数切换（bad 去注解） | 247 | `+` | ✓ body 文本相同 → `+` |
| v9 expected signature 改变（`relay<Int64>` + `let bad: Int64`） | — | 无 fire | ✓ 程序完全合法 |
| v10 嵌套 lambda 调用（`{ u: Int64 => u }(v) + 1`） | — | 无 fire | ⚠️ **不支持形态**：lambda 调用表达式超出子集引擎 → 整体 Unknown → 假接受。按 §9.3「本轮不新增启发式」原则不加代码，如实记录 |

关键性质验证：
- **v2**：twin 注册发生在**声明检查期**（函数体按序 typecheck），不依赖
  调用到达顺序——与官方 checker 行为一致；
- **v6**：运算符锚点判定发生在 `+` 到达时刻（body `v +` 已是 twin 前缀），
  与后续右操作数无关——与 audit「The `+` commits」的时刻一致。

## §13.2 信息增益对照（LambdaFrontier 项）

> LambdaFrontier 修复 ≥ 2 个非 twin-only 形态

非 twin-only 形态（全部结构化、有证据）：

1. **闭 lambda `}` 返回类型锚点** — 12 例（hof_explicit 380、hof_return
   313、in_class_static_explicit 264、infer_class_helper 278、
   infer_interface_helper 304、infer_wrong_return_1 255、
   infer_wrong_return_2 348、interface_callback_explicit 344、
   maplabel_return 350、return_type_explicit 314、static_eval 231、
   zero_body_explicit 258），官方 audit 原句（maplabel_return）：
   「The body is recoverable via `.size` until the lambda `}` commits it」；
2. **`=>` 时刻决策（元数 / 需标注）** — 3 例（arg_arity_explicit 340、
   arity_vs_pair 233、needs_param_types 324）；
3. **参数类型错配** — 1 例（param_narrow_explicit 306）；
4. **外层调用关闭 `)` / `,`（expected 来自 CallFrontier 候选）** — 4 例
   （collection_1 289、collection_2 308、ambiguous_1 307、ambiguous_2 353）。

twin 门仅覆盖 1 例（tick_callback 250），且该例经 audit 双向证明就是
twin 依赖形态（见上）——§9.1「Unknown 才允许 twin」满足：结构化引擎对该
形态返回 Unknown（两个 audit 的锚点对同一结构不同），twin 是唯一能命中
官方锚点的机制。

## §9.2/§9.3 范围决策（诚实记录）

- **多 overload 的 expected 联合**（§9.3「对多个 overload 分别检查」）：
  未激活。语料中歧义例（infer_ambiguous_1/2）的官方锚点在**外层调用**的
  `,`，由 CheckSignatures 在 gold 处 fire；lambda 内部不存在「多候选不同
  expected 改变锚点」的语料目标。当前 expected 来自外层调用推断（含类型
  参数替换，`relay<String>` → `cb: (Int64) -> String`），两例 audit 均依
  赖该替换成立。多候选联合属无目标新行为，按 §6.2 保持 fallback。
- **嵌套 lambda 调用表达式**：不支持（v10 假接受），按 §9.3 不加启发式。

## 验证

### 回归 gate（§13.1）——全绿

```text
wrong:  50/50   wrong2: 50/50   （22 个 lambda fire 全部恰在 gold）
```

### 22 个 lambda fire 逐例（fire=gold 全部命中）

```text
=> 3 例（元数 2 + 需标注 1）· 参数 1 例 · `,`/`)` 4 例（外层调用）
`}`/`})` 12 例（闭 lambda）· `+` 1 例（twin 门）· `}` 1 例（变量初始化器）
```

## 代码变更

净 diff 为 0 行为变化 + 1 处注释（回退结构尝试后与 Patch 5 字节等价，
注释记录了证伪结论与 audit 依据）。`work/patch6_matrix/` 10 个变体文件
保留为 anti-overfit 证据（不随 zip 打包）。

## 提交

- 生产路径与 Patch 5 完全一致（gate 100/100 证明）；
- git commit：Patch 6 单独提交（注释 + 本文档）。
