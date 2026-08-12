# 仓颉前缀语义检查器本地优化测试条约

版本：1.3
生效日期：2026-08-13
适用项目：T2026100552010674 / 圆周运动

## 1. 目的与效力

本条约用于判断一次代码修改是否构成真实、可复现、可迁移到赛事 ARM64 环境的
性能优化。任何未满足本条约的结果，不得表述为“性能提升”“优化有效”或替换正式
baseline。

本文使用以下强制等级：

- **必须**：违反即判定测试无效；
- **应当**：原则上执行，不能执行时必须在报告中解释；
- **可以**：辅助诊断，不作为强制验收条件。

## 2. 锁定的初始 Baseline

### 2.1 代码与样例

| 项目 | 锁定值 |
|---|---|
| 项目源码提交 | `b40791c7104be19196f5c045c17a297103ae1267` |
| 官方公开样例提交 | `88336c400e7a4a671424e3e6c46c0866c8c0af93` |
| 官方首错位置文件 SHA-256 | `2425e64184d69dd392f6cdec52dc20d42d0977cbe84be744a0ffbd1dfad374f2` |
| `build.sh` SHA-256 | `0a67862dd64aa2a26812d9caf3f4627f30f828ec6355036df857a187781b4912` |
| `context.json` SHA-256 | `8058e383390f444f56ee4ac0008493c44c8e32fa632d18ed48f998dc36623348` |
| `grammar/cangjie.gbnf` SHA-256 | `6131041ed52120b65ee75440c97704dfe91d1a0fda0aaf99b3e1c75e3054f989` |
| `grammar/cangjie_token.gbnf` SHA-256 | `cbe033bea0b88c4d042e258cb4a9b79dfe0912072dc6b5468f742c5d57d6dae0` |

测试样例、首错位置、context 或 grammar 发生变化时，结果必须进入新的 baseline
系列，不能继续与本表结果直接比较。

### 2.2 官方镜像与本机资源

| 项目 | 锁定值 |
|---|---|
| Docker 镜像 | `docker.educg.net/compiler_system_challenge/cjchecker:20260522` |
| 镜像 digest | `sha256:980dd9f2ede4f0132e9c71c71c1d6553cafd5de7cf1977c2ffe97a5ab34b8c90` |
| 容器架构 | Linux AArch64 |
| 当前 Docker CPU 配额 | 10 CPU |
| 当前容器可见内存 | 8,126,480 KiB |

Docker CPU、内存、镜像 digest 或宿主机发生变化时，历史绝对耗时只能作为参考。
正式对比必须在新环境中同时重跑对照版本和候选版本。

### 2.3 初始性能值

| 指标 | 初始值 |
|---|---:|
| 功能正确性 | 50/50 |
| 每例预热次数 | 1 |
| 每例实测次数 | 9 |
| 50 个样例总耗时中位数的中位数 | 31.991 ms |
| 50 个样例总耗时中位数的 P95 | 41.963 ms |
| 最慢样例中位数 | `err_assign_let` / 45.946 ms |
| 本地官方 harness 单轮中位数，仅供参考 | 118.0 ms |
| 历史官网中位数，仅供参考 | 276.5 ms |

初始完整报告位于
[`baseline_results/official_50_baseline_20260811_arm64.json`](baseline_results/official_50_baseline_20260811_arm64.json)。

## 3. 必须区分的三种计时口径

### 3.1 核心进程口径：主要优化指标

每次 trial 启动一个全新的 `solution` 进程，逐 token 写入 stdin 并逐行读取 stdout。
样例文本读取、tiktoken 导入和 token 编码在 trial 计时开始前完成。

必须记录：

- `first_response_ms`：创建进程到收到第一个 token 回复；
- `detection_ms`：创建进程到收到官方精确首错 token 回复；
- `process_total_ms`：创建进程到 `solution` 正常退出。

正式性能结论以 `process_total_ms` 为主，`detection_ms` 用于区分进程退出开销，
`first_response_ms` 用于分析启动成本。

### 3.2 本地官方 harness 口径：端到端复核指标

