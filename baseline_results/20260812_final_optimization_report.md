# 正确率优先优化最终封板报告

## 最终结论

最终生产代码检查点为 `8db0fbf`，相对原始提交 `b40791c`：

- 官方公开样例精确首错保持 **50/50**；
- 同轮累计 A/B/A 的 SUM 从 `1913.215 ms` 降至 `1643.670 ms`，改善
  **14.089%**；
- MEDIAN/P95/MAX 分别改善 **13.516% / 16.689% / 16.143%**；
- A1/A2 SUM 漂移仅 **0.333%**；
- 46 个显著胜例、0 个显著败例，没有任何总耗时正回退样例；
- 全部优化均为通用算法/扫描复用，不含公开样例、token 序列、首错位置或源码片段特化；
- 构建目标为官方 Linux AArch64，未使用 `-march=native`、Apple CPU 参数或 PGO。

历史参考 `SUM=1571.046 ms` 只保留为旧环境绝对值；本报告的正式累计结论只使用
同一容器内本轮 A1/B/A2 对照。

## 最终正式累计 A1 → B → A2

环境：`docker.educg.net/compiler_system_challenge/cjchecker:20260522`，Linux AArch64。
每阶段均为 50 例、每例 1 次预热 + 9 次实测、每次启动新进程并逐 token 立即交互。

| 指标 | original A1 `b40791c` | final B `8db0fbf` | original A2 `b40791c` | A1/A2 逐例均值 control | B 相对 control |
|---|---:|---:|---:|---:|---:|
| SUM | 1910.028 ms | 1643.670 ms | 1916.401 ms | 1913.215 ms | **-14.089%** |
| MEDIAN | 39.133 ms | 34.005 ms | 39.506 ms | 39.319 ms | -13.516% |
| P95 | 50.115 ms | 42.101 ms | 50.955 ms | 50.535 ms | -16.689% |
| MAX | 55.825 ms | 46.844 ms | 55.899 ms | 55.862 ms | -16.143% |
| 首响应 SUM | — | 389.831 ms | — | 401.085 ms | -2.806% |

- A1/A2 SUM 漂移：0.333%，低于 3% 无效阈值；
- 以 `max(1 ms, control × 3%)` 为噪声阈值：46 WIN / 0 LOSS；
- 无总耗时正回退样例，因此超出 `2 ms + 8%` 双阈值的回退数为 0；
- 50 例 × 9 次 × 3 阶段，共 1350 次正式测量，全部得到精确预期响应；
- 官方 `token_interaction_test.py` 端到端复核：original 50/50、5763 ms；
  final 50/50、5485 ms（-4.824%，仅为补充墙钟，不混入核心指标）。

原始逐次数据保存在 `20260812_cumulative_*` 的 JSON、CSV 和 Markdown 文件中。

## 最终正确性封板

最终代码的干净 clone 在同一官方容器内通过：

- 仓库内单元测试：34/34；
- native fragment differential：66/66 语义例 × byte/random/cl100k/whole；
- native context differential：7/7；
- 固定 seed `20260805` 隐藏语义 fuzz：144 例 ×
  byte/random/line/cl100k/whole，0 失败；
- 官方公开样例精确首错：50/50；
- 官方语义语料：45/45；
- 项目语料：57/57；
- 官方 harness：50/50。

工作树中用户另外新增但未提交的 3 个测试也曾与候选一同运行，总计 37/37；这些文件
保持未暂存，未被本优化分支纳入提交。

两项正式接受候选均额外通过 ASan/UBSan、shadow differential、固定 fuzz 与官方
精确首错验证。正式默认构建不包含 profile 计时路径或 shadow 对照路径；二者分别只在
`CANGJIE_PROFILE_BUILD=1` 和 `CANGJIE_REGEX_SHADOW_BUILD=1` 时编译。

## 正式接受的生产优化

### 1. 线性 malformed declaration 扫描

- 代码提交：`f85f1a3`；结果提交：`1bf24ef`；
- 用一次通用线性扫描替换两次全源码 `std::regex_search`；
- 旧正则保留为 opt-in shadow，并在全部语料/分片上逐结果断言等价；
- 同轮 SUM 改善 5.358%，A1/A2 漂移 0.414%，45 WIN / 0 LOSS；
- 规则画像耗时 `189.903→2.611 ms`（-98.625%）。

详细报告：`20260812_linear_malformed_verdict.md`。

### 2. nominal 声明索引复用

- 代码提交：`9fbc285`；结果提交：`1de1a00`；
- 保留原正则和诊断顺序，在一次 declared-type 检查内只收集一次 nominal 声明，
  供各函数复用作用域/泛型参数查询；
- shadow 对每个函数同时运行旧的逐次全源码扫描并断言集合相同；
- 同轮 SUM 改善 8.204%，A1/A2 漂移 1.433%，46 WIN / 0 LOSS；
- declared-type 画像耗时 `335.378→154.839 ms`（-53.832%）。

详细报告：`20260812_nominal_index_verdict.md`。

## 已验证但未进入最终生产代码的候选

| 候选 | 判定 | 主要依据 |
|---|---|---|
| accepted token 容器改计数器 | NO PROVEN GAIN，已回退 | SUM 回退 0.458% |
| FunctionContext 去深拷贝 | NO PROVEN GAIN，已回退 | 复制量归零，但 SUM 回退 0.357% |
| 类型规范化复用/清理临时字符串 | NO PROVEN GAIN，已回退 | SUM 仅改善 0.320% |
| TokenTable 单缓冲区 | NO PROVEN GAIN，已回退 | SUM 仅改善 0.331% |
| 通用 `-flto` | REJECTED，已回退 | SUM 回退 2.116% |
| 每 token 直接 `write` | NO PROVEN GAIN，已回退 | SUM 仅改善 0.057% |
| 增量 lexer/source facts | NO PROVEN GAIN，已回退 | 扫描字节归零，但 SUM 回退 0.293% |
| commit-gated model generation | REJECTED，已回退 | `err_interface_sig_mismatch` 首错 token 32→33 |
| stable-event model generation | REJECTED，已回退 | 同样发生首错 token 32→33 |
| CollectNominals 必要关键字 guard | PROVISIONAL，已回退 | 21 次双轮 SUM 改善 2.179% / 2.723%，均未达 5% |

每个候选均独立提交、独立验收；未接受候选未与后续生产优化叠加。详细原始数据和
判定报告均保存在 `baseline_results/`。

## 停止边界与后续建议

本轮已获得同轮累计 14.089% 的稳定收益。剩余主要热点是 model/context 重建、语法
匹配和初始化；继续推进需要持久增量声明索引、细粒度 generation 或 TypeId 化，都会
扩大作用域/泛型/首错时序风险。鉴于两次 model dirty-generation 已真实导致首错偏移，
本轮按“正确率优先”停止在已证明等价的扫描优化，不直接重写完整 Pratt/LR 状态机，
也不把未达 5% 的 guard 合并进生产代码。

后续若继续优化，应以 `8db0fbf` 的生产代码作为 control，仍执行完整正确性门禁和
同轮 A/B/A；先扩展 declaration-index shadow 覆盖，再考虑持久增量索引或 TypeId。
