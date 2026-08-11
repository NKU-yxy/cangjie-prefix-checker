# 线性 malformed declaration 扫描候选判定

## 结论

**ACCEPTED**。候选提交 `f85f1a3` 成为下一阶段 control。

候选将 `CheckMalformedGenericConstruct` 的两次全源码 `std::regex_search`
替换为单次通用线性扫描。实现仅匹配原规则描述的词法结构，不读取样例名、token
序列、首错位置、源码哈希或 benchmark/harness 身份。旧正则实现保留为仅在
`CANGJIE_REGEX_SHADOW_BUILD=1` 时编译的 shadow path；正式构建不包含 shadow
断言与旧正则检查。

## 正确性门禁

全部在官方 ARM64 镜像
`docker.educg.net/compiler_system_challenge/cjchecker:20260522` 中通过：

- 默认正式构建：37 个单元测试通过；
- native fragment differential：66/66 语义例 × 4 种分片；
- native context differential：7/7；
- 固定 seed `20260805` 隐藏语义 fuzz：144 例 × byte/random/line/cl100k/whole，0 失败；
- 官方公开样例精确首错：50/50；
- 官方语义语料：45/45；
- 项目语料：57/57；
- shadow 构建在上述全量语料与所有分片上无新旧结果分歧；
- ASan/UBSan + shadow：fragment 66/66 × 4、fuzz 144 × 5、官方精确首错
  50/50、官方语义 45/45、项目语料 57/57，均无 sanitizer 报告；
- 官方 `token_interaction_test.py` 端到端复核：control 50/50、candidate 50/50。

## 画像结果

画像覆盖同一组 251 个输入，调用次数保持不变（`malformed_generic_checks=7025`）：

| 指标 | control `eb0a144` | candidate `f85f1a3` | 变化 |
|---|---:|---:|---:|
| malformed generic 检查 | 189,902,731 ns | 2,611,408 ns | -98.625% |
| Analyze 总计 | 985,944,558 ns | 801,824,895 ns | -18.674% |
| semantic check 阶段 | 1,654,570,062 ns | 1,472,278,481 ns | -11.017% |

候选原始画像见 `profile_20260812_linear_malformed_candidate.json`；control 画像为
`profile_20260812_rule_timing.json`。

## 正式 A1 → B → A2

计时条件：同一容器、相同官方样例提交、每例 1 次预热 + 9 次实测、每次冷启动
新进程、逐 token 立即交互。control 为 `eb0a144`，candidate 为 `f85f1a3`。

| 指标 | A1 | candidate B | A2 | A1/A2 逐例均值 control | B 相对 control |
|---|---:|---:|---:|---:|---:|
| 50 例中位数之和 SUM | 1942.761 ms | 1842.489 ms | 1950.817 ms | 1946.789 ms | **-5.358%** |
| 跨例 MEDIAN | 39.960 ms | 37.973 ms | 40.002 ms | 39.974 ms | -5.006% |
| 跨例 P95 | 51.868 ms | 48.952 ms | 51.878 ms | 51.873 ms | -5.631% |
| 跨例 MAX | 56.908 ms | 53.004 ms | 58.984 ms | 57.946 ms | -8.528% |
| 首响应 SUM | — | 395.646 ms | — | 405.552 ms | -2.442% |

- A1/A2 SUM 漂移：0.414%，低于 3% 的无效阈值；
- 以 `max(1 ms, control × 3%)` 为噪声阈值：45 个显著胜例、0 个显著败例；
- 没有任何正回退样例，因此“同时超过 2 ms 和 8%”的回退数为 0；
- 50 例的 1,350 次正式测量全部得到精确预期协议响应；
- 改善达到 5% 直接接受阈值，因此不触发 2%–5% 区间的 21 次双轮复测；
- 官方 harness 整轮补充墙钟：control 5891 ms、candidate 5817 ms。该值包含
  Python harness 启动开销，只用于端到端复核，不用于正式收益判定。

原始逐次数据保存在同名前缀的 A1/B/A2 JSON、CSV 和 Markdown 文件中。

## 验收解释

该优化同时满足 SUM 至少改善 5%、MEDIAN/P95 无显著回退、无单例超限回退、
正确性门禁全通过和 A1/A2 漂移有效。它是平台无关的 ASCII/`string_view` 线性扫描，
未启用 `-march=native`、Apple CPU 参数、PGO 或任何宿主机专用路径。