每个样例单独启动官方 `token_interaction_test.py`，包含 Python 解释器、tiktoken、
文件读取、编码、`solution` 子进程和 IPC。该口径应当在候选优化正式验收时至少运行
一轮，但不得和核心进程口径混合计算提升比例。

### 3.3 历史官网口径：外部参考指标

历史官网数字包含不可完全复现的平台固定开销和硬件差异。经验拟合关系为：

```text
官网耗时(ms) ≈ 194.3 + 2.514 × 本地核心进程耗时(ms)
```

该公式只用于估算，不得作为候选优化的正式验收指标，也不得宣称为未来官网实测值。

## 4. 功能正确性是硬门槛

官方公开 50 例精确首错是本项目最高优先级、不可豁免的正确性门禁。综合语料、
vendored oracle 或项目 grammar 均不能覆盖、放宽或替代官方 50 例结论。

任何性能数字只有在以下条件全部满足后才有效：

1. 官方公开 50 例全部通过；
2. 每个样例在官方 `first_error_token_index` 精确首次报错；
3. 每个首错 token 之前不得提前报错；
4. stdout 每轮只能输出协议要求的 `0` 或 `1`；
5. 进程退出码为 0，stderr 不包含未处理异常或动态库错误；
6. 所有预热和实测 trial 均通过，不能只统计成功 trial；
7. 不得修改、跳过、缩短或重新排序单个样例的 token 序列来获得更快结果。

正式接收优化前，还必须在同一官方容器内通过：

```bash
python3 -m unittest discover -s tests
python3 benchmark/native_fragment_differential.py
python3 benchmark/native_context_differential.py
python3 benchmark/hidden_semantic_fuzz.py \
  --seed 20260805 \
  --cases-per-family 12 \
  --solution ./solution
python3 benchmark/differential_check.py \
  --official-root /official \
  --solution ./solution \
  --mode fast
python3 tools/generate_comprehensive_cases.py --check
python3 tools/run_comprehensive_cases.py \
  --solution ./solution \
  --check-competition-output \
  --expectation-policy oracle-backed \
  --skip-family scale_stress \
  --timeout 30 \
  --json baseline_results/comprehensive_gate.json
python3 tools/run_comprehensive_cases.py \
  --solution ./solution \
  --check-competition-output \
  --expectation-policy oracle-backed \
  --family scale_stress \
  --timeout 30 \
  --json baseline_results/comprehensive_scale_diagnostic.json
```

综合语料门禁必须使用版本库锁定的
[`test_cases/comprehensive/manifest.json`](test_cases/comprehensive/manifest.json)，不得在候选
版本上重新生成或筛选样例。当前门禁的精确期望为：

- manifest schema 为 `3`，共 `373` 例：`214` 个完整合法程序、`120` 个已提交
  错误和 `39` 个可补全前缀；
- `305/305` 个声明覆盖目标齐全。该数字表示机器可检查的覆盖标签，不等于 305 项
  相互独立的语义证明；
- 按独立证据分为三个互斥层级：`authoritative=219`、
  `diagnostic_spec_pending=145`、`diagnostic_scale=9`；三者合计 `373`；
- `authoritative` 仅包含 `oracle=true` 且不属于 `scale_stress` 的样例。性能候选必须
  `219/219` 全部符合 manifest 标签；
- `diagnostic_spec_pending` 是非规模、但尚无独立赛事规范或 oracle 证明的标签。生产
  grammar 接受只是一致性检查，不能证明这些标签就是赛事服务端规范；标签差异必须
  完整报告，但不得单独否决候选；
- `diagnostic_scale` 的 9 例只用于发现非线性耗时、卡死和资源问题；超时或标签差异必须
  报告，但不进入正确性硬门禁或官方性能统计；
- 生产 grammar 一致性检查覆盖全部 `364` 个非规模样例。`9` 个 `scale_stress` 例按
  设计跳过第二遍字符级 grammar 扫描；
- vendored reference-derived 完整程序 oracle 共复核 `227` 例，其中 `219` 个非规模例
  形成 authoritative 层，另外 8 个 oracle-backed 规模例仍归入 diagnostic_scale。
  `oracle=false` 必须保留非空机器可读原因，候选不得通过新增豁免消除差异；
