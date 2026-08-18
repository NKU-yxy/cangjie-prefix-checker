# v13-Narrow-Recovery 提交记录（2026-08-19 打包，待上传）

## 交付物

- `cangjie-checker_v13_Narrow_Recovery_20260819.zip`，899,657 B < 1MB
- zip sha256：`2e1996b2eac322bddba879b4d578c8bb1c9defedbbcf965e95753810c011779b`
- 方案：**v11（100/100 公开门禁基线）模型原样 + 两点窄化**：
  1. primitive→String 硬编码（`{Int64,Float64,Bool}`）替换为**链闭包**
     `ChainClosureReaches({Int64,Float64,String})`：三者在 postfix 链上任意深度
     相互可达（`1.0.toString().size`→Int64 保持 `1.0` 存活，对应
     err_rel_mixed_numeric）；**Bool 在位置层无成员**（`true` 立即锚定，
     对应 err_type_mismatch / err_arith_non_numeric —— 尽管
     checker.py:1021 硬编码 Bool.toString，位置层语义以 audit 为准）；
  2. 虚构零参函数调用规则（仅"零参→直接兼容"存活）替换为**函数值恒存活**
     （尾部确实是函数值 → 可继续，Plan 5.3 明确要求，对应 err_abs_* 家族）。
- 其余全部继承 v11 原样（v11 已证明 100/100 公开门禁）：
  - result 兼容任意元数（err_instance_method_args：`p.add` 的 Int64 结果）；
  - 裸类型变量结果 `IsIdentifierText(result) && !KnownType(result)` → 存活
    （err_lambda_infer_interface_helper 的 `run<R>` 的 `R`）；
  - 带参方法结果 + 一层浅 postfix（HasShallowPostfix）→ 存活；
  - 裸标识符 dead_identifier 判定与 v11 完全一致。
- 与 v12-F1-L zip 的 manifest 逐文件一致（109 文件），**仅 cpp/native_semantic.cpp
  内容变化**（sha256 `360456c4017834697df246e56ccf5903df381322a35bd3cd6d3f191e02172b59`）；
  build.sh / context.json / context.bin 字节级一致。vs 纯净 v11（/tmp/v11_ns.cpp）的
  diff = 59 行，仅含上述两处函数体替换 + 注释。
- 本地复验：zip 解压 → build.sh（macOS 本地仅替换链接参数
  `-Wl,--gc-sections` → `-Wl,-dead_strip`，**交付 zip 内 build.sh 保留 Linux
  原版未动**）→ solution `e3a86470de57ca9c57dd1746bf0fdabe2af7e09d82bea12a883a6d73721785e0`，
  与直建版本**字节一致**。

## 分支与 commit

- 分支：`v13`，自 v12-F1-L（`09abd7c`）分出
- 本次：交付 zip + 结果记录（native_semantic.cpp 两点窄化 + build.sh 恢复
  Linux 原版一并提交）

## 本地门禁（交付前复验）

| 验证项 | 结果 |
|---|---|
| 官网 harness wrong（50 例，官方新 golds） | **50/50** |
| 官网 harness wrong2（50 例） | **50/50** |
| vs v11 全 100 例 fire 序列差分 | **0 divergence**（v13 ≡ v11 于公开集） |
| vs v12-F1-L（官方 63 基线）全 100 例差分 | **1 divergence**：恰为 err_arraylist_toarray_assign 309→**308 = gold**（v10 起遗留偏差收敛）；interface_helper 304 / instance_method_args 335 等其余全部逐字节一致 |
| zip 解压重建复验 | solution 字节一致；wrong 50/50 + wrong2 50/50 |
| zip 大小 | 899,657 B < 1MB |

## 探测矩阵（v11 → v13，合成形态）

