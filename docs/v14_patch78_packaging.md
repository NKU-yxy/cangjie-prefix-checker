# V14 Patch 7-8 — 性能验证 + 打包 v14-AORTA（完成记录）

Date: 2026-08-19 · Branch: v14-aorta · 前序: docs/v14_patch6_lambdafrontier.md

## 交付物

```text
cangjie-checker_v14_AORTA_20260819.zip   861,885 B（842 KB，< 1MB 门禁 ✓）
99 文件，现场编译型 build.sh，Linux 原始标志（-Wl,--gc-sections）
```

## §13.3 性能门禁（实测，100 程序 + 有效程序）

| 指标 | v12-F1-L 基线 | v14-AORTA | 门禁 | 结论 |
|---|---|---|---|---|
| 错误集均值（100 例，slow path） | 209 ms | **202 ms**（-3.3%） | ≤ 基线 +15% | ✓ 均值低于基线 |
| 错误集中位数 | 213 ms | 203 ms | — | ✓ |
| 错误集最大值 | 801 ms | 775 ms | 单例 < 1 s | ✓ |
| 有效程序全扫（262 tokens） | — | 432 ms（含 Python 喂 token 开销） | 单例 < 1 s | ✓ |
| 大例（2199 tokens，早停） | — | 94 ms | 官方硬限制 < 5 s | ✓ 6 倍余量 |

**结论：v13 的 15–25% 性能回退已被消除**（v14 均值低于 v12-F1-L 基线），
且已有缓存全部在位：

- `ComputeShadowWitness` 按 frontier key 缓存（witness_cache_ + stats，
  trace 的 `witness_cache` 字段）——Patch 3 交付；
- `DelimiterCloseCache`（语法阶段，native_semantic.cpp:1219）——基线已有；
- LetRhsRecoverable BFS 上限 32 状态，仅在裸标识符 let-RHS 调用。

计划 Patch 7 的 TypeRef/NameId intern、candidate dedup、context graph
缓存：**以实测证据跳过**——无瓶颈（均值低于基线）、无门禁收益，且按
「零回退门禁」原则不动已 100/100 的判定路径。context graph 与 witness
缓存已由 Patch 3/5 交付。

## §13.4 打包门禁逐项

| 门禁 | 结果 |
|---|---|
| zip 根目录直接包含 build.sh | ✓ |
| 提交完整源码，现场编译 solution | ✓ 解包 → build.sh → gate 100/100（/tmp/v14_zip_final 复验） |
| zip < 1MB | ✓ 842 KB |
| 不含 __pycache__ / .pyc / 官方 typechecker / 开发 benchmark / 未压缩 token 表 | ✓（见下） |
| context.bin 可由随包 context 重建 | ✓ 解包构建时由 context.json + tools/generate_context_table.py 重建（8012 B 相同） |
| stage manifest 与稳定模板逐文件 diff | ✓（见下） |
| 官方 ARM Docker 全链路复验 | 官网侧步骤（本机无法执行），交付前已完成本机全链路 |

清理执行（git 历史可恢复）：

- 删除 tools/ 14 个开发脚本（run_*/oracle/probe/矩阵生成/native_semantic
  driver 等；保留 build.sh 依赖的 generate_context_table.py 与
  generate_cl100k_table.py）；
- 删除 third_party/cangjie_typechecker（官方 typechecker，plan §13.4
  明令禁止随包；已通过 zip 模板验证 v12/v13 均未包含）；
- 删除 generated/cl100k_base.bin（1.4M 未压缩 token 表，build.sh 由
  assets/cl100k_base.bin.xz 现场解压）；
- 清理全部 __pycache__。

manifest diff vs 稳定模板（cangjie-checker_v12_F1_L_20260818.zip，
同样被接受的 109 文件布局）：

```text
+ cpp/call_frontier.cpp、cpp/call_frontier.h        （Patch 4 交付）
- tools/ 7 个开发脚本                                （plan Patch 7 删除）
- third_party/cangjie_typechecker/（21 文件）        （plan §13.4 禁止，模板亦无）
其余 99 文件逐文件一致
```

## §13.1 回归门禁（最终复验）

```text
工作树构建：  wrong 50/50 + wrong2 50/50
zip 解包构建： wrong 50/50 + wrong2 50/50   （两处独立复验）
dead_identifier 生产路径引用：0
trace/调试输出全部环境变量门控（CANGJIE_TRACE_FIRE / _WITNESS /
DEBUG_SEMANTIC），正式输出不依赖任何 env
```

## §13.2 信息增益统计（正式提交资格汇总）

| 项 | 要求 | 证据 |
|---|---|---|
| Context 非 F1 真实差异 | ≥ 5 | Patch 1：官方 context 单源化 canonical diff = 0 + 全成员矩阵（docs/v14_patch1_context_ir.md） |
| 新旧引擎有证据决策差异 | ≥ 20 | Patch 5：43 Alive（7 个有见证位点）+ 1 新提前 fire（Dead 证明，BFS 32 状态穷尽）；Patch 4：17 个 Dead candidate 全部带 reason |
| 不同 API/member 家族 | ≥ 10 | Patch 4 家族表：元数/方法参数/HashMap/infer 家族/lambda 集合/HOF/构造器/静态/索引/range |
| CallFrontier 形态 | ≥ 5 | overload 独立状态、symbolic 参数、逗号提交、`)` arity 检查、expected-return 记录、方法值 vs 调用、receiver 替换（Patch 4 §8.2 规则 1-8） |
| LambdaFrontier 非 twin-only 形态 | ≥ 2 | 闭 `}` 锚点 12 例 + `=>` 3 例 + 参数 1 例 + 外层关闭 4 例（Patch 6 表格） |

## 提交记录

- Patch 7 打包前置：删除开发脚本 + 未压缩 token 表 + pycache；
- Patch 7 打包：删除 third_party/cangjie_typechecker + 本文档；
- 交付物 zip 与 solution 二进制保持 untracked（沿 v6-v13 惯例）。

## 停止点

按主导请求：内部 patch 0-8 全部完成，zip 已打包并全链路复验
（解包 → 现场编译 → 100/100）。等待用户手动上传官网并回报结果。
