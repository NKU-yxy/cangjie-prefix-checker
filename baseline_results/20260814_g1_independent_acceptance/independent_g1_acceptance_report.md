# G1 独立竞赛验收与正确性审计报告

- 审计时间：2026-08-14（Asia/Shanghai）
- 审计对象：`/Users/doufuru/Documents/编译大赛/Final/project3230617-388044`
- 审计产物根目录：`/private/tmp/g1_independent_audit_20260814.jPABK6`
- Control：`68d780d54c25883b4e05c3f3562b315750b38af0`
- Candidate：`499c9c787fdbd8140307c5b5f472e9aee0c9342c`

## 最终判定

**STATEMENT-LIST SCALE ROBUSTNESS ACCEPTED**

该判定仅适用于本轮重新定义的 G1“大型语句块规模稳健性”范围。旧轮因“300 locals 与 4KB identifier 两项目标只完成一个”而作出的 **REJECTED** 保持不变，本报告不追溯修改旧结论。

G1 未解决 4KB identifier；该问题仍需单独的 G4 lexer/state-machine 项目。

接受依据概括如下：

- 官方精确首错、完整非规模正确性、native/fuzz/context、sanitizer、shadow、反作弊均通过。
- 300 locals 候选两协议中位数为 448.227/455.782 ms；对照均在 35 秒截止，保守加速下界 78.09×/76.79×。
- 500 locals 候选两协议中位数为 1041.254/1017.998 ms，均低于 2 秒。
- 候选 50→500 曲线的 endpoint 指数约 1.34，明显不再接近 O(n³)。
- 其他 7 个 scale 样例最大时间回退 1.25%，逐 trial 保守 RSS 最坏比 1.087，均在门槛内。
- 4KB identifier 仍超时，但候选没有明显恶化：30 秒回答数 90 对 88，共同 88 响应约快 5.9%–6.0%，RSS 基本持平，输出前缀全部正确。
- provenance-bound 官方 50 A/B/A 全部保护门槛通过；SUM/MEDIAN/P95 分别改善 3.896%/3.661%/2.312%。SUM 改善不足 5%，因此不附加宣称“官方 50 改善 ≥5%”。

## 1. 独立性、只读边界与方法

评委现场使用 `git clone --no-local` 分别建立 control、candidate 和官方样例 clone，并 checkout 锁定完整 SHA。当前状态的支持证据为：control/candidate `.git/objects` realpath 不同、均无 alternates，HEAD 分别精确锁定。需要诚实限定：当前文件系统状态不能反向重建历史 clone 命令本身；`--no-local` 是本次评委操作记录，而不是由 Git 元数据单独证明的历史事实。

所有构建和测试均在仓库外审计根目录及一个持续存活的锁定 Docker 容器中完成。未修改 candidate/control 的 `cpp`、grammar、`build.sh`、context、测试语料或标签；仅构建生成 `solution`、`solution_profile`、shadow/sanitizer 二进制等允许的派生物。未执行 `git add`、`commit` 或 `push`。

原始项目仓库评审前后均为 HEAD `9517dfe893790e94e856c2796989914df7dde4d8`，`git status --short` 只有两个评审开始前已存在且保持不变的 untracked 报告：

- `CURRENT_BEST_VS_INITIAL_OFFICIAL50_20260813.md`
- `TEAM_OPTIMIZATION_PROGRESS_REPORT_20260813.md`

评委在仓库外创建了采集器和重算器；它们是证据工具，不进入候选提交，也不替候选修复任何失败：

| 工具 | SHA-256 | 用途 |
|---|---|---|
| `audit_harness.py` | `5c8fe5e6dc44c3aa5048702fdaf33738110bcca8df1776435e21bd82759057a3` | strict official、逐 token scale、transcript/RSS 原始采集；collector-only，不签发 verdict |
| `scale_analyze.py` | `bbd8a8037fc9c55ffadce866982fbc7a4b7c35e7dc7c23b78936e494cd80277e` | 从 raw runs 重算数值 |
| `aba_analyze.py` | `67979de75a48cf25f04d0038c9744d8f3eaae7adf8b7bacc4134ddfb8635ef5a` | 从每例 raw runs 重算 A/B/A |
| `run_aba_bound.py` | `2ed8e1608fb931161330edd76cbcd3015d54084c7e1054b43c17033e2c49a82a` | 固化 A1/B/A2 的 argv、root、HEAD、grammar、资源、顺序和输出哈希 |

`scale_analyze.py` 的通用判定能力经第二评委反例审查后被认定只能用作“已认证 raw JSON 的数值重算器”，不能单独签发 PASS。最终 scale 判定另行逐 trial 复核了：source/token/run 绑定、交替 schedule、raw stderr、timeout phase/termination、完整响应、逐 trial 最大 VmHWM 和尾部局部复杂度；未仅依赖其汇总。

## 2. 锁定版本与环境

