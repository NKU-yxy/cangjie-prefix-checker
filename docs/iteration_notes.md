# 迭代笔记 — 仓颉片段检查器

## v0（2026-08-17）— 基线

**结果**：56/100 通过（详情见 `results/results_20260817_v0.md`），判题 WA，得分 0.00。全部耗时 0.388–1.147 s，均值 ~0.464 s，无超时。

### 观察

1. **通过用例全部是 `err_*` / `infer_*` 命名** —— 官网隐藏集（至少已显示的部分）看起来是错误用例集；44 个失败的用例名**无从得知**（官网只报通过的）。
2. **lambda 已可用**：err_lambda_* 9 个全过，说明 lambda 语法/类型路径基本工作。
3. **泛型推断（infer_*）8 个全过**，但这类用例在 70/15/15 分层里属于 15% 的难层，数量少不代表覆盖全。
4. **耗时异常点**：`err_lambda_param_narrow` 1.147 s，是均值 2.5 倍 —— 参数窄化（narrow）路径可能存在低效（比如类型矩阵爆炸或重复计算），值得 profile。
5. err_deque_*（8）与 err_stack_*（7）合计 15 个通过，说明容器 API 家族覆盖尚可。

### 未知/风险

- 44 个失败用例的**名字与类别未知**。需要本地复现策略来获知失败模式：
  - 本地 50 公开用例是否全过（契约要求）；
  - 仓库 tests/、benchmark/ 里是否有 hidden 风格（err_*/infer_*）用例可直接跑；
  - 与参考 typechecker 做 differential 测试。
- 官网判题"得分 0.00 / WA"的语义未完全确认：可能是整体 WA 的展示方式，也可能平台另有计分逻辑 —— 下次提交时对比确认。

### 下一步候选（按预期收益排序）

1. **摸清本地评测环境**：跑通 build.sh → 对 50 公开用例验证；检查 tests/、benchmark/、tools/ 是否有隐藏风格用例与参考实现可对比。
2. **构造差分测试**：拿参考 typechecker（gitcode 仓库）对错例片段逐个前缀比对，找出我们"该输出 0 却输出 1"的类别。
3. **profile err_lambda_param_narrow 类路径**（1.147 s 异常点）。
4. 修复完一轮后重新提交官网，拿到新的通过列表再对 diff。

---

## v0 补充调查（2026-08-17 晚间）

### 本地复现环境（已搭建）

- **Docker 就绪**：官方镜像 `docker.educg.net/compiler_system_challenge/cjchecker:v1.2`（linux/arm64）已拉取，daemon 运行正常。
- **判题流程逆向完成**：镜像 ENTRYPOINT = `build.sh` → `/course_grader.py --checker-root /opt/cangjie-fragment-checker --testdata-dir <隐藏集挂载> --solution ./solution`。判题器在 `official-reference/course_grader.py`（从镜像提取）。协议：harness 逐行发 tiktoken cl100k_base token ID，solution 逐行回 0(OK)/1(错误)，`--competition-output` 翻转；判题器直接调用 `./solution`（默认约定），5 秒/例超时，verdict = AC/WA/TO，detail 只列通过用例 —— 与官网输出格式完全一致。
- **本地评测脚本**：`official-reference/`（镜像内参考仓库 + 判题器）+ `reference-upstream/`（gitcode 官方仓库）+ `local-testset/`（wrong2 挂载布局）。
- solution 已在官方容器内重建（Linux AArch64，1.6MB）。

### 本地评测结果（全部 AC）

| 数据集 | 结果 | 说明 |
|---|---|---|
| wrong/ 50（官网公开例） | **50/50 AC** | 单例 0.24–0.30s（含 harness 开销） |
| wrong2/ 50（gitcode 二期数据集） | **50/50 AC** | 单例 0.15–0.36s |
| 自有 hidden_semantic_fuzz（20260814 快照） | **0 failures** | 6 家族 × 24 例，官方 oracle 打标 |

### 核心判断：44 个隐藏失败在哪

