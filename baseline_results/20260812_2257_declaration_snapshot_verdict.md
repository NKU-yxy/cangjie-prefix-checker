# DeclarationSnapshot 候选 C 正式结论

日期：2026-08-12

Control：`f5969646a6bd7cd8a2a66d7e004d92837320d1b9`

Candidate：`58f03c760a1a57cf4bc7a875ea8b61b10edd5870`

结论：**ACCEPTED，保留为下一轮 control**

## 候选内容与语义边界

候选在原有 `model_dirty` 时刻建立 generation 级声明快照，复用严格 nominal、宽松
class 以及三种保持独立的函数头扫描结果。记录使用自有字符串和字节 offset，不保存
可能随 `source_` 扩容失效的指针或 `string_view`。本地变量、lambda、for、字段、方法、
constructor body、类型兼容规则、dirty 时机和各检查顺序均未修改。

生产实现没有样例名、公开源码、token 序列、首错位置或 benchmark 身份分支；输入输出
协议、`context.json` 和两份 grammar 均保持不变。

## 正确性门禁

正式性能计时前，候选在锁定的 Linux AArch64 镜像中通过：

- 官方公开样例精确首错 `50/50`；
- 单元测试 `40/40`；
- native fragment differential：`66` 例 × `4` 种分片；
- native context differential：`7/7`；
- 新增声明边界门禁覆盖 `13` 例 × whole/byte/random/line，共 `52` 条路径，包含在
  `40/40` 单元测试中；
- seed `20260805` hidden fuzz：`144` 例 × byte/random/line/cl100k/whole，
  `0` 失败；
- 官方 oracle 语料 `45/45`，项目语料 `57/57`；
- 综合语料 `113/113`、`96` 次 oracle、双协议共 `226` 次运行；
- 独立旧 regex shadow 路径通过相同的关键前缀、fuzz、differential 和综合语料；
- ASan/UBSan 全进程通过官方/项目 differential、综合语料和 hidden fuzz，未报告
  sanitizer/runtime error。

hidden-fuzz 产物中的 `legacy_prefix_disagreements=190` 是 native checker 与旧 Python
checker 的既有诊断统计，不是 DeclarationSnapshot 与独立旧 regex shadow 的失败；
本候选的 `failures=0`，任何声明 shadow 分歧都会直接使门禁非零退出。

候选不引入线程或共享同步，因此本候选不要求 TSan、单核及 1000 次并发冷启动附加
门禁。显式诊断编译出现的 3 条 range-loop warning 均来自旧提交 `d711313f`，候选没有
新增 warning。诊断结束后已重新构建生产二进制，并确认其中不含 shadow 分歧字符串。

完整摘要见
[`20260812_2257_declaration_snapshot_gate_summary.json`](20260812_2257_declaration_snapshot_gate_summary.json)。

## 正式 A/B/A

三阶段位于同一个官方镜像生命周期，每阶段均为 `1` 次预热 + `9` 次实测；每个 trial
启动全新进程并逐 token 立即交互。正式 control 先对每个样例取 A1/A2 中位数的平均值，
再计算全局指标。

| 指标 | A1 | 正式 control | Candidate | A2 | 改善 |
|---|---:|---:|---:|---:|---:|
| SUM | 1637.824 ms | 1646.111 ms | 1511.386 ms | 1654.397 ms | **8.184%** |
| MEDIAN | 33.926 ms | 34.011 ms | 30.966 ms | 34.020 ms | **8.954%** |
| P95 | 42.115 ms | 42.054 ms | 38.076 ms | 41.993 ms | **9.459%** |
| MAX | 45.959 ms | 46.538 ms | 41.023 ms | 47.116 ms | **11.850%** |

- A1/A2 SUM 漂移：`1.007%`；MEDIAN 指标漂移：`0.277%`；逐例相对漂移中位数：
  `0.369%`，全部低于 `3%`，且最大门禁漂移低于 `2%`；
- 按 `max(1 ms, 3% × control_i)` 噪声阈值统计：`46 WIN / 0 LOSS`；
- 无单例同时回退超过 `2 ms` 和 `8%`；最大绝对回退仅
  `err_interface_not_implemented +0.0665 ms / +0.478%`；