| 项目 | 锁定/实测值 |
|---|---|
| 官方样例 commit | `88336c400e7a4a671424e3e6c46c0866c8c0af93` |
| Registry SHA-256 | `2425e64184d69dd392f6cdec52dc20d42d0977cbe84be744a0ffbd1dfad374f2` |
| Docker tag | `docker.educg.net/compiler_system_challenge/cjchecker:20260522` |
| Docker RepoDigest / image ID | `sha256:980dd9f2ede4f0132e9c71c71c1d6553cafd5de7cf1977c2ffe97a5ab34b8c90` |
| 实际容器 | `a043f41a6c6538a8821fb9149e433fffe06d2e8ca00048196fd1955c8c59d3d2`（同一生命周期） |
| 容器 OS/架构 | Linux AArch64 (`aarch64`/image `arm64`) |
| 容器 CPU/内存 | 10 vCPU；`MemTotal=8,126,480 KiB`（Docker 上限约 7.75 GiB） |
| 编译器 | GCC/G++ 11.4.0 |
| Python/XGrammar | Python 3.10.12；XGrammar 0.2.1 |
| 关键依赖 | tiktoken 0.13.0；lark 1.3.1；numpy 2.2.6；pydantic 2.13.4 |
| 宿主 | MacBook Air Mac17,3；Apple M5；10 核；16 GB |
| 电源 | AC attached；`lowpowermode=0` |

镜像实际 RepoDigest、容器/挂载、宿主和电源状态保存于 `logs/runtime_binding_addendum.txt`，SHA-256 `9f08185fa8eb09b26d7c1458b1f7603a2571fb616930629cebb84dd846f882b2`。容器依赖/ELF 环境保存于 `logs/container_environment.txt`，SHA-256 `e01091779933cb121879c812ec24179af22d2f4823cd78356c8b95d7a9b1280f`。

默认 control/candidate 分别独立构建。构建日志无编译 warning；日志中只有外层 shell `time` 的时长。sanitizer 构建有 3 条既有 `-Wrange-loop-construct` warning，运行期所有 sanitizer stderr 均为空。

## 3. Commit ancestry、production diff 与 grammar 等价

`merge-base(control,candidate)` 精确为 control；`rev-list --left-right --count control...candidate` 为 `0 8`。线性祖先链如下：

1. `735a52e20671930f7e956401d39d5ca1c69d3ec9` — bound declaration regex scans with candidate index
2. `75e9702c5efaf98e60fc2c8b99e62efcd44ae7fe` — 对上一提交精确 revert
3. `3579e9be7de9c3c7822e48b17b99c0e85d982ad8`
4. `353608c0f222be9f2b812048ec15762bc9277724`
5. `1fe3f04b95179ad0b88e3e671f6b2f057262c893`
6. `5c0953b3668e30dbca42eb127e9c7ee4a32feaab` — shadow 基础设施
7. `8c90d6ff7547244c0f31b20b6ed9cf2dc12b44b2` — statement-list grammar
8. `499c9c787fdbd8140307c5b5f472e9aee0c9342c` — grammar baseline integrity hash

完整 diff 为 28 files、`+137948/-4`，其中绝大多数是归档的历史报告/JSON。生产构建与 grammar 的实质范围是 4 files、`+214/-2`：

| 文件 | 变化 | 默认 production 影响 |
|---|---:|---|
| `build.sh` | +3 | 仅显式 `CANGJIE_GRAMMAR_SHADOW_BUILD=1` 时启用 shadow 宏 |
| `cpp/solution.cpp` | +209 | 全在 `CANGJIE_ENABLE_GRAMMAR_SHADOW` 条件编译中；默认分支保留原实现 |
| `grammar/cangjie.gbnf` | +1/-1 | raw statement-list 递归变换 |
| `grammar/cangjie_token.gbnf` | +1/-1 | token statement-list 对应变换 |

`test_cases/comprehensive/manifest.json` 只更新两项 grammar integrity hash；authoritative 标签、语料和首错位置未修改。context、tokenizer、native semantic 生产数据无净变化。

Grammar 精确变化：

```text
raw old: statements ::= statement (ws statements)?
raw new: statements ::= statement (ws statement)*

token old: statements ::= statement statements?
token new: statements ::= statement statement*
```

令 `T=statement`、`W=ws`：raw 旧规则满足 `S=T | TWS`，展开即 `T(WT)*`，与新规则相同；token 旧规则产生 `T+`，新规则 `TT*` 亦为 `T+`。`ws`、可选分号、statement alternatives 均无差异。

| 工件 | Control SHA-256 | Candidate SHA-256 |
|---|---|---|
| raw grammar | `6131041ed52120b65ee75440c97704dfe91d1a0fda0aaf99b3e1c75e3054f989` | `eb4a5cd0b705407281860bd2ddf1e20b97ad48aceafd96621d55c1385c06ca90` |
| token grammar | `cbe033bea0b88c4d042e258cb4a9b79dfe0912072dc6b5468f742c5d57d6dae0` | `1cb6503b4ce8c24b6a4f12b7ff0ee1a7e8f4d09273bf4e87d254749209096cc1` |
| `context.json` | `8058e383390f444f56ee4ac0008493c44c8e32fa632d18ed48f998dc36623348` | 相同 |
| `generated/context.bin` | `5fe131cdb2f0fdb3e7bfbc1a527f469873324b95d455e081306369f96b77c765` | 相同 |
| `generated/cl100k_base.bin` | `308b0361bc24138a3ba3b3659cc09083f2d8fcd5dcd080a407b499e97cc2fd34` | 相同 |
| manifest | `e0af56059f58f8f5d99fc9c1d243c75ed9df9670f2057b20421292dc48782496` | `b3ac3ccfc845ac37e61ed2146fefb61b67ae6b78336b8d80338486bd0806768e` |