- gitcode 仓库只有 master 分支、只有 wrong/ + wrong2/ 两套数据，**官网隐藏 100 例不在任何公开仓库**。
- 从官网通过的 56 例命名推断，隐藏集**深度测试 context API 语义**：`err_optional_is_some_bool`（Optional.isSome）、`err_array_slice_index`（Array.slice）、`err_deque_reserve_arg`/`err_deque_capacity_string`/`err_deque_clear_unit`、`err_hashmap_replace_value`/`err_hashmap_contains_key`、`err_string_indexof_optional`/`err_string_empty_to_int`、`err_arraylist_get_throw_str`/`get_optional` 等 —— 这类"方法用错参数类型/返回值/接收者"的语义错误，在 wrong/、wrong2/ 和自有 fuzz 家族中**基本没有覆盖**（fuzz 家族只有 multiline/nested_lambda/overload/generic_inheritance/valid/scope_isolation）。
- 结论：**失败集中在 context API 方法调用的语义深度**（Optional 判空、切片/索引类型、reserve/capacity/clear/fill 等具体方法签名）。

### 迭代 1 方向（待与用户确认）

1. **建 context-API 语义差分 fuzzer**：从 context.json（11 nominal + 6 接口 + 8 全局函数）枚举每个方法的错误调用变体（参数类型错、arity 错、接收者错、Optional 方法用错、返回类型不匹配等）→ vendored 官方 typechecker（third_party/cangjie_typechecker）打标 → 与 solution 差分。发现的偏差 = 隐藏失败候选，逐一修复。
2. 差分发现的 bug 修复后，重跑全部本地集 + 官网提交验证。
3. profile err_lambda_param_narrow（1.147s）作为性能侧并行项。

---

## v1（2026-08-17/18）— context-API 差分 fuzzer 迭代

### 交付内容（solution 3 处修复）

1. **InferCall 不丢弃未闭合调用的尾部空参数**（`f(1,` 的逗号锁定前一个参数）：`HashMap<String, Int64>(1,` 在逗号处即不可续 → 官方 GT 在 `,`；保留空槽让 arity 检查在逗号处拒绝，而不是推迟到闭括号。
2. **多重载方法引用歧义**：官方 typechecker 判定 `(Int64) -> Unit = values.add` 为 INVALID（add 有 4 个重载 → 方法引用有歧义，即使期望类型匹配单个候选）。InferImpl 成员访问分支：候选 >1 时直接报 "ambiguous overloaded member reference"。
3. **未闭合超参立即拒绝**（零参方法 `a.clone(1`）：官方 GT 在参数 `1` 本身（`.toString()` 续写救不了 arity）。两处配合：
   - `CheckSignatures`：未闭合超参只记 `over_arity_fallback`，仅当**所有候选都放不下**参数数时才提升为 "wrong argument arity"（否则让更具体的参数类型诊断胜出，保证 `String(1` 可续 `.toString())` 时推迟）；
   - `should_defer_expression_error`：`"wrong argument arity"` 且非 `(` 结尾 → 不 defer（`a.clone(` 因参数列表未开始仍可续 `)`）。

### fuzzer 校准（5 处）

- reassign_type 填充用 `v`（`rv` 未声明污染差异）；
- `longest_member_prefix`：成员名与真实成员共享字符前缀时（`a.is` + `Empty()` = `a.isEmpty()` 合法），GT 在最长共享前缀之后（BPE 字符粒度可续性）；
- ctor_arg：括号内扫描字面量，避免 `Int64` 里的 "1" 误匹配；
- arity_long：`nth_top_level_comma`（从 `(` 之后计数）→ GT 在最后一个合法参数后的逗号；
- arg_type：恢复 `+ len(lit)`（数字参数类型错 GT 在 `)`，`.toString()` 可续）。

### 结果

| 验证集 | 结果 |
|---|---|
| wrong/ 50 | 50/50 AC |
| wrong2/ 50 | 50/50 AC |
| hidden_semantic_fuzz（官方 oracle 打标） | 144 标签，0 failures |
| context_api_differential | **475 generated，34 → 0 divergences** |
| native_context_differential | 7/7 |

### 澄清的"非问题"