- 完整 373 例诊断运行会在默认协议和 `--competition-output` 下各运行一次，
  共 `746` 次完整源码进程运行；正式非规模门禁只运行 364 例，对应 `728` 次；
- 每个 reject 例的原始字节安全前缀必须被独立截取、重新以 `cl100k_base` 编码，并在
  两种协议下由全新进程执行；全量诊断为 `240` 次，正式非规模门禁为 `238` 次；
- `13` 种协议输入边界在两种协议下运行，共 `26` 次；
- 单个 solution 的全量 373 例诊断共启动 `746 + 240 + 26 = 1012` 个协议进程；
  正式非规模门禁共启动 `728 + 238 + 26 = 992` 个。带 control 的 reference diff
  对 candidate 与 control 各运行一遍，合计 `1984` 个；
- 两种协议的逐 token transcript 必须严格逐位翻转，首次拒绝 token 和字节位置必须
  完全相同。正式非规模门禁的协议/infrastructure 错误不可豁免；manifest 标签
  差异则按上述 evidence tier 判定。`diagnostic_scale` 中的单例超时、异常或标签差异
  必须报告，但不单独否决候选；

当前锁定输入摘要为：

| 项目 | SHA-256 |
|---|---|
| manifest | `e0af56059f58f8f5d99fc9c1d243c75ed9df9670f2057b20421292dc48782496` |
| 373 例路径与源码聚合 | `764af01cd910c341662a84bcab497cfdcf003150c434684a4d0838d80fc3967d` |
| generator | `3ba41564238358e487e72cf40678aef8606921a26da14b30a2ba4ed6ddc51c4a` |
| runner | `d04f1df184b095996503f004598b6b99d42d414f94a410710e81ff8ac125b55e` |

正式性能候选还必须把最近一个 authoritative `219/219` 的已接受 control 作为
`--reference-solution`，并对全部 `364` 个非规模样例执行严格逐 token reference diff。
候选与 control 的完整 stdout transcript、首次拒绝 token/byte、退出码、stderr 和
超时/启动异常必须完全一致。这里的 reference diff 对 145 个 spec-pending 样例同样
严格：它不把其 manifest 标签升级为赛事规范，但能防止性能修改悄悄改变既有行为。

规模族单独保留 diagnostic 结果，不纳入这项 reference 等价门禁。若任务是修复已知
authoritative 正确性缺陷，允许行为相对旧 control 发生变化，但必须独立提交、达到
`219/219` 后建立新 control，不能与性能优化混在同一候选中。

正式非规模门禁固定允许且要求使用
`--skip-family scale_stress`，与单独的 `--family scale_stress` 诊断运行配对。
禁止用其他 `--skip-family`、`--family`、`--name`、`--skip-grammar`、`--skip-oracle`、
`--skip-protocol`、`--skip-input-edge-cases` 或 `--fail-fast` 筛掉应测项。这些其他用法
只允许用于开发期定位。

这 373 例只用于正确性、行为稳定性和规模诊断，不参与官方 50 例的 `SUM`、`MEDIAN`、
`P95`、`MAX`、`WIN` 或 `LOSS` 计算。

官方 50、authoritative 219、非规模 364 reference diff 或非规模基础设施/协议检查任一失败时，
候选直接判定为 **REJECTED**，不得讨论其性能收益。spec-pending 标签差异和 scale 诊断
必须披露，但不得仅凭这些未经独立证明的标签否决候选。

### 4.1 新语料迁移状态

2026-08-13 已使用最终分层 runner 在官方 Linux AArch64 镜像正式复跑。旧门禁为官方
`50/50` 精确首错、oracle `45/45`、项目 `57/57`，综合 runner 无基础设施失败；最终
`oracle-backed` 摘要为 `371/373`，其中 2 个 authoritative 硬失败，另有 42 个诊断
差异。若以 `all` 策略观察全部 manifest 标签，匹配数为 `329/373`。按 evidence tier
解释为：

