# nominal 声明索引复用候选判定

## 结论

**ACCEPTED**。候选提交 `9fbc285` 成为下一阶段 control。

候选不改变 `CheckDeclaredTypes` 的正则模式、类型规则或诊断顺序。它在一次类型声明
检查内只收集一次 class/interface 声明、泛型参数和作用域边界，随后供各函数查询，
取消原实现对每个函数重新扫描整份源码的重复工作。shadow 构建仍对每个函数调用
原逐次正则扫描，并断言得到的 enclosing type parameters 集合完全相同。

实现不读取样例名、token 序列、首错位置、源码哈希或 benchmark/harness 身份。

## 正确性门禁

全部在官方 ARM64 镜像
`docker.educg.net/compiler_system_challenge/cjchecker:20260522` 中通过：

- 默认正式构建：37 个单元测试；
- native fragment differential：66/66 语义例 × 4 种分片；
- native context differential：7/7；
- 固定 seed `20260805` 隐藏语义 fuzz：144 例 × byte/random/line/cl100k/whole，0 失败；
- 官方公开样例精确首错：50/50；
- 官方语义语料：45/45；
- 项目语料：57/57；
- shadow 构建在全量语料与所有分片上无新索引/旧扫描结果分歧；
- ASan/UBSan + shadow：fragment 66/66 × 4、fuzz 144 × 5、官方精确首错
  50/50、官方语义 45/45、项目语料 57/57，均无 sanitizer 报告；
- 默认正式构建确认不包含 shadow 分歧字符串；
- 官方 `token_interaction_test.py` 端到端复核：control 50/50、candidate 50/50。

## 画像结果

画像覆盖同一组 251 个输入，调用次数保持不变（`declared_type_checks=4012`）：

| 指标 | control `1bf24ef` | candidate `9fbc285` | 变化 |
|---|---:|---:|---:|
| declared type 检查 | 335,377,707 ns | 154,838,853 ns | -53.832% |
| Analyze 总计 | 801,824,895 ns | 622,186,053 ns | -22.404% |
| semantic check 阶段 | 1,472,278,481 ns | 1,293,781,512 ns | -12.124% |

候选原始画像见 `profile_20260812_nominal_index_candidate.json`；control 画像为
`profile_20260812_linear_malformed_candidate.json`。

## 正式 A1 → B → A2

计时条件：同一容器、相同官方样例提交、每例 1 次预热 + 9 次实测、每次冷启动
新进程、逐 token 立即交互。control 为 `1bf24ef`，candidate 为 `9fbc285`。

| 指标 | A1 | candidate B | A2 | A1/A2 逐例均值 control | B 相对 control |
|---|---:|---:|---:|---:|---:|
| 50 例中位数之和 SUM | 1838.250 ms | 1699.616 ms | 1864.777 ms | 1851.514 ms | **-8.204%** |
| 跨例 MEDIAN | 37.931 ms | 35.074 ms | 38.346 ms | 38.138 ms | -8.035% |
| 跨例 P95 | 47.965 ms | 43.122 ms | 48.977 ms | 48.471 ms | -11.035% |
| 跨例 MAX | 52.903 ms | 47.918 ms | 53.751 ms | 53.327 ms | -10.143% |
| 首响应 SUM | — | 398.519 ms | — | 396.443 ms | +0.524% |

- A1/A2 SUM 漂移：1.433%，低于 3% 的无效阈值；
- 以 `max(1 ms, control × 3%)` 为噪声阈值：46 个显著胜例、0 个显著败例；
- 仅 3 个样例出现总耗时微小正回退，最差为 `+0.145 ms / +1.122%`，均在噪声内；
- “同时超过 2 ms 和 8%”的回退数为 0；
- 首响应 SUM 的 `+0.524%` 处于噪声范围，未换取或隐藏任何显著单例回退；
- 50 例的 1,350 次正式测量全部得到精确预期协议响应；
- 改善达到 5% 直接接受阈值，因此不触发 2%–5% 区间的 21 次双轮复测；
- 官方 harness 整轮补充墙钟：control 5863 ms、candidate 5717 ms。该值包含
  Python harness 启动开销，只用于端到端复核，不用于正式收益判定。

原始逐次数据保存在同名前缀的 A1/B/A2 JSON、CSV 和 Markdown 文件中。

## 验收解释

该优化同时满足 SUM 至少改善 5%、MEDIAN/P95 无回退、无单例超限回退、正确性
门禁全通过和 A1/A2 漂移有效。它只复用一次通用源码扫描的结果，未使用
`-march=native`、Apple CPU 参数、PGO 或任何平台专用路径。
