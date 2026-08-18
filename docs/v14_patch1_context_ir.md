# V14 Patch 1 — Context Canonical IR 单源化（完成记录）

Date: 2026-08-19 · Branch: v14-aorta · 前序: docs/v14_patch0_baseline.md

## 目标（V14_Plan §5）

1. 官方 context_final.json 成为运行时模型的**唯一来源**：删除 AddBuiltinModel（其
   12 个 println/print/eprintln/eprint overload 与官方重复 = BUG_OVERLOAD；其 9 个
   nominal 全部被 context.bin 覆盖 = 死代码）。
2. 建立 canonical Context IR（context-ir-v1）双端 dump + 结构化对比工具链。
3. 生成完整 member mutation matrix（§12.2），以官方 checker 为 oracle 判定每条 snippet。

## 交付物

| 文件 | 说明 |
|---|---|
| `cpp/native_semantic.h` | `IncrementalSemanticEngine::DumpContextIrJson` / `NativeSemanticChecker::DumpContextIrJson` 声明（+`<ostream>`） |
| `cpp/native_semantic.cpp` | 删除 AddBuiltinModel（779-909）及其调用；新增匿名 namespace JSON 序列化器（JsonWriteString/Texts、DumpSignature{Json,ListJson,MapJson}、DumpFieldMapJson、DumpNominalJson、DumpModelJson）；`Impl::DumpContextIrJson`、`IncrementalSemanticEngine::DumpContextIrJson` |
| `cpp/solution.cpp` | `--dump-context-ir` flag：构造 NativeSemanticChecker 后 dump 到 stdout 即退出 |
| `tools/export_official_context_ir.py` | 官方 context JSON → canonical IR（与 context.bin 同一条 normalize 路径） |
| `tools/compare_context_ir.py` | 官方 vs 运行时 dump；diff 分类（EXPECTED_BUILTIN / EXPECTED_DEVIATION / BUG_MEMBER_KIND / BUG_DISPATCH / BUG_PARAMS / BUG_RETURN / BUG_GENERIC_SUBSTITUTION / BUG_INHERITANCE / BUG_OVERLOAD / BUG_MISSING_MEMBER）；gate = 0 BUG_* |
| `tools/generate_context_member_matrix.py` | 556 条 snippet × 17 种 shape；`--oracle` 用本地官方 checker（final context）判定 |

## 门禁结果

### §5.4 canonical IR gate — PASSED（0 BUG_*）

```
python3 tools/export_official_context_ir.py <context_final.json> /tmp/official_ir.json
./solution --dump-context-ir > /tmp/runtime_ir.json
python3 tools/compare_context_ir.py /tmp/official_ir.json /tmp/runtime_ir.json
GATE PASSED: no BUG_* differences
EXPECTED_DEVIATION ×2: Array.first / Array.last（F1 裁决，见 §1.1）
```
规模：17 nominals（11 类 + 6 接口）、8 个全局函数（23 overloads）、127 个成员签名
全部逐成员一致（含 supers、type_params、required_params、constructor 列表）。

### wrong/wrong2 回归 gate — 与基线逐字节一致

```
wrong:  49/50   （唯一差异仍为 err_arraylist_toarray_assign: gold=308 fire=309）
wrong2: 50/50
```
与 v12-F1-L 基线完全相同；AddBuiltinModel 删除对判定零影响。

## Member matrix（§12.2）

556 snippets，覆盖所有 nominal/interface member 与全局函数：

- 每种 member ≥ 合法使用 / kind 误用（字段当调用、方法当值）/ arity（多一、少一）/
  每参数位错型 / 返回目标错型（Patch 1 完成标准）
- 附加 shape：dispatch_type_name（实例成员经类型名）、dispatch_instance（静态成员
  经实例）、method_as_value（零参方法当函数引用）、field_as_call
- oracle（官方 checker，final context）判定：**127 ACCEPT / 424 REJECT / 5 解析不可达**
- 16 条 "legal 但被拒" 全部为官方 checker 的真实语义（下表）；4 条 arg_type_0 被接受
  是 print 家族 sibling overload 的正确匹配（非缺陷）

