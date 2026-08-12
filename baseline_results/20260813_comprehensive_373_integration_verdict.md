# 373 例综合语料分层接入核验

日期：2026-08-13
状态：**官方 Linux AArch64 最终复跑完成；证据分层与原始结果均已锁定。**

## 结论

官方公开 50 例精确首错是最高优先级、不可豁免的硬门禁。新增 373 例不能作为一个
未经区分的 `373/373` 硬门禁，而应按独立证据分为：

| 层级 | 数量 | 门禁效力 |
|---|---:|---|
| `authoritative` | 219 | `oracle=true` 且非规模例；标签必须全部通过 |
| `diagnostic_spec_pending` | 145 | 标签尚缺独立赛事规范/oracle 证明；差异只作诊断 |
| `diagnostic_scale` | 9 | 规模、超时和非线性增长诊断；不作正确性硬门禁 |

最终 `oracle-backed` 运行的硬门禁摘要为 `371/373`，其中 2 例是 authoritative
失败；若把全部诊断标签也按 `all` 策略计为失败，原始标签匹配仍为 `329/373`。按证据
层级解释为：

- authoritative `217/219`：存在 2 个有独立 oracle 依据的明确 false reject；
- diagnostic_spec_pending：145 例中有 40 个 manifest 标签差异；
- diagnostic_scale：9 例中有 2 个 30 秒超时。

因此，恢复性能优化前必须修复两个 authoritative 缺陷并建立 `219/219` control；不要求
为 40 个待规范确认差异或两个规模超时修改生产语义以凑成 `373/373`。未来性能候选还
必须对全部 364 个非规模样例与当前 control 做严格逐 token reference diff。

## 测试对象与环境

- 仓库锚点：`3d745b641a7f1c60629eef43c173ed483a9b9982`
- 生产逻辑：`58f03c760a1a57cf4bc7a875ea8b61b10edd5870`
- 最终正式 AArch64 `solution` SHA-256：
  `0b380688ab8a5fb850437f594a1154d2738059d07431459433f17a5e6b9e4bd2`
- 镜像：`docker.educg.net/compiler_system_challenge/cjchecker:20260522`
- 镜像 digest：
  `sha256:980dd9f2ede4f0132e9c71c71c1d6553cafd5de7cf1977c2ffe97a5ab34b8c90`
- 系统：Linux AArch64；GCC `11.4.0`；Python `3.10.12`；tiktoken `0.13.0`
- 测试在隔离副本中构建和执行；未修改 `cpp/`、`build.sh`、`context.json`、grammar
  或生产入口。

## 语料锁

- schema：`3`
- 373 例：214 个完整合法、120 个完整错误、39 个可补全前缀
- 30 个测试族；305/305 个声明覆盖标签
- manifest SHA-256：`e0af56059f58f8f5d99fc9c1d243c75ed9df9670f2057b20421292dc48782496`
- 路径与源码聚合 SHA-256：`764af01cd910c341662a84bcab497cfdcf003150c434684a4d0838d80fc3967d`
- generator SHA-256：`3ba41564238358e487e72cf40678aef8606921a26da14b30a2ba4ed6ddc51c4a`
- runner SHA-256：`d04f1df184b095996503f004598b6b99d42d414f94a410710e81ff8ac125b55e`
- ownership marker SHA-256：`87b9784c22996a9cb5f00158199d4e4efabe00c855dfa60b085eba15209606c5`
- 最终 AArch64 JSON 结果 SHA-256：
  `0260fef5716a12cc90e1803110ea818e1561142857b7ef4be3ab1595621e7197`

每例源码、安全前缀和依赖哈希继续由 schema v3 锁定。不得通过删例、修改源码、放宽
安全前缀或按当前实现改写标签来消除差异。证据层级改变也必须有新的独立规范/oracle
依据，并进入新的 baseline 系列。

## 为什么必须分层

仓库内 vendored typechecker 来源于竞赛配套公开仓库；其 README 明确将 Lark checker
称为 subset typechecker。生产 `cangjie.gbnf` 则包含团队为扩大覆盖而加入的语法。
生产 grammar 能确认样例与当前 grammar 一致，但不能反过来独立证明这些扩展就是赛事
服务端规范。

因此采用以下机械分类：

- 非 `scale_stress` 且 `oracle=true`：`authoritative`，共 219 例；
- 非 `scale_stress` 且 `oracle=false`：`diagnostic_spec_pending`，共 145 例；
- 所有 `scale_stress`：`diagnostic_scale`，共 9 例，无论其 oracle 标记为何。

vendored oracle 共支持 227 个完整程序，其中 8 个属于规模族，所以只留下 219 个非规模
authoritative 标签。`oracle_skip_reason` 继续用于解释未送入 oracle 的原因，但不是把
该标签自动提升成赛事规范的凭证。

## 最终 AArch64 运行

- 确定性生成一致性：373/373
- 单元测试：55/55
- 生产 grammar 一致性：364/364；9 个规模例跳过重复字符级扫描
- vendored reference-derived 完整程序 oracle：227/227
- 原有门禁：官方精确首错 50/50、原 oracle 语料 45/45、项目语料 57/57
- 双协议完整源码运行：746 次
- 独立安全前缀运行：240 次
- 协议输入边界运行：26 次
- 基础设施失败：0
- `oracle-backed` 摘要：371 个样例未触发硬失败，2 个 authoritative 样例失败；
  另有 42 个完整保留的 diagnostic disagreement