独立构建的默认 control/candidate `solution` SHA-256 都是 `5d9b87076929726411a65d93e5fe1988a71f41ebbcf541c52843f1397c4c4110`，均为 ELF64 AArch64 PIE。二进制字节相同是可解释且预期的：grammar 和 generated 资源由 executable-relative root 在运行时读取，因此验收始终同时绑定 solution realpath 与各自 root/grammar；不能以相同 ELF 哈希替代 grammar 绑定。

其他构建工件：

- shadow solution：`b34ccb550d3904f46241937a47bdbe9d219966b5fedf96d3effeacbe68e66ba2`
- profile control/candidate solution：均为 `45a93a62e75dfc9713b1c39c98bbe6629bd0968543b549a9f7c86a411ca10866`
- ASan/LSan/UBSan + shadow solution：`63624da3e90dbda616cfe0f0f555f37ebd6258013c58813bbf439a16f9524678`
- sanitizer native semantic driver：`51efdeab1c06df8a42b6824bd12ca5b47c3aa3ba9c965ad0acf52fdaee615723`

## 4. 反作弊与默认二进制审计

对 control→candidate 全部生产差异做了静态搜索和人工审查。未发现：官方/综合样例名或源码片段、token 序列、首错常数、benchmark/harness 检测、Docker/container 字符串或生产分支、identifier/locals 阈值、Apple/macOS/CPU 特化、`-march=native`、PGO、CPU affinity、延迟/批量 stdout、context/registry/标签/语料修改。

唯一新增执行路径是明确编译开关控制的 shadow 测试构建。默认 control/candidate ELF 的 strings/symbol 审计确认不包含 shadow grammar、mismatch、profile、test/sample hook；`logs/default_binary_audit_v2.stdout` SHA-256 为 `118502f47a3b2014e34803aa1b629b5dc936f6da591cae1d1f50c3a88dc1bcf8`。静态审计记录 `logs/static_anticheat_audit.txt` SHA-256 为 `86255de1479b21f1b3f4e55243fb8014fba04d354694efedaca92154e78a8971`。

**反作弊审计：PASS。**

## 5. 官方 50 精确正确性

官方锁定 registry 在 control/candidate 默认构建上均为 50/50。额外 strict harness 对 50 例执行 control/candidate × default/competition 共 200 个 fresh-process trial，完整保存逐 token transcript、首拒 token/byte、尾随 stdout、stderr、exit、timeout 和 initialization exception：200/200 精确通过，0 缺测、0 trial exception；stdout 仅严格 `0/1`，首错前无提前拒绝、首错无延迟、首错后无额外 stdout，exit 0、stderr 空。

下表“4/4”表示每例 control/candidate × 两协议全部精确通过：

| 官方样例 | 锁定首错 token index | strict 结果 |
|---|---:|---:|
| `err_undefined` | 374 | 4/4 |
| `err_assign_let` | 425 | 4/4 |
| `err_arity` | 374 | 4/4 |
| `err_if_not_bool` | 306 | 4/4 |
| `err_break` | 356 | 4/4 |
| `err_type_mismatch` | 346 | 4/4 |
| `err_continue_outside_loop` | 347 | 4/4 |
| `err_return_type_mismatch` | 18 | 4/4 |
| `err_duplicate_var` | 54 | 4/4 |
| `err_arraylist_toarray_assign` | 309 | 4/4 |
| `err_unary_minus_non_numeric` | 293 | 4/4 |
| `err_eq_incomparable` | 296 | 4/4 |
| `err_rel_mixed_numeric` | 281 | 4/4 |
| `err_mod_non_int64` | 272 | 4/4 |
| `err_range_non_int` | 285 | 4/4 |
| `err_for_not_iterable` | 279 | 4/4 |
| `err_for_pattern_map_bad` | 308 | 4/4 |
| `err_array_index_not_int64` | 367 | 4/4 |
| `err_array_fill_type` | 345 | 4/4 |
| `err_string_contains_arg` | 312 | 4/4 |
| `err_ctor_call_mismatch` | 347 | 4/4 |
| `err_generic_arity` | 329 | 4/4 |
| `err_interface_not_implemented` | 57 | 4/4 |
| `err_interface_sig_mismatch` | 32 | 4/4 |
| `err_no_member` | 279 | 4/4 |
| `err_unknown_named_arg` | 298 | 4/4 |
| `err_index_non_array` | 270 | 4/4 |
| `err_unary_not_non_bool` | 258 | 4/4 |
| `err_while_not_bool` | 280 | 4/4 |
| `err_arraylist_add_type` | 293 | 4/4 |
| `err_hashmap_key_type` | 297 | 4/4 |
| `err_bound_var_mismatch` | 273 | 4/4 |
| `err_rel_unordered` | 270 | 4/4 |
| `err_interface_as_value` | 240 | 4/4 |
| `err_arith_non_numeric` | 347 | 4/4 |
| `err_lambda_arg_arity_explicit` | 340 | 4/4 |
| `err_lambda_return_type_explicit` | 314 | 4/4 |
| `err_lambda_zero_body_explicit` | 258 | 4/4 |
| `err_lambda_hof_explicit` | 380 | 4/4 |
| `err_lambda_interface_callback_explicit` | 341 | 4/4 |
| `err_lambda_in_class_static_explicit` | 264 | 4/4 |
| `err_lambda_param_narrow_explicit` | 306 | 4/4 |
| `err_lambda_infer_ambiguous_1` | 307 | 4/4 |
| `err_lambda_infer_ambiguous_2` | 353 | 4/4 |
| `err_lambda_infer_wrong_return_1` | 255 | 4/4 |
| `err_lambda_infer_wrong_return_2` | 348 | 4/4 |
| `err_lambda_infer_collection_1` | 289 | 4/4 |
| `err_lambda_infer_collection_2` | 308 | 4/4 |
| `err_lambda_infer_class_helper` | 278 | 4/4 |
| `err_lambda_infer_interface_helper` | 304 | 4/4 |