## 参考语义事实（oracle 逐条验证，后续 patch 必须镜像）

| # | 事实 | 证据 |
|---|---|---|
| R1 | **first/last 零参方法被自动应用为字段**（F1 裁决就写在官方 checker 源码里）：`[1,2,3].first` → `Optional<Int64>` 值；`.first()` → `E_SYNTH_NOT_CALLABLE not callable Optional<Int64>` | checker.py:968-969；probe |
| R2 | **字段与同名方法并存时字段胜出**：`m.size` → Int64；`m.size()` → not callable | 官方 JSON HashMap/HashSet 同时声明 size 字段与方法；probe |
| R3 | **零参方法作为值 = 函数引用**：`m.keys` → `() -> KeysView<String>`；赋给 `KeysView<String>` → E_SUBTYPE_MISMATCH | probe |
| R4 | **表达式语句必须为 Unit**：`m.get("k")` 单独成句 → `expected Unit, got Optional<Int64>` | probe |
| R5 | **官方 checker 无任何静态成员访问**：`ArrayList.of(...)`、`ArrayList<Int64>().of(...)`、`String.empty` 全部 `E_SYNTH_NO_MEMBER` | probe（context JSON 有 static_methods/static_fields，但 checker 不解析类型名作值） |
| R6 | **泛型调用不做类型参数替换**：`min(1, 2, [3])` → `candidate[1] (T, T, Array<T>) -> T -> expected T, got Int64`。min/max 在参考 checker 中**完全不可调用** | probe 全部变体 |
| R7 | **重载解析 = 从左到右第一个 typecheck 通过的 candidate**；全部失败报 E_CHECK_NO_MATCHING_CTOR 并附逐个 candidate 失败 | checker.py:_select_call_candidate |
| R8 | **ArrayList.add 有 4 个重载**（JSON）：add(T)、add(ArrayList\<T\>)、add(T, Int64)、add(ArrayList\<T\>, Int64) → `add(1, 1)` 合法 | 官方 JSON；probe |
| R9 | **官方 grammar 无 Rune 字面量**：`'a'` 解析失败 → Array\<Rune\> / String(Array\<Rune\>) 不可表达 | probe |
| R10 | **Range 字面量类型化怪异**：`(0..10).size` → `expected Range<T>, got Int64` | probe |
| R11 | **任何 nominal 均无 toString**（final context）；官方 checker 仅接受 Int64/Float64/Bool 基元的 toString（checker.py:1021） | §5.5 审计（Patch 1 不改，留待 Patch 5） |
| R12 | keys()/values() 返回 KeysView\<K\>/ValuesView\<V\>；`let r: KeysView<String> = m.keys()` 合法 | probe |

## 分歧清单（runtime vs 参考 checker → Patch 5/6 裁决）

| # | 分歧 | runtime 现状 | 参考 checker | 裁决点 |
|---|---|---|---|---|
| D1 | **静态成员分发**：runtime 支持类型名/实例访问 static_methods（native_semantic.cpp:3471,3991,4003），参考 checker 全部拒绝 | 接受 `ArrayList.of(...)` | 拒绝 | Patch 5（比照 §5.5 toString 流程） |
| D2 | **泛型全局函数调用**：runtime 是否替换 T？若接受 min/max 则比参考更宽容 | 待查 | 拒绝一切 | Patch 4（CallFrontier per-overload candidate 语义） |
| D3 | toString 硬编码（native_semantic.cpp:3582） | 全 receiver 接受 | 仅 3 种基元 | Patch 5 |
| D4 | Range.size / `0..10` 字面量 | 待查 | `(0..10).size` 拒绝 | Patch 2/5 |

## 提交

- 本 patch 不触碰 checker 判定规则（纯模型单源化 + 观测工具）
- context.bin 由 build.sh step 2 从 context.json（= 官方 + F1）再生成，与官方
  canonical IR 逐成员一致