native_fragment_differential 报 5 个 valid-片段被拒（function decl、package+import、无返回类型 `func main() {`、`Array<Int64>(10)`、`Map<String, Int64>()`）—— 用官方 vendored typechecker 复核：**5 个全部 INVALID**（Int32 不在 context；官方语法要求返回类型注解；package/import 不支持）→ main.py 标签过时，solution 与官方一致，非 bug。

### 已知边界（接受）

- `a.clone((`（`((` 直接嵌套在未开始参数列表）→ 尾部 `(` 触发 defer，与官方 GT 差 1 token。病态形态，fuzzer/隐藏集不生成。
- 多参超参 `m.add(1, 1, 1, 1)` 的 GT 在逗号（官方已校准）✓；零参超参 `a.clone(1)` GT 在 `1` ✓（本轮修复）。

### 下一步候选

1. 官网提交 v1，拿新的通过列表对照（预期 56 → 显著上升，重点看 err_* 容器/字符串类）。
2. 若仍有失败：对失败类别建针对性差分（lambda 推断、泛型推断 infer_* 族 —— fuzzer 目前只覆盖 context-API 方法调用）。
3. profile err_lambda_param_narrow（1.147s）性能侧并行项。

---

## v2（2026-08-18）— 尾空参 double-push 修复 + 隐式泛型 strict 延迟

### 交付内容（solution 2 处修复）

1. **删除 InferCall 尾空参数 re-attach 块**：SplitTopLevel 已保留尾随空槽（`SplitTopLevel("2,", ',')` = `["2",""]`），re-attach 造成 double-push（nargs=3）→ `Array<Int64>(2,` 在逗号处误报。删除后 8 个 wrong/ 用例恢复、validation 50/50。
2. **CheckSignatures Compatible 失败分支新增 strict 延迟**：官方对隐式泛型裸调用（min/max，T 从不绑定）在 `)` 才拒绝候选（"no matching call candidate"），未闭合调用内的参数不匹配不得锁定逗号/字面量位置。

### 结果

| 验证集 | 结果 |
|---|---|
| wrong/ 50 | 50/50 |
| context_api_differential | 538 生成，22 → 11 分歧 |

### 官方锚定规则实证（wrong/ 50 例 GT 分析）