**官方 50 正确性门禁：PASS。**

## 6. 完整正确性门禁

| 门禁 | 独立结果 |
|---|---|
| 官方精确首错 | 50/50；strict 200/200 |
| authoritative | 219/219 |
| non-scale comprehensive | 364/364 |
| default/competition reference diff | candidate 728 runs 与 control/reference 728 runs 全等 |
| safe-prefix | candidate 238 与 control/reference 238，全等 |
| input edge | candidate 26 与 control/reference 26，全等 |
| 官方语义语料 | 45/45 |
| 项目语料 | 57/57 |
| unittest | 61/61 |
| native fragment | 66/66 × 4 fragmentations |
| native context | 7/7 |
| hidden fuzz | seed 20260805，144 cases × 5 fragmentations，0 failure |
| comprehensive corpus generation | control/candidate 均生成并校验 373 cases |

364 例严格比较同时核对完整逐 token transcript、first reject token、first reject byte、exit code、stderr、timeout 和 initialization exception，未发现任何候选/对照非规模行为差异。145 个 diagnostic/spec-pending 样例不以未独立证明的 manifest 标签作为门禁；其中 40 个标签 disagreement 被保留为诊断，但 candidate 与 control/reference 的既有逐 token 行为全等，因此不构成 authoritative 失败。

Sanitizer 使用独立 clone 和独立构建，启用 ASan/LSan/UBSan，运行环境包括：

```text
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1:abort_on_error=1:strict_string_checks=1
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1
```

sanitizer 下官方 50/50、oracle 45/45、project 57/57、comprehensive 364/364、authoritative 219/219、native fragment 66×4、native context 7/7、hidden fuzz 144×5 全部通过；所有运行期 sanitizer stderr 为空。

**完整正确性与 sanitizer 门禁：PASS。**

## 7. Shadow 与等价审计

`CANGJIE_GRAMMAR_SHADOW_BUILD=1` 独立构建后，raw old/new matcher 对每一 fragment 比较 accept/reject、首次 reject、完整 transcript；shadow 代码同时比较 exception 是否存在、异常类型和消息，任一 divergence 会立即失败。

动态矩阵实际完成 98 cases × 5 layouts（byte/random/line/cl100k/whole）× 2 protocols = **980 runs**，0 divergence。覆盖 whitespace/tab/CRLF、行/块/嵌套注释、字符串、var/assign/expr、member/index、nested block、lambda、if/else、for/while/do、try/catch/finally、match/case、函数/类体、incomplete、late-error、illegal byte boundary，并覆盖有/无分号、同行/换行。

规模 shadow 的**实际 observation 最大范围**是：

- locals：0、1、2、10、25、50、100、150、200、250、300
- identifier：1、2、8、16、32、64、128、256、512

JSON 顶层配置列表还包含 locals 500 和 identifier 1024–8192，但实际 observations 没有运行这些点，故本报告不宣称动态覆盖。identifier-512 最慢完成 cell 为 byte/competition，约 77.6 秒；按任务规则没有无限等待更长 old matcher。

此外，shadow build 下官方 50/50、oracle 45/45、project 57/57、non-scale 364/364、authoritative 219/219、safe-prefix 238、edge 26、hidden fuzz 144×5 全部通过。

限制：动态 shadow 基础设施比较 raw grammar；token grammar 没有单独的动态双 matcher。token 侧依据是前述形式语言等价、token grammar 静态 diff，以及 default/competition 两协议的完整 reference/transcript 测试。默认 production 二进制不包含 shadow 路径。

**可完成范围内 shadow 门禁：PASS。**

## 8. Statement-list locals 规模曲线

正式 process total/RSS 来自默认 production binary。syntax/semantic 来自单独的 profile build，只作分阶段诊断，不替代 production 时间/RSS 门禁。0–250 每角色每协议 3 次、表中为中位数；300 对照每协议 1 次、候选 3 次；500 候选 3 次，对照因 300 超时按规则跳过。RSS 列为所有保留 trial 的最大 kernel `VmHWM`，单位 KiB；采集器另以 5 ms 读取 `/proc/PID/status`，但门禁使用内核高水位而不是点采样 VmRSS。

`C/B` 表示 control/candidate；phase 为 profile build 中位数：

