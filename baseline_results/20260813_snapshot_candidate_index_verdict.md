# DeclarationSnapshot 候选起点索引正式结论

结论：**PROVISIONAL（扩展验证后未升格）/ 已回退**。候选提交 `735a52e` 的正确性门禁全部通过，
但正式性能收益未达到项目合同的 `SUM >= 5%` 接受门槛。候选已由
`75e9702` 本地 revert，当前 accepted control 仍为 `68d780d`。本轮没有推送
远程仓库。

## 变更范围

- control：`68d780d54c25883b4e05c3f3562b315750b38af0`；
- candidate：`735a52e20671930f7e956401d39d5ca1c69d3ec9`；
- revert：`75e9702`；
- 生产差异仅在 `cpp/native_semantic.cpp`；
- 算法只构建通用的 `class/interface/func/main` 原始字节候选起点，
  然后用原有 8 族 regex 从该起点连续匹配；
- 不识别样例名、源码片段、token 序列、首错位置或 benchmark 身份；
- 不跳过注释或字符串，保留旧 regex 的原始字节行为。

## 正确性和可移植性

锁定环境为 `docker.educg.net/compiler_system_challenge/cjchecker:20260522`，
digest `sha256:980dd9f2ede4f0132e9c71c71c1d6553cafd5de7cf1977c2ffe97a5ab34b8c90`，
Linux AArch64，10 CPU，GCC 11.4.0。

- 官方 50 例精确首错：`50/50`；
- authoritative：`219/219`；
- 非规模综合语料：`364/364`；
- 相对 control 严格差分：728 次双协议、238 次安全前缀、26 次输入边界，
  transcript、首拒绝、退出码、stderr、异常和超时全部一致；
- 单元测试 `57/57`，native fragment `66 x 4`，context `7/7`，
  hidden fuzz `144 x 5`，官方/oracle/项目语料 `50/45/57`；
- 独立旧 regex shadow 的记录、Model、FunctionContext 和 CheckStatus 对比全过；
- ASan/UBSan + shadow 完整门禁全过，无 sanitizer 报告；
- 9 个 scale 诊断样例无新回退，仍只有既知的 4KB 标识符和 300 局部
  变量两例超时。

完整 gate 摘要的 SHA-256 为
`a9fd77c5a2e27974e243de670d35f7f1b3ab6258765b4cdd7c3ff6728efc3772`。

## 正式 A/B/A

所有阶段均为 fresh process/token 即时交互，seed `20260811`。正式 control 对每例
先取 `(A1 中位数 + A2 中位数) / 2`，再计算 50 例聚合指标。

### 初轮：1 次预热 + 9 次实测

| 指标 | Control | Candidate | 改善 |
|---|---:|---:|---:|
| SUM | 1534.476 ms | 1469.590 ms | 4.229% |
| MEDIAN | 31.611 ms | 30.362 ms | 3.951% |
| P95 | 39.005 ms | 35.793 ms | 8.235% |
| MAX | 42.075 ms | 40.185 ms | 4.491% |

- A1/A2 SUM 漂移：`0.478%`；
- A1/A2 MEDIAN 漂移：`1.407%`；
- `32 WIN / 0 LOSS`，无单例同时回退超过 2 ms 和 8%；
- 官方 harness：control `5491.981 ms`，candidate `5427.593 ms`，候选快 `1.172%`。

初轮 SUM 位于 2%-5%，因此严格升级为两轮完整 `1 + 21` A/B/A。

### 扩展第 1 轮：1 + 21

| 指标 | Control | Candidate | 改善 |
|---|---:|---:|---:|
| SUM | 1551.804 ms | 1481.171 ms | 4.552% |
| MEDIAN | 31.920 ms | 30.803 ms | 3.499% |
| P95 | 39.375 ms | 36.763 ms | 6.634% |
| MAX | 42.580 ms | 40.189 ms | 5.616% |

- SUM/MEDIAN 漂移：`1.858% / 1.007%`；
- `36 WIN / 0 LOSS`，无严重单例回退。

### 扩展第 2 轮：1 + 21

| 指标 | Control | Candidate | 改善 |
|---|---:|---:|---:|
| SUM | 1579.640 ms | 1504.180 ms | 4.777% |
| MEDIAN | 32.834 ms | 30.937 ms | 5.779% |
| P95 | 40.084 ms | 37.021 ms | 7.642% |
| MAX | 43.392 ms | 40.898 ms | 5.748% |

- SUM/MEDIAN 漂移：`0.427% / 0.636%`；
- `36 WIN / 0 LOSS`，无严重单例回退。

扩展轮官方 harness：control `5588.535 ms`，candidate `5518.128 ms`，候选快
`1.260%`。

## 判定

正确性、漂移、MEDIAN/P95、单例和 harness 均合格；但扩展后两轮 SUM 分别只改善
`4.552%` 和 `4.777%`，均未达到合同要求的 `>=5%`。依据“两轮都必须满足
正式接受条件”的条款，它仍是 **PROVISIONAL（扩展验证后未升格）**，
而不是 ACCEPTED。由于它不能成为下一个 control，按计划回退。

该改动不与后续微优化叠加，也不会改写门槛。