- authoritative：`217/219`，两个明确 false reject 为
  `lambda-block-body-and-iife` 与 `postfix-member-call-index-chain`；
- diagnostic_spec_pending：145 例中有 40 个 manifest 标签差异，仅作规范待确认诊断；
- diagnostic_scale：9 例中 `four-kilobyte-identifier` 与
  `three-hundred-local-declarations` 超过 30 秒，仅作规模诊断。

因此，恢复正式性能候选只要求先修复两个 authoritative 缺陷并建立 `219/219` control，
不要求把未经独立证明的 40 个 spec-pending 差异或两个规模超时改成 `373/373`。不得为
通过硬门禁而删例、改 authoritative 标签、放宽安全前缀或增加 oracle 豁免；同样不得
把 diagnostic 标签当成已确认赛事规范去驱动高风险语义改写。

### 4.2 并发或启动路径修改的附加门禁

任何修改线程、future、条件变量、启动初始化顺序或异常汇合方式的候选，
还必须在正式性能计时前执行：

```bash
python3 tools/run_concurrency_startup_checks.py \
  --solution ./solution \
  --cold-starts 1000 \
  --long-statements 256 \
  --parallel-clients 8 \
  --parallel-rounds 20
```

该命令是正确性压力测试，不是性能 benchmark；其耗时统计只用于发现卡死和异常
值，不得与第 3 节口径混合或用于宣称提升。脚本必须确认：

1. 1000 个全新进程均在超时内启动、回复且正常退出；
2. 长合法输入的每个 token 均只获得一个正确回复；
3. 多客户并行压力下无死锁、丢回复、重复回复或非零退出；
4. 缺失或损坏的 context、token table 和 grammar 只在临时副本上测试，失败时
   必须非零退出、写出诊断且不得卡死；
5. 同时缺失 token table 与 grammar 时，仍保持 token table 异常优先；
6. 脚本不得移动、重命名、覆盖或修改仓库中的真实资源。

线程创建失败和状态转移强制 yield 无法由黑盒进程稳定触发，必须通过仅测试
构建启用的可注入 launcher/yield hook 或等价单元测试覆盖。必须验证线程创建失败
回退到串行路径，并在每个共享状态转移前后执行强制 yield 后仍与串行结果一致。
这些 hook 必须由编译开关隔离，在正式构建中完全编译掉。

单 CPU 检查必须在额外的 `--cpus=1` 官方容器内执行同一正确性命令，并添加
`--require-single-cpu`。这一轮不记性能数字，不得在生产代码或正式 A/B/A 计时中
设置 CPU affinity。涉及共享内存、引用生命期或线程同步的候选必须运行
ASan/UBSan；当官方 AArch64 工具链和 XGrammar 支持时还必须运行 TSan，无法运行时
必须在报告中保留工具链错误和说明，不得静默跳过。

## 5. ARM64 可移植性约束

为了避免只针对 Apple Silicon 优化，候选版本必须满足：

1. 必须在锁定的 Linux AArch64 官方镜像内构建和运行；
2. 不得使用 `-mcpu=apple-m1`、`-mcpu=apple-m2`、`-march=native` 等宿主机专用参数；
3. 不得检测 Apple CPU 型号并走特殊快速路径；
4. 不得依赖 macOS API、Accelerate、Metal、Apple 私有指令或宿主机动态库；
5. 不得依赖宿主机固定页大小、核心数量、CPU 频率或文件缓存状态；
6. 使用 SIMD 时必须以官方目标可用的通用 ARMv8-A/AArch64 能力为边界，并保留
   正确的标量或通用实现；
7. 不得通过提高 Docker CPU/内存配额或更换宿主机来宣称代码优化；
8. 编译器、编译参数或第三方库版本发生变化时，必须单独标注，不能伪装成算法优化。

当前 `-O3`、C++17 和通用 AArch64 构建属于允许范围。

## 6. 禁止针对公开样例作弊

以下行为无论速度提升多少都必须拒绝：