| locals | 协议 | production total ms C/B | profile syntax ms C/B | profile semantic ms C/B | VmHWM max KiB C/B | answer C/B |
|---:|---|---:|---:|---:|---:|---:|
| 0 | default | 11.059 / 9.117 | 0.033 / 0.034 | 1.860 / 1.927 | 8412 / 8412 | 5 / 5 |
| 0 | competition | 8.930 / 10.695 | 0.032 / 0.033 | 1.901 / 1.824 | 8476 / 8516 | 5 / 5 |
| 1 | default | 10.636 / 11.749 | 0.928 / 0.874 | 1.961 / 2.102 | 8584 / 8556 | 21 / 21 |
| 1 | competition | 12.929 / 12.184 | 0.919 / 0.892 | 1.963 / 2.093 | 8584 / 8556 | 21 / 21 |
| 2 | default | 12.527 / 12.338 | 1.464 / 1.376 | 2.156 / 2.154 | 8944 / 8912 | 32 / 32 |
| 2 | competition | 12.337 / 12.113 | 1.450 / 1.369 | 2.059 / 2.085 | 8948 / 8908 | 32 / 32 |
| 10 | default | 18.906 / 16.879 | 6.995 / 4.881 | 2.520 / 2.532 | 11484 / 11244 | 120 / 120 |
| 10 | competition | 19.188 / 17.225 | 6.941 / 4.921 | 2.583 / 2.532 | 12232 / 12220 | 120 / 120 |
| 25 | default | 48.679 / 27.707 | 33.067 / 12.580 | 4.276 / 4.430 | 20112 / 15988 | 285 / 285 |
| 25 | competition | 48.498 / 27.468 | 33.362 / 12.547 | 4.466 / 4.364 | 19980 / 15040 | 285 / 285 |
| 50 | default | 184.262 / 47.941 | 159.976 / 25.427 | 10.337 / 9.907 | 28784 / 21748 | 560 / 560 |
| 50 | competition | 183.648 / 47.115 | 160.443 / 25.258 | 10.234 / 9.937 | 29092 / 20628 | 560 / 560 |
| 100 | default | 1101.294 / 98.686 | 1051.138 / 51.110 | 32.428 / 31.566 | 86704 / 32772 | 1110 / 1110 |
| 100 | competition | 1097.237 / 100.689 | 1049.007 / 51.027 | 32.126 / 31.645 | 85724 / 32624 | 1110 / 1110 |
| 150 | default | 4014.832 / 167.469 | 3916.366 / 81.302 | 69.232 / 66.885 | 152328 / 53668 | 1660 / 1660 |
| 150 | competition | 4082.559 / 166.025 | 3909.235 / 81.641 | 68.891 / 67.936 | 152772 / 54156 | 1660 / 1660 |
| 200 | default | 10269.205 / 247.828 | 10246.810 / 110.480 | 123.006 / 117.648 | 159872 / 56960 | 2210 / 2210 |
| 200 | competition | 10424.078 / 246.638 | 10061.132 / 110.490 | 123.578 / 119.774 | 161272 / 54740 | 2210 / 2210 |
| 250 | default | 21332.360 / 343.365 | 20913.916 / 140.006 | 194.699 / 177.984 | 293112 / 62832 | 2760 / 2760 |
| 250 | competition | 21387.209 / 343.310 | 21221.819 / 139.080 | 192.839 / 176.215 | 292704 / 62532 | 2760 / 2760 |
| 300 | default | ≥35000 / 448.227 | N/A / 170.828 | N/A / 254.190 | 556700 / 98840 | 3241 / 3310 |
| 300 | competition | ≥35000 / 455.782 | N/A / 169.774 | N/A / 249.865 | 555956 / 98684 | 3233 / 3310 |
| 500 | default | skipped / 1041.254 | N/A / 287.148 | N/A / 687.835 | N/A / 118460 | N/A / 5510 |
| 500 | competition | skipped / 1017.998 | N/A / 287.049 | N/A / 723.127 | N/A / 118584 | N/A / 5510 |

300 control 的两次超时均在 `waiting_for_response`，截止约 35.001 秒，随后由采集器 SIGTERM，return code `-15`；没有伪造完成时间。profile build 的 132 个自然完成 trial 全部恰有 1 条 phase record 和 1 条 counter record、无解析错误/额外 stderr，且 `tokens_checked == answer_count`。两条 control-300 超时因进程被终止，没有 phase footer，因此 syntax/semantic 如实为 N/A；control-500 跳过也为 N/A。

关键门禁重算：

- 300 default：`35 / 0.448227 > 78.09×`；competition：`35 / 0.455782 > 76.79×`。
- 500 两协议完整输出 5510 响应，均 ≤2 秒。
- 50→500 候选 `t500/t50` 为 21.719/21.607；endpoint p 为 1.337/1.335，OLS p 为 1.332/1.331；相邻尾部局部指数约 1.04–1.65，无近 O(n³) 尾部。
- 0–250 同规模逐 trial RSS 均未越过 1.25×；按每组 `max(candidate)/max(control)` 最坏约 1.005×，采用更保守的 `max(candidate)/min(control)` 口径最坏约 1.065×。300 候选约 98 MiB，显著低于对照超时点约 556 MiB。
- control-500 按规则未运行，因此没有同尺寸精确时间倍率或 RSS 比；本报告不虚构。候选 500 VmHWM 为 118,460/118,584 KiB，control-300 超时点仅作上下文，不当作同尺寸比例。
- 所有自然完成 scale trial stdout transcript、exit 0、stderr 空；小规模绝对抖动完整保留，例如 locals-0 competition 候选比对照 +1.765 ms。

**Statement-list locals 规模门禁：PASS。**

## 9. 其他 scale 样例保护