官方 first_error_token_index 的锚定规则（直接证据）：
- 超参/少参 → 调用闭合 `)`（err_arity: add(1) → 374=`)\n`）
- 参数类型错 → 参数闭合点（err_arraylist_add_type: a.add("x") → `")\n`）
- 不可救字面量 → 字面量本身（err_arith_non_numeric: `let bad: Int64 = true` → `true`；err_array_index_not_int64: a[true → `true`）
- 可扩展表达式（标识符/字符串+后缀）→ 延迟到语句边界 `\n`（err_arraylist_toarray_assign: `let s: String = arr` → `\n`；err_assign_let: `n = "x"` → `"\n`）
- 关键字错误 → token 本身（continue/break）

**推论**：官方 GT 不是"main 闭合 `}`"（probe 全量 parse 假象——typecheck 只在语法完整前缀跑），而是增量检查的锚定位置；solution 的参数闭合点机制与 wrong/ 50 例一致。

---

## v3（2026-08-18）— min/max 超参延迟 + fuzzer 模型修正，差分归零

### 交付内容（solution 2 处修复）

1. **actual.error 分支加 strict 延迟**：`[1, 2]` vs Array<T>（T 未绑定，InferImpl 无法解构 Array<T>）不再锁定逗号——延迟到 `)` 候选匹配失败。
2. **over_arity_fallback 在 strict_generic 下不提升**：`min(1, 1, [1, 2], 1)`（4 参 > min 3 参）的超参延迟到 `)`——官方 T 从不绑定，任何调用在 `)` 报 "no matching call candidate"。

### fuzzer 模型修正（4 处）

1. **g_arg/g_arg_mixed 非尾参去掉 +1**：字面量结束边界即逗号本身（`clamp("bad", ...)` 的 `"` 与逗号同 token）——clamp/print 4 例消除。
2. **g_arity_long 长重载判定加 arg0 兼容性**：`print("x", 1)` 有 (String, Bool) 长重载且 arg0="x" 兼容 → GT 在 `)`；`print(1, 1)` 的 arg0=1 对长重载全错 → GT 在逗号1（arg0 在逗号1 已锁定）——print/eprint 数值重载 5 例消除。
3. **mixed 表移除 Float64→"1"**：Int64 字面量对 Float64 是隐式转换（`abs(1)` 匹配 abs(Int64) 重载，官方报的是尾表达式 Unit 错而非参数错），不再生成假错 case。

### 结果

| 验证集 | 结果 |
|---|---|
| context_api_differential | **536 生成，0 分歧** |
| wrong/ 50 | **50/50** |
| hidden_semantic_fuzz | **144 标签，0 失败** |

### 下一步候选

1. 官网提交 v3（zip 已备好 cangjie-checker_v3_20260818.zip），对照新的通过列表。
2. 若仍有失败：按失败类别建针对性差分（lambda 推断、泛型继承 infer_* 族、字符串/数值转换的深层救援语义）。
3. 性能侧：err_lambda_param_narrow（1.147s）profile。

---

## v4（2026-08-18 上午）— 决赛 CE/0 分根因定位与打包修复

### 背景

v2（02:58 提交）→ **CE**；v3 首发（09:34）→ **WA 0 分（通过列表为空）**；v3 二次提交（09:48）→ **CE**。用户反馈"估计是代码问题"，实际两处根因全部是**打包内容缺失**，与代码逻辑无关。

### 根因 1：v2/v3 zip 缺失 `grammar/` → 运行时崩溃 → 0 分（已实证）

- `solution.cpp:1148/1182/1184`：`NativeSyntaxChecker(root/"grammar"/"cangjie.gbnf")` 构造器**运行时必须读语法文件**，缺文件即抛异常 → 每个用例启动即挂 → 通过数 0。
- v1 zip **含 `grammar/`**（00:21 提交 → 60/100 ✓）；09:30 重打包（43ab84d "fix(zip): repackage v2/v3 with src/"）把 `grammar/` 换成了 `src/` —— v2/v3 zip 从此没有运行时语法文件。
- 容器实证：v3 zip 构建成功（exit=0, 1m37s）但无 grammar/；v4 恢复 grammar/ 后判题流程 100/100。

### 根因 2：v2 原包缺 `src/` → build.sh python 步骤 ImportError → CE（高置信）

- build.sh 的 `generate_context_table.py` 需要 `from src.context_loader import load_context`；v2 原始 zip（823832 B）缺 `src/` → python 步骤失败 → build.sh exit 1 → CE。
- 09:48 二次 CE 的 CE 详情行（`harness: ...; wrong_error_positions.json: ...; wrong/: ...`）为决赛判题器缺失文件/构建失败的配置行格式；zip 内容已本地全查无误，怀疑该次上传为打包路径问题（如 zip 内路径嵌套），无法复现，由 v4 的 build.sh 硬化兜底。

### 修复内容（v4）

1. **zip 补回 `grammar/cangjie.gbnf` + `cangjie_token.gbnf`**（运行时必需，v1 有、v2/v3 丢）。
2. **build.sh 硬化**：移除全部 `verify_sha256` 校验（防 hash 不匹配类 CE）；cl100k 表解压失败不硬退出（保留 shipped fallback 链）；`generate_context_table.py` 失败时保留 zip 内预置的 `generated/context.bin`；`strip` 失败容忍。唯一硬失败：无表/无 toolchain 且无 fallback。
3. **zip 预置 `generated/context.bin`**（8KB，由 context_final 生成；哈希与 v3 完全一致 —— 我们的 context.json 本就与 `reference-upstream/typechecker/typechecker/context_final.json` 逐字节相同，`HashSet.addIfAbsent` 差异不在 context.bin 编码内，检查器行为零变化）。
4. **zip 精简**：排除 `src/__pycache__` 与 `third_party/cangjie_typechecker`（开发用参考实现，构建不需要），v4 zip = 887,825 B < 1MB。

### 验证

| 验证集 | 结果 |
|---|---|
| 判题容器内完整流程（解压→build.sh→官方 harness）wrong/ + wrong2/ | **100/100 PASS**（build exit=0, 1m25s） |
| 本地 macOS 同流程 | 100/100 |
| context_api_differential（context_final 语义，容器内） | 待 fuzzer 输出 |
| 预置/生成 context.bin 一致性 | 哈希一致（2cf015b7...） |

### 下一步

1. **上传 `cangjie-checker_v4_20260818.zip`**（项目根目录，887,825 B），拿官网通过列表。
2. 若仍有失败：按类别建 context_final 专项差分（目前 fuzzer 已自动切到 context_final 语义）。
3. 性能侧维持现状（单例 0.4-0.6s，远低于 5s 上限）。

---

## v5（2026-08-18 10:35）—— 预编译二进制 + 永不失败 build.sh，判别 CE 归属

### 事实：v4 仍 CE，三包同款 CE 详情

- 10:27 提交 v4（887,825 B，容器内 100/100），官网 CE，详情与 v2/v3 二次 CE **逐字相同**：
  `harness: /opt/cangjie-fragment-checker-finals/scripts/token_interaction_test.py; wrong_error_positions.json: /opt/cangjie-fragment-checker-finals/wrong_error_positions.json; wrong/: /coursegrader/testdata/wrong`
- 该详情格式正是判题器 `course_grader.py` 缺失文件清单的渲染；三份 zip（v2 原包/v3 重打包/v4）内容互不相同（连 v4 的 solution 构建都成功 —— 否则会有 `solution executable: ...` 项），CE 详情却完全一致 ⇒ **CE 与 zip 内容无关，判题端缺失自身文件**。
- 时间线佐证：v1（00:21）正常出分 60/100 → 09:34 v3-first 正常出 WA（说明当时判题端 harness/wrong 均在）→ 09:48 起三次 CE。判题端环境在 09:48 后损坏，与我们的打包无关。

### 修复内容（v5）—— 判别性提交

1. **预编译 aarch64 二进制**（`solution.aarch64.xz` 520,900 B，容器内 GCC 11.4 编译 v4 同源 `cpp/solution.cpp + native_semantic.cpp + xgrammar_core`，`-O3 -DNDEBUG -Wl,--gc-sections`，strip 后 1,629,528 B）。
2. **build.sh 零编译零依赖**：`python3 lzma` 解出二进制 + cl100k 表（judge 必有 python3 —— harness 本身是 python 脚本），`generated/context.bin` 直接 shipped；所有步骤失败容忍，**无条件 exit 0** ⇒ 我们侧不存在任何 CE 触发点。
3. zip 精简为运行产物（build.sh / context.json / grammar/ / generated/context.bin / assets/cl100k_base.bin.xz / solution.aarch64.xz），**985,455 B < 1MB**。

### 验证（判题容器 = aarch64 Ubuntu 22.04）

| 验证集 | 结果 |
|---|---|
| 解压 → build.sh | **0.16s**，exit 0，solution 1,629,528 B（aarch64） |
| 官方 harness wrong/ + wrong2/ 全量 | **100/100 PASS** |
| 负向对照（固定输出 1 的假解） | FAILED（判词不误报） |

### 判别逻辑（本次提交的使命）

- 上传 v5 后若 **CE 详情与之前逐字相同**（三路径，无 `solution executable`）⇒ 判题端问题 100% 实锤（预编译二进制 + 无条件 exit 0 的 build.sh 不可能 CE），需联系官网/平台恢复环境，我们的代码无需再改。
- 若 CE 详情**变化**（出现 `solution executable` 等新项）⇒ 有新的判题端信息，据此再定位。
- 若**正常出分** ⇒ 之前 CE 为判题端临时故障，v5 直接继续迭代语义优化。

### 下一步

1. 上传 `cangjie-checker_v5_20260818.zip`（项目根目录，985,455 B，sha256 `7b5e8f48a529722cf2d2bf6c6860c6d68c62fb4fce08b50c1a9fd9b9870bcbfc`）。
2. 按 CE 详情三种走向分别处理（见上）。