- 硬编码 50 个样例的名称、源码片段、token 序列或首错位置；
- 根据公开样例特征查表返回答案；
- 将官方答案或首错索引编译进生产二进制；
- 识别 benchmark/harness 进程后改变语义逻辑；
- 跨进程保留公开样例结果缓存；
- 减少语法或语义规则，使公开样例仍通过但隐藏样例能力退化；
- 修改计时器、吞掉失败 trial 或只报告最快一次。

所有优化都必须能用算法、数据结构、内存访问、初始化或通用编译优化解释，并对未见
样例保持同样语义。

## 7. 标准性能测试流程

### 7.1 测试前检查

每轮测试必须记录：

```bash
git rev-parse HEAD
git status --short
git diff --stat
docker info --format '{{.OSType}} {{.Architecture}} {{.ServerVersion}} {{.NCPU}} {{.MemTotal}}'
docker image inspect docker.educg.net/compiler_system_challenge/cjchecker:20260522 \
  --format '{{.Id}} {{.RepoDigests}} {{.Architecture}} {{.Os}}'
shasum -a 256 context.json grammar/cangjie.gbnf \
  ../../cangjie-fragment-checker/wrong_error_positions.json
```

还必须满足：

- 宿主机接通电源，关闭低电量模式；
- Docker Desktop 资源配置保持不变；
- 暂停大规模编译、视频转码、模型推理和系统更新；
- 不在明显热降频状态下开始正式测试；
- 对照版本和候选版本测试间隔应当不超过 30 分钟。

### 7.2 构建约束

必须在同一个容器生命周期内完成“构建后立即测试”。`build.sh` 安装的 XGrammar
动态库不会自动保留到另一个全新容器。

构建必须使用：

```bash
set -euo pipefail
./build.sh
```

构建失败、出现 warning 新增、生成非 AArch64 ELF 或运行时找不到共享库时，测试无效。
构建时间必须单独记录，但不计入单样例运行时间。

### 7.3 测量参数

默认正式参数固定为：

```text
warmups=1
repetitions=9
seed=20260811
fresh_process_per_trial=true
timer=time.perf_counter_ns
```

统一使用：

```bash
python3 -u baseline_results/run_official_baseline.py \
  --official-root /official \
  --solution /workspace/solution \
  --warmups 1 \
  --repetitions 9 \
  --seed 20260811 \
  --output-prefix /workspace/baseline_results/<版本名>
```

不得只运行最有利的样例；每次正式测试必须运行全部 50 例。允许开发期单测，但单测
结果不得作为正式优化结论。

### 7.4 正式 A/B/A 对照

正式接收候选版本时，不得只把候选结果与数天前保存的 baseline 比较。必须在相同
宿主机状态和 Docker 配置下依次测试：

1. `A1`：未修改的对照版本；
2. `B`：候选优化版本；
3. `A2`：再次测试未修改的对照版本。

每一阶段都执行 1 次预热和 9 次实测。对每个样例，正式对照值取 A1、A2 两个中位数
的平均值。

如果 A1 与 A2 的 50 例中位数或 50 例耗时总和相差超过 3%，说明环境发生漂移，整轮
A/B/A 测试判定为 **INVALID**，必须重新测试。

## 8. 统计指标与优化判定

对每个样例 `i` 定义：

```text
B_i = 对照版本 process_total_ms 中位数
C_i = 候选版本 process_total_ms 中位数
R_i = (B_i - C_i) / B_i
N_i = max(1.0 ms, 3% × B_i)    # 单例噪声阈值
```

全局指标：

```text
SUM = 50 个样例中位数之和
MEDIAN = 50 个样例中位数的中位数
P95 = 50 个样例中位数的 P95
MAX = 50 个样例中位数的最大值
WIN = C_i <= B_i - N_i 的样例数
LOSS = C_i >= B_i + N_i 的样例数
```

### 8.1 ACCEPTED：正式接受

通用优化必须同时满足：

1. 所有正确性硬门槛通过；
2. A/B/A 环境漂移不超过 3%；
3. `SUM` 至少改善 5%；
4. `MEDIAN` 不得回退超过 1%；
5. `P95` 不得回退超过 3%；
6. 不得有单例回退同时超过 2 ms 和 8%；
7. 本地官方 harness 端到端复核不得出现超过 5% 的整体回退；
8. 满足 ARM64 可移植性与禁止作弊要求。