| 形态 | v11 fire | v13 fire | 判定 |
|---|---|---|---|
| toarray_assign（arr→String 一 hop dead） | 39 | 39 | 相同（合成布局，公开集 gold=308 两版均一致） |
| f64→Int64（链 2-hop 存活） | 23 | **24** | ✓ 延迟一 token：标识符处存活 → 推迟到换行 |
| f64→Bool（链存活） | 22 | **23** | ✓ 同上 |
| i64→Bool（链存活） | 20 | **21** | ✓ 同上 |
| i64→Float64（链 dead） | 21 | 21 | 相同（闭包不可达，仍立即锚定） |
| bool→String（Bool 无成员） | 19 | **18** | ✓ 提前一 token：v11 硬编码存活，v13 立即锚定 |
| str→Bool（链存活） | 20 | 20 | 相同（String→Bool 两版均可达） |
| abs→String / abs→Bool / abs→Int64 | 11/11/12 | 11/11/12 | 相同：合成探测中 typer-error 路径先于 dead_identifier 触发，函数值规则未达（见边界） |
| alist→String / opt→String / deque→String | 27/43/29 | 27/43/29 | 相同（一 hop dead，与 v11 一致） |
| opt→Int64 / map→Int64 / range→Int64 | 45/33/26 | 45/33/26 | 相同（一 hop alive，与 v11 一致） |

**意图位移汇总：4 处**（f64→i64、i64→bool、f64→bool 各 +1 = 更晚、bool→String −1
= 更早），全部与 audit 锚点语义一致；其余 12 形态与 v11 完全一致。

## 设计依据（Plan 5.3 提交 3 放行条件逐条）

1. **当前最高基线 + 只由官方 context 显式产生的恢复 witness**：v11 模型原样（含
   official context 的 member 表）；两点窄化全部由官方 context / audit 显式支撑。
2. **primitive 硬编码**：{Int64,Float64,Bool}→String 替换为链闭包 —— 硬编码丢失
   `1.0→Int64`（rel_mixed_numeric）与 `Int64→Bool`、`Float64→Bool` 形态；
   Bool→String 保留（Bool 成员less，位置层锚定）。
3. **虚构零参函数调用**：替换为函数值恒存活 —— v11 的"零参 + 结果兼容"规则对
   带参函数值（`abs` 等实参形态）判 dead，与 err_abs_* 家族（官方隐藏集中
   v12-L 通过、v11 丢失）矛盾。
4. **裸类型变量匹配任意目标**：保留 v11 规则（err_lambda_infer_interface_helper
   官方 gold 证明必要）。
5. **无参数可构造证明的带参方法边**：保留 v11 规则（HasShallowPostfix，
   err_instance_method_args 官方 gold 证明必要）。

## 预期官方结果与判别标尺

- 基线：v12-F1-L = 63/100。v13 在公开 100 例上与 v11 逐字节一致、与 v12-L 仅
  toarray 一处分歧（且指向 gold）→ **63 例预期全保留**。
- 潜在增益（隐藏集中 v11 丢失、v12-L 拿到的 4 例 err_abs_bool_helper /
  err_abs_to_string / err_arraylist_get_throw_str / err_deque_capacity_string 的
  形状族）：
  - Float64→Int64 / Int64→Bool / Float64→Bool 接收者形态 → 链闭包覆盖；
  - 函数值形态 → 恒存活覆盖（生效前提：真实文件的 typer 状态使
    dead_identifier 可达，见边界）。
- 判别标尺：err_stack_toarray_string 不在预期增益内（dead_identifier 行为与
  v11 一致）——若官方通过该例，说明其丢失机制与 recovery 无关，需复核归因。
- 风险：Bool→String 形态若官方按 checker.py:1021 硬编码存活（而非 audit 的
  位置层锚定），v13 将提前一 token 新丢一例。audit 为位置层唯一权威，接受。

## 已知边界

- **abs 函数值形态的 fire 路径**：合成探测中 v11/v12-L/v13 全部 fire=11（换行），
  经 typer-error/defer 路径而非 dead_identifier（stderr 空，CANGJIE_DEBUG_FIRE
  未触发）——`actual.known && !actual.error` 门控使 HasRecoveringMember 未被
  咨询。但 v12-L 以同样 fire=11 通过官方 abs 隐藏例 → 官方 gold 即此路径；
  函数值恒存活规则在"已知且无错"的函数值标识符形态下才生效（若真实文件
  布局使 typer 已知，v11 会在标识符处早报 → v13 修正；合成探测无法完整
  复刻真实文件的 typer 状态）。
- **get_throw / deque_capacity 形态**：v13 与 v11 行为一致（一 hop dead 锚定）。
  官方若在该两例锚定更晚，与 toarray（Array 一 hop dead、gold=308 锚定标识符）
  在 member 表层面不可区分（三容器 one-hop 均无 String 成员），无规则能在
  不破坏 308 的前提下同时存活两者 —— 若丢失，属不可修复边界，记录备查。
