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