其余 7 个非 identifier 样例使用默认 production、双协议、control/candidate 交替、各 3 次，所有 trial 保留。时间为中位数；RSS 为 trial 最大值，并额外以 `max(candidate)/min(control)` 给出更保守比率。

| 样例 | 协议 | total ms C/B | Δ ms | 时间比 | answers C/B | VmHWM max KiB C/B | 保守 RSS 比 | transcript/exit/stderr |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `eight-kilobyte-string` | default | 114.671 / 114.647 | -0.025 | 1.000 | 5135 / 5135 | 17912 / 17908 | 1.000 | exact/0/empty |
| `eight-kilobyte-string` | competition | 119.810 / 115.433 | -4.377 | 0.963 | 5135 / 5135 | 17908 / 17904 | 1.000 | exact/0/empty |
| `eighty-top-level-functions` | default | 165.558 / 162.675 | -2.883 | 0.983 | 1372 / 1372 | 21672 / 21224 | 1.024 | exact/0/empty |
| `eighty-top-level-functions` | competition | 168.425 / 168.464 | +0.038 | 1.000 | 1372 / 1372 | 22484 / 22516 | 1.068 | exact/0/empty |
| `ninety-six-nested-blocks` | default | 34.751 / 32.611 | -2.140 | 0.938 | 201 / 201 | 11724 / 11724 | 1.000 | exact/0/empty |
| `ninety-six-nested-blocks` | competition | 32.996 / 33.320 | +0.324 | 1.010 | 201 / 201 | 11724 / 11728 | 1.001 | exact/0/empty |
| `sixty-four-nested-comments` | default | 12.626 / 12.092 | -0.534 | 0.958 | 133 / 133 | 8416 / 8412 | 1.000 | exact/0/empty |
| `sixty-four-nested-comments` | competition | 12.474 / 11.898 | -0.576 | 0.954 | 133 / 133 | 8504 / 8480 | 1.000 | exact/0/empty |
| `three-hundred-element-array` | default | 62.890 / 62.101 | -0.790 | 0.987 | 917 / 917 | 16104 / 15720 | 1.070 | exact/0/empty |
| `three-hundred-element-array` | competition | 61.654 / 62.424 | +0.770 | 1.012 | 917 / 917 | 15276 / 16036 | 1.087 | exact/0/empty |
| `two-hundred-crlf-lines` | default | 10145.239 / 245.584 | -9899.655 | 0.024 | 2405 / 2405 | 292248 / 52252 | 0.180 | exact/0/empty |
| `two-hundred-crlf-lines` | competition | 10216.663 / 242.161 | -9974.503 | 0.024 | 2405 / 2405 | 290908 / 52260 | 0.180 | exact/0/empty |
| `late-error-after-250-declarations` | default | 21969.863 / 358.156 | -21611.707 | 0.016 | 2765 / 2765 | 292496 / 100084 | 0.343 | exact/0/empty |
| `late-error-after-250-declarations` | competition | 22316.074 / 355.991 | -21960.083 | 0.016 | 2765 / 2765 | 294052 / 98524 | 0.338 | exact/0/empty |

最大时间正回退是 `three-hundred-element-array/competition` 的约 1.25%，远低于 10%；最坏保守逐 trial RSS 比 1.087，低于 1.25。所有 7 类样例双协议均完成，transcript、answer、exit 和 stderr 无差异。

### 4KB identifier 非回归

双方每协议各 3 次，全部在 30 秒等待响应时超时；截止后评委 SIGTERM，return code `-15`，stderr 空，不存在提前退出或新异常。所有已输出响应均为正确 `0/1` 前缀。

| 协议 | 30s answers C/B | 共同正确前缀 | 到共同前缀秒 C/B | 时间比 | 到前80秒 C/B | 时间比 | VmHWM max KiB C/B | 保守 RSS 比 | 结论 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| default | 88 / 90 | 88 | 29.626 / 27.879 | 0.941 | 21.718 / 20.467 | 0.942 | 274592 / 274376 | 1.004 | PASS，双方仍 timeout |
| competition | 88 / 90 | 88 | 29.598 / 27.813 | 0.940 | 21.728 / 20.407 | 0.939 | 274688 / 274756 | 1.003 | PASS，双方仍 timeout |

允许回答数短缺是 `max(2, 2%×88)=2`，而候选不是短缺，反而多 2 个响应；共同前缀时延约改善 5.9%–6.0%，RSS 持平，无新错误。

**其他 scale 与 4KB identifier 非回归门禁：PASS。**

再次明确：**G1 未解决 4KB identifier；该问题仍需单独的 G4 lexer/state-machine 项目。**

## 10. 官方 50 provenance-bound A/B/A

只有在全部正确性和 scale 门禁通过后才执行正式 A/B/A。顺序严格为 A1(control) → B(candidate) → A2(control)；每阶段 1 次预热、9 次实测、seed 20260811、fresh process、逐 token 即时交互、exit timeout 2 秒，同一容器和同一组构建产物，无并行 benchmark。三阶段各 9×50=450/450 measured raw runs 正确，return code 0，runner stderr 空。

初次 A/B/A 的 `aba_B.json` metadata 落在 `/control` 与 control commit，runner 又不保存 `--solution` realpath。由于两边 ELF 字节相同，该组 `aba_A1/B/A2.*` 自身无法独立绑定 B 的 executable-relative candidate 资源，故被评委标记为 **provenance insufficient / superseded**，完全排除于正式结论；本报告不从该组文件推断 B 实际加载了哪套 grammar。

