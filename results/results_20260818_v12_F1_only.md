# v12-F1-only 提交记录（2026-08-18 打包，待上传）

## 交付物

- `cangjie-checker_v12_F1_only_20260818.zip`，891,348 B < 1MB
- zip sha256：`ba5ef4dcdefd5decc9705b331a3af021aef9b969e825c738a6621eba3fcd10fa`
- 方案：**v10 基线 + F1 单一机制**（Array.first/last 从零参方法修正为 Optional\<T\> 实例字段）
- manifest 与 v10 zip 逐文件一致，仅 3 个文件内容变化：

| 文件 | v10 sha256 | v12 sha256 |
|---|---|---|
| context.json | `facb628ab01a52d7ef8f2fe36ca463ccd381e02e45282c82803b793730068303` | `b7d248af346c73d674843d49320bab2856767a08295a4e8ca9ac891c4ced45cd` |
| cpp/native_semantic.cpp | `a3199658838902b3910664554385b569aca94a77599409ad66c52ee85a78e7e4` | `20d506ab140654c0a963b39d2bed05398019162c3f6756d9acaa602d10be513d` |
| generated/context.bin | v10 zip 内 8044 B | `4c592b1abc1a9c59e3bfb8d61ea303bed4f628392ec669f300b3fe4ba6f5ceb7`（8012 B） |

- 本地复验：zip 解压 → build.sh（Linux 版，macOS 本地仅替换链接参数 `-Wl,--gc-sections` → `-Wl,-dead_strip`）→ solution

## 分支与 commit

- 分支：`v12-f1-only`，自 v10 `8720cc0` 分出
- `3c2dc3a` F1 改动（context.json + native_semantic.cpp，5 insertions / 27 deletions）
- `c4cccd5` 新增 tools/run_terminal_gates.py（wrong/wrong2 官方新 golds 门禁）
- `7eab83a` 交付 zip
- v12 相对 v10 的完整 diff = 仅 F1 两处（已验证 `git diff 8720cc0` 无其他内容）

## 本地门禁（交付前复验）

| 验证项 | 结果 |
|---|---|
| 官网 harness wrong（50 例，官方新 golds） | **48/50**（与 v10 完全一致：err_arraylist_toarray_assign 309-vs-308、err_lambda_interface_callback_explicit 341-vs-344 两个有意偏差原样保留） |
| 官网 harness wrong2（50 例） | **50/50** |
| v10 vs v12 全 100 例公开集 fire 序列差分 | **0 divergences**（F1 不触碰任何公开用例） |
| zip 解压重建复验 | wrong 48/50 + wrong2 50/50，与直建 solution 一致 |
| 最坏单例耗时 | 1.147s ≪ 5s |
| zip 大小 | 891,348 B < 1MB |

## F1 家族专项（官方 typechecker + context_final 裁决 vs v12）

关键证据：官方 context_final.json 的 JSON 结构将 first/last 列在 instance_methods，
但官方 typechecker **实测裁决为字段语义**（`a.first` 报 `got Optional<Int64>`、
`a.first()` 报 `not callable Optional<Int64>`）——v11/v12 的字段模型与官方实测一致。

| 用例形态 | v10（方法模型） | v12（字段模型） | 官方 typechecker |
|---|---|---|---|
| `let o: Optional<Int64> = a.first`（合法） | fire=30 **误报** | NO FIRE ✓ | 合法 |
| `let o: Optional<Int64> = a.last`（合法） | fire=30 **误报** | NO FIRE ✓ | 合法 |
| `pick<T>(a: Array<T>): Optional<T> { a.first }`（合法） | fire=15 **误报** | NO FIRE ✓ | 合法 |
| `(a.first.getOrThrow()).toString()`（合法） | fire=31 **误报** | NO FIRE ✓ | 合法 |
| `a.first()` / `a.last()`（非法） | NO FIRE **漏报** | fire=30 ✓ | `not callable Optional<Int64>` |
| `let s: String = a.first`（err_array_first_optional 族） | fire=27 | fire=29（println） | 类型不匹配（gold 待官网确认） |

`let s: String = a.first` 的 v12 fire=29（println，换行延续后新语句起点）与 v11 行为一致
——v11 官方通过 err_array_first_optional 的记录表明该锚点与官方 gold 匹配，v12 预期 +1。

## 官方结果（待填写）

- 提交时间：___
- 得分：___ /100（v10 = 60/100）
- 通过名单变化：___
- 归因：___

## 预期与决策规则（Plan 5.3 提交 1）

- 期望新增 `err_array_first_optional`，不丢失 v10 的四个 String/helper 家族（err_abs_bool_helper、
  err_abs_to_string、err_arraylist_get_throw_str、err_deque_capacity_string）；
- 若 61：升为新基线；
- 若 60 且通过集合不变：保留实验记录，不升基线（F1 需与其他机制交互）；
- 若 <60：检查 context.json / AddBuiltinModel / context.bin 双源冲突（已预检：加载顺序
  AddBuiltinModel → LoadContextTable 整体覆盖 nominals，运行时以 context.bin 为唯一事实源，
  两源一致，无冲突）。

## 已知边界（非 F1 引入，v10 既有）

- `(a.first.toString())`：官方报 `no member toString on Optional<Int64>`，solution 两版均 NO FIRE
  （Optional.toString 缺失时 solution 未报 no-member；与 F1 无关，记录待后续 narrow-recovery 处理）。