- 三阶段全部 `50/50`，所有 `1350` 个正式 measured trial 均通过；
- first-response SUM 改善 `5.396%`，detection SUM 改善 `8.592%`；
- 官方 harness：control `5648.604 ms`，candidate `5544.868 ms`，候选改善
  `1.836%`，双方均 `50/50`。

候选同时满足 `SUM ≥ 5%`、MEDIAN/P95/单例/harness 和漂移门槛，因此直接
`ACCEPTED`，无需进入 21 次双轮扩展。

## 环境与可迁移性

- 镜像：`docker.educg.net/compiler_system_challenge/cjchecker:20260522`；
- digest：`sha256:980dd9f2ede4f0132e9c71c71c1d6553cafd5de7cf1977c2ffe97a5ab34b8c90`；
- 环境：Linux AArch64，10 CPU，MemTotal `8126480 KiB`；
- 编译器：GCC `11.4.0`；正式参数为通用
  `-O3 -DNDEBUG -Wall -Wextra -pedantic -pthread -std=c++17`，无 Apple 或宿主 CPU 参数；
- 官方样例提交：`88336c400e7a4a671424e3e6c46c0866c8c0af93`；
- registry SHA-256：`2425e64184d69dd392f6cdec52dc20d42d0977cbe84be744a0ffbd1dfad374f2`；
- control/candidate 的 `build.sh`、context 和 grammar 哈希完全相同。
- control `solution` SHA-256：
  `52747c12de6129cc132d2e145cf05a3bafeac427cdc622a7a42009217ade5fbd`；
  candidate `solution` SHA-256：
  `0b380688ab8a5fb850437f594a1154d2738059d07431459433f17a5e6b9e4bd2`。

两个 checkout 在构建前均为 clean；构建后仅受跟踪的 `solution` 被生产 ELF 替换。官方
样例 checkout 有一个无关的未跟踪 `.DS_Store`，官方提交、registry 哈希和全部输入文件
仍按锁定值验证。

本轮 `build.sh` SHA-256 为
`f3232ef08d4fde32c0f9670e8d658234d7a96ba1411c0ad676d96ca0626f85e6`，与条约最初
锁定的初始提交 hash 不同，但本轮 A/B 两侧完全一致，因此这是以 `f596964` 为 control
的新同轮结论，未与初始 baseline 的绝对值直接相减。control 首次构建还承担容器内依赖
安装，构建耗时不参与运行性能指标。

## 类型查询缓存停止条件

接受候选 C 后，又在同一 AArch64 镜像中对官方 50、项目 57、固定 fuzz 144 和综合
113，共 `364` 例运行画像。官方 50 例内 `Compatible` 为 `3786` 次调用、`607` 个
generation 唯一键，重复率 `83.967%`，通过了 `60%` 重复率门槛；但其 inclusive 耗时
仅 `0.869 ms`。即使把所有已画像类型 helper 的 inclusive 时间相加作为刻意放大的
理论上限，也只有 `20.873 ms`，占正式 control SUM 的 `1.268%`（占 candidate SUM 的
`1.381%`），远低于进入候选所需的 `7% / 115.228 ms`。而这些 inclusive 计时本身
还有重叠，实际可消除上限只会更低。

因此严格按预定条件停止，本轮**不实现类型查询缓存**，也不把它与已接受候选叠加。
计算见
[`20260812_2257_declaration_snapshot_type_cache_threshold.json`](20260812_2257_declaration_snapshot_type_cache_threshold.json)。

## 结果文件

- 三阶段完整原始 trial：`20260812_2257_declaration_snapshot_{f596964_A1,58f03c7_B,f596964_A2}.{json,csv,md}`；
- 汇总判定：
  [`20260812_2257_declaration_snapshot_initial_verdict.json`](20260812_2257_declaration_snapshot_initial_verdict.json)；
- 官方 harness：
  [`20260812_2257_declaration_snapshot_official_harness.json`](20260812_2257_declaration_snapshot_official_harness.json)；
- 环境：`20260812_2257_declaration_snapshot_environment_{host,pre-build,post-build}.json`；
- AArch64 364 例画像：
  [`20260812_2257_declaration_snapshot_arm64_profile.json`](20260812_2257_declaration_snapshot_arm64_profile.json)。

候选 `58f03c7` 保留在本地 Git，成为后续独立候选的 control；本轮不推送远程仓库。