随后重新执行 provenance-bound 版本：A1/A2 使用 `/control/baseline_results/run_official_baseline.py --solution /control/solution`，B 使用字节相同的 `/candidate/.../run_official_baseline.py --solution /candidate/solution`。B JSON 原生记录 `/candidate` 与完整 candidate SHA；外部 provenance 同时固化 runner/solution realpath、raw/token grammar、context、generated 资源、stage 时间区间、argv、return code 和输出哈希。A/B runner SHA 均为 `7b22de5cf1dd957dfc0848549f83267457ceab408b3b0a18b62199c0f24b0e56`。

每例先计算 `Control_i=(median(A1_i)+median(A2_i))/2`，再汇总；P95 为 nearest-rank：

| Timing | Aggregate | A1 ms | Control ms | B ms | A2 ms | B change | A1/A2 drift |
|---|---|---:|---:|---:|---:|---:|---:|
| process total | SUM | 1170.741667 | 1176.520166 | 1130.678627 | 1182.298666 | -3.896% | 0.982% |
| process total | MEDIAN | 23.916563 | 23.931511 | 23.055312 | 23.946458 | -3.661% | 0.125% |
| process total | P95 | 29.111042 | 29.511271 | 28.829042 | 29.911500 | -2.312% | N/A |
| process total | MAX | 32.863959 | 32.910605 | 31.984167 | 32.957250 | -2.815% | N/A |
| first response | SUM | 393.219831 | 395.424585 | 394.914916 | 397.629339 | -0.129% | 1.115% |
| first response | MEDIAN | 7.866625 | 7.907104 | 7.894000 | 7.946896 | -0.166% | 1.015% |
| first response | P95 | 7.923917 | 7.955792 | 7.972875 | 8.014625 | +0.215% | N/A |
| first response | MAX | 7.938417 | 7.966730 | 7.976542 | 8.035959 | +0.123% | N/A |
| detection | SUM | 1070.564959 | 1075.564480 | 1030.441585 | 1080.564000 | -4.195% | 0.930% |
| detection | MEDIAN | 21.813250 | 21.924531 | 21.178750 | 22.035812 | -3.402% | 1.015% |
| detection | P95 | 27.196250 | 27.540480 | 26.694709 | 27.884709 | -3.071% | N/A |
| detection | MAX | 30.806750 | 30.908084 | 29.967708 | 31.009417 | -3.042% | N/A |

保护判定：

- A1/A2 SUM 漂移 0.982% ≤3%；MEDIAN 漂移 0.125% ≤3%。
- Candidate SUM/MEDIAN/P95 均无回退，分别改善 3.896%/3.661%/2.312%。
- `N_i=max(1 ms, 3%×Control_i)` 下 WIN/LOSS/NEUTRAL = 18/0/32。
- 50 例没有任何 process-total 正回退，故也没有同时 >2 ms 且 >8% 的严重单例。
- A1/B/A2 各 450/450；任一 trial 不是 50/50 的数量为 0。

**官方 50 A/B/A 保护门禁：PASS。**

## 11. 未覆盖风险与证据限定

1. Dynamic shadow 的真实上限仅为 locals 300、identifier 512；不宣称覆盖 locals 500 或 identifier 1024–4096/8192。
2. Dynamic shadow 是 raw grammar matcher；token grammar 依赖静态等价证明和双协议完整 reference/transcript 测试。
3. control-300 两协议均超时，control-500 按允许规则跳过；不存在 control-500 精确时间或同尺寸 RSS 比，不能推算或伪造。
4. syntax/semantic 来自单独 instrumentation build，仅覆盖任务第八节要求的 locals 曲线；它会引入测量扰动，不替代 default production 的 process total/RSS。control-300 timeout 和 control-500 skip 无 phase footer，按事实为 N/A。
5. 4KB identifier 双方仍超时。本轮证据只能支持“没有明显恶化”，不能支持“已解决”。
6. RSS 门禁使用 Linux `/proc/PID/status` 的 kernel `VmHWM`；点采样 VmRSS 仅作辅助。所有必需 trial 的 gate VmHWM 均存在，但结果仍受此 Docker/宿主环境约束。
7. `git --no-local` 是评委现场操作；当前 objects 独立且无 alternates可验证，但历史命令无法仅凭现存 Git 元数据重建。
8. 旧的未绑定 `aba_A1/B/A2` 与 `aba_analysis` 已作废，只能引用 `aba_bound_*`。
9. 官方 50 SUM 改善 3.896%，不足 5%；不宣称达到可选的“官方 50 改善 ≥5%”。

## 12. 原始证据与哈希

所有路径均相对审计根目录 `/private/tmp/g1_independent_audit_20260814.jPABK6`：