这些数字中的 grammar `364/364` 只是生产一致性信号，不把 145 个 spec-pending 标签
变成 authoritative。

### Authoritative：217/219

两个明确 false reject 是：

- `lambda-block-body-and-iife`
- `postfix-member-call-index-chain`

两例均由未经过项目语法扩展的竞赛配套 subset parser/typechecker 完整接受，且 manifest
为 `oracle=true`。当前实现提前拒绝属于有独立依据的正确性缺陷，必须先修复。

### Diagnostic spec-pending：40 个标签差异

145 个 spec-pending 样例中，105 个与 manifest 标签一致，以下 40 个存在差异。这些差异
必须保留和报告，但当前不能单独否决性能候选。

28 个完整合法标签被当前实现提前拒绝：

`all-numeric-compound-assignments`, `array-list-static-of`, `array-suffix-type`,
`do-while`, `dotted-nominal-type`, `float-exponent-variants`,
`match-case-block-body`, `match-literal-identifier-wildcard`, `nothing-return-type`,
`nullable-type-and-postfix-unwrap`, `operator-pipelines`, `operator-shift-left`,
`operator-shift-right`, `optional-semicolon-matrix`, `primitive-float16-f16`,
`primitive-float32-f32`, `primitive-float64-f64`, `primitive-intnative`,
`primitive-rune`, `rune-escaped`, `string-constructor-overloads`, `super-member-call`,
`throw-statement`, `top-level-variable-declarations`, `try-catch`, `try-finally`,
`try-untyped-catch-finally`, `try-without-handler`。

6 个 manifest 标为可补全的前缀被当前实现拒绝：

`partial-do-while`, `partial-float-suffix`, `partial-match-case`, `partial-rune`,
`partial-shift`, `partial-try-catch`。

4 个 syntax reject 样例在 manifest 声明的安全前缀内就被拒绝：

`do-missing-while`, `malformed-rune`, `match-missing-arrow`,
`try-malformed-catch`。

2 个 manifest 标为语义错误的样例未被当前实现拒绝：

`duplicate-local-declaration`, `immutable-field-assignment-outside-constructor`。

其中 `duplicate-local-declaration` 被竞赛配套 subset oracle 接受，且其 typing rules 允许
同一 binding chain 中较晚声明遮蔽较早声明；`malformed-rune` 使用的 `r'…'` 也不属于
配套 subset grammar。这说明把全部 40 项直接当赛事硬规范会产生实质误导，而不是单纯
“更严格更安全”。

### Diagnostic scale：2 个超时

以下两个合法规模样例在默认和 competition 两种协议下均超过单进程 30 秒：

- `four-kilobyte-identifier`
- `three-hundred-local-declarations`

两例的完整程序标签有 oracle 支持，但 30 秒阈值和合成输入规模没有被证明是官方输入
约束，因此归入 `diagnostic_scale`。它们是重要的非线性性能信号，但不阻止正确率已满足
的通用优化，也不进入官方 50 例性能统计。

## 后续正式门禁

性能候选必须依次满足：

1. 官方公开 50 例精确首错 `50/50`；
2. 综合语料 authoritative `219/219`；
3. 全部 364 个非规模样例相对最近一个已接受 control 的逐 token transcript、首次拒绝
   token/byte、退出码、stderr 和进程异常严格一致；
4. 145 个 spec-pending 标签差异完整写入 diagnostic 报告；
5. 9 个 scale 样例单独运行并报告完成、超时和增长情况；
6. 全部原有单元、差分、fuzz、sanitizer 和并发门禁继续通过。

推荐的非规模候选/control 命令为：

```bash
python3 tools/run_comprehensive_cases.py \
  --solution /candidate/solution \
  --reference-solution /control/solution \
  --check-competition-output \
  --expectation-policy oracle-backed \
  --skip-family scale_stress \
  --timeout 30 \
  --json /tmp/comprehensive-reference-diff.json
```

正确性修复允许有意改变旧 control 行为，但必须与性能修改分离，达到 authoritative
`219/219` 后先建立新的 control。性能候选不得改变任何一个非规模样例的当前 control
transcript。综合语料不参与官方 50 例 `SUM`、`MEDIAN`、`P95`、`MAX`、`WIN` 或
`LOSS`。

## 证据文件

以下均为最终分层 runner 在官方 AArch64 镜像中的归档结果：

- [`20260813_comprehensive_373_schema3_arm64.json`](20260813_comprehensive_373_schema3_arm64.json)：
  逐例 observation、首拒位置、响应哈希、硬失败与诊断差异；
- [`20260813_comprehensive_373_schema3_arm64.log`](20260813_comprehensive_373_schema3_arm64.log)：
  最终 runner 的人类可读输出；
- [`20260813_comprehensive_373_environment.txt`](20260813_comprehensive_373_environment.txt)：
  AArch64 环境、源码状态、工具与二进制信息；
- [`20260813_comprehensive_373_unittest.log`](20260813_comprehensive_373_unittest.log)：
  官方镜像单元测试；
- [`20260813_comprehensive_373_existing_differential.log`](20260813_comprehensive_373_existing_differential.log)：
  原有 50/45/57 差分结果；
- [`20260813_comprehensive_373_solution_elf.txt`](20260813_comprehensive_373_solution_elf.txt)：
  生产二进制 AArch64 ELF 头；
- [`20260813_comprehensive_373_generator_check.log`](20260813_comprehensive_373_generator_check.log)：
  373 例确定性生成检查。