### 8.2 PROVISIONAL：待验证

出现下列任一情况，只能标记为待验证：

- `SUM` 改善在 2% 到 5% 之间；
- 改善主要来自少数 trial 或单个样例；
- A1/A2 漂移在 2% 到 3% 之间；
- 不同轮次的提升方向不一致；
- 改动涉及编译器、链接方式或第三方库版本。

待验证版本必须将实测次数提高到 21，并完整重复两轮 A/B/A。两轮均满足正式接受条件
后才能改为 **ACCEPTED**。

### 8.3 NO PROVEN GAIN：未证明提升

`SUM` 改善小于 2%，或提升没有超过噪声阈值时，不得宣称优化有效。可以保留代码质量
改进，但性能结论必须写为“未证明有显著提升”。

### 8.4 REJECTED：拒绝

以下任一情况直接拒绝：

- 正确性测试失败；
- `SUM`、`MEDIAN` 或慢样例出现明确回退且无预先声明的目标收益；
- 结果不可复现；
- 违反 ARM64 可移植性要求；
- 存在公开样例特化或测试作弊；
- 只报告最好一次、删除异常值或改变计时边界。

### 8.5 定向优化例外

若优化目标在测试前已明确限定为启动时间、Lambda、泛型或某个慢样例族，可以使用定向
验收，但必须满足：

- 目标组 `SUM` 至少改善 10%；
- 全部 50 例 `SUM` 不得回退超过 1%；
- `MEDIAN`、`P95` 和 `MAX` 均不得出现显著回退；
- 报告必须同时展示目标组和全部 50 例结果。

不得在看到测试结果后再选择“目标组”。

## 9. 结果文件与命名

所有正式结果必须保存，禁止覆盖旧结果。建议命名：

```text
baseline_results/YYYYMMDD_HHMM_<commit>_<role>.json
baseline_results/YYYYMMDD_HHMM_<commit>_<role>.csv
baseline_results/YYYYMMDD_HHMM_<commit>_<role>.md
```

其中 `<role>` 为 `A1`、`candidate` 或 `A2`。

每份正式报告必须包含：

- 源码 commit、完整 `git status --short` 和补丁说明；
- 官方样例 commit 与 registry SHA-256；
- 镜像 tag、digest、架构和 Docker 资源；
- 编译器版本、编译参数和 `solution` SHA-256；
- 预热次数、实测次数、随机种子和计时器；
- 每例原始 trial、min、median、P95、max；
- 50 例正确性结果；
- A1/B/A2 环境漂移；
- `SUM`、`MEDIAN`、`P95`、`MAX`、`WIN`、`LOSS`；
- 最终判定：`ACCEPTED`、`PROVISIONAL`、`NO PROVEN GAIN`、`REJECTED` 或 `INVALID`。

## 10. 每次优化报告模板

```text
优化名称：
目标瓶颈：
优化前假设：
修改文件：
是否改变语义：否/是（说明）
是否改变依赖或编译参数：否/是（说明）

环境检查：PASS/FAIL
官方 50 例：__/50
完整回归：PASS/FAIL
A1/A2 漂移：__%

A1 SUM：__ ms
B  SUM：__ ms，变化 __%
A2 SUM：__ ms
A1/B/A2 MEDIAN：__ / __ / __ ms
A1/B/A2 P95：__ / __ / __ ms
A1/B/A2 MAX：__ / __ / __ ms
WIN / LOSS：__ / __
最严重单例回退：__，__ ms / __%
官方 harness 变化：__%

ARM64 可移植性检查：PASS/FAIL
公开样例特化检查：PASS/FAIL
最终判定：
判定理由：
结果文件：
```

## 11. 最终原则

一次有效优化必须同时做到：结果正确、计时边界一致、统计上超过噪声、同机可复现、
没有伤害慢样例，并且能在通用 Linux AArch64 环境运行。绝对耗时可以因 Apple Silicon、
鲲鹏服务器或平台调度而变化，但只要严格执行本条约，优化前后的相对结论才具有可信度。