| 证据 | SHA-256 |
|---|---|
| `results/strict_official.json` | `6c9193bd588a57dbde130203f5f89c9688ac3c0527e9d9325f2a9762c13f2178` |
| `results/comprehensive_non_scale_reference_diff.json` | `32405962f5aa7e9bc33b88d59bbf0683d2a1d41246efe013777038c020cbf629` |
| `results/hidden_fuzz_candidate.json` | `afc0ff6efcdd557ac03d562a2b0944d16a21575fe9abf381e7248e4e53fd00c3` |
| `results/shadow_matrix_through_locals300_identifier512.json` | `37632f1af9017830264fea444292d7ba8e81ee48c099cde09006decffa71fe8a` |
| `results/shadow_official50.json` | `3f5d1ca40aef8dd8a6b6edd0c4fad7e45e248390e14228ec104964a1ce8ed781` |
| `results/shadow_comprehensive_non_scale_reference.json` | `bca8f4344767aeaadc9d5b9be21132ff163c523bece4101985e80e4a5bdae858` |
| `results/shadow_hidden_fuzz.json` | `afc0ff6efcdd557ac03d562a2b0944d16a21575fe9abf381e7248e4e53fd00c3` |
| `results/sanitizer_official50.json` | `a23676986ab91aa73e5d8402f5d62625eb55fe43901db938783480723d3681c9` |
| `results/sanitizer_comprehensive_non_scale.json` | `74f3654435a59d3665c3f4fd3bdf909926acd2a8c9e1beb81a3bf25350feca50` |
| `results/sanitizer_native_context.json` | `2c89495f81093d79e033c82f685ab11e04b7677dbf3bc04cca9800b56f9b5a45` |
| `results/sanitizer_hidden_fuzz.json` | `afc0ff6efcdd557ac03d562a2b0944d16a21575fe9abf381e7248e4e53fd00c3` |
| `results/scale_locals.json` | `b31676b781b5c117e1530e8286d949b2ff42487284012e84011ea4e64a3ec12b` |
| `results/scale_profile_locals.json` | `498344b36ca00f3646a3faf8ca98a14d5e28c7d6d9d872d55218c4dc9e637206` |
| `results/scale_other.json` | `2a0c8f5ee6cbc7609739b5b4250cb27f0aff4763098a1298d2decc00e62f5620` |
| `results/aba_bound_provenance.json` | `29b078f112d74f4ae478657c32a2d8c59bcc86b922e1fccbb883ce164e070ff0` |
| `results/aba_bound_A1.json` | `e08a2868065b26b81c1bf706c4c6fd765497412eefb16822263a8b885af40cee` |
| `results/aba_bound_B.json` | `8831a6073419cff3f8977a99aaacfd2be00c3a5af51b0783233e6a2bc6696759` |
| `results/aba_bound_A2.json` | `9796be8ff5f702cbf3f5a774d525d48e613c65184abc4f9a684411132d9f12ec` |
| `results/aba_bound_analysis.json` | `15f882ef29f93a63aa3658c0785dd4d3715699fd710045da18127432307cef81` |
| `results/aba_bound_analysis.md` | `2f072a6afb6ed712f9309417270b605b2cd200efdd9224b26fead1aa23a562b9` |

关键日志位于 `logs/`：

- 环境/镜像：`container_environment.txt`、`runtime_binding_addendum.txt`、`pip_freeze.txt`
- 构建：`control_build.*`、`candidate_build.*`、`candidate_shadow_build.*`、`sanitizer_build.*`
- 默认 ELF/反作弊：`default_binary_audit_v2.*`、`static_anticheat_audit.txt`
- 正确性：`official50_*_gate_valid.*`、`strict_official.*`、`comprehensive_non_scale_reference_diff.*`、`differential_*_valid.*`、`unittest_candidate_valid.*`、`native_*`、`hidden_fuzz_candidate.*`
- shadow：`shadow_matrix.*`、`shadow_official50.*`、`shadow_comprehensive_non_scale_reference.*`、`shadow_differential.*`、`shadow_hidden_fuzz.*`
- sanitizer：`sanitizer_official50.*`、`sanitizer_comprehensive_non_scale.*`、`sanitizer_differential.*`、`sanitizer_native_*`、`sanitizer_hidden_fuzz.*`

同哈希的 deterministic fuzz JSON 是独立重跑相同 seed/生成器后产生相同规范化内容；对应 stdout/stderr 和独立构建路径均保留，不能据哈希相同推断为复用运行。

### 被保留但排除的 setup-invalid / provenance-invalid 轨迹

- `official50_control_gate.*`：最初从 `/audit/bin` 裸 ELF 启动，缺 executable-relative `generated/context.bin`，属于 setup-invalid；正式使用 `official50_control_gate_valid.*`。
- 初始 `differential_control.*`：容器缺 pydantic，属于依赖 setup-invalid；安装锁定 requirements 后使用 `differential_control_valid.*`。
- `default_binary_audit.*` v1：把正常 XGrammar `AcceptString` 符号误当 hook；正式规则修正后使用 `default_binary_audit_v2.*`。
- 首次构建计时尝试：镜像无 `/usr/bin/time`，在编译前失败；随后用 shell `time` 独立重建。
- `results/aba_A1/B/A2.*` 与 `aba_analysis.*`：B 资源路径未在 raw JSON 内自证，provenance 不充分；正式判定只使用 `aba_bound_*`。

所有上述无效轨迹均保留，没有删除失败 trial 或异常值，也没有混入正式统计。

## 签发

在本报告明确列出的动态覆盖上限、control-500 跳过、profile 仪器化和 4KB identifier 未解决等限制下，锁定 candidate `499c9c787fdbd8140307c5b5f472e9aee0c9342c` 满足本轮全部硬接收条件。

**FINAL VERDICT: STATEMENT-LIST SCALE ROBUSTNESS ACCEPTED**
