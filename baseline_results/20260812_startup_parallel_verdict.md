# TokenTable 与 grammar 启动并行判定

## 结论

候选 `6a8df15` 相对诊断基础设施 control `2e0a780` 的功能正确性全部通过，
但正式性能判定为 **PROVISIONAL，未升格，生产改动回退**。

候选只把彼此独立的 TokenTable 构造与 XGrammar 编译重叠；语义检查器仍最先在
主线程构造，TokenTable 与 grammar 的异常仍按旧顺序汇合。没有修改输入输出协议、
grammar、context、token 表格式、语义规则、首错时序或编译器优化参数。

## 正确性与并发安全

官方 Linux AArch64 镜像内通过：

- 单元测试 39/39；
- native fragment differential：66 例 × 4 种分片；
- native context differential：7/7；
- 固定 seed `20260805` fuzz：144 例 × byte/random/line/cl100k/whole；
- 官方公开样例精确首错 50/50；
- 官方语义语料 45/45、项目语料 57/57；
- 综合语料 113/113，96 个 oracle，默认与 competition 双协议共 226 次；
- 1000 次冷启动、256 条语句长输入、8×20 并行进程和 7 种临时资源故障均通过；
- TokenTable 与 grammar 同时缺失时保持 TokenTable 错误优先；
- test-only 强制 async launch 失败路径与串行协议逐字节一致；
- `--cpus=1` 官方容器内同一并发压力通过；
- ASan/UBSan 下官方/项目/综合语料与并发压力通过。

TSan 构建成功，但官方容器禁止运行时设置 `ADDR_NO_RANDOMIZE`，libtsan 在进程初始化
阶段以 exit 66 退出，未进入被测程序；原始工具链失败记录保存在
`20260812_startup_6a8df15_tsan_unavailable.txt`，未把它误报为通过。

## 初始 1 + 9 A1 → B → A2

| 指标 | A1 `2e0a780` | B `6a8df15` | A2 `2e0a780` | A1/A2 control | B 相对 control |
|---|---:|---:|---:|---:|---:|
| SUM | 1729.011 ms | 1641.999 ms | 1711.290 ms | 1720.151 ms | **-4.543%** |
| MEDIAN | 35.828 ms | 34.049 ms | 35.259 ms | 35.628 ms | -4.433% |
| P95 | 44.238 ms | 42.536 ms | 43.825 ms | 44.032 ms | -3.396% |
| MAX | 48.392 ms | 46.886 ms | 48.517 ms | 48.455 ms | -3.237% |

- A1/A2 SUM 漂移 1.030%；
- 48 WIN / 0 LOSS；
- 无单例同时回退超过 2 ms 和 8%；
- 所有 1350 次正式 trial 都得到官方精确首错。

由于 SUM 改善介于 2% 与 5% 之间，按条约升至 21 次并重复两轮完整 A/B/A。

## 两轮 1 + 21 升格测试

| 轮次 | control SUM | B SUM | SUM 改善 | MEDIAN 改善 | P95 改善 | 漂移 | WIN / LOSS |
|---|---:|---:|---:|---:|---:|---:|---:|
| R1 | 1690.732 ms | 1621.759 ms | **4.079%** | 3.442% | 2.690% | 2.045% | 41 / 0 |
| R2 | 1716.508 ms | 1646.782 ms | **4.062%** | 4.876% | 3.504% | 0.486% | 37 / 0 |

两轮方向稳定、无显著败例，但都未达到合同要求的 `SUM ≥ 5%`。因此不能将该候选
标记为 ACCEPTED，也不能和后续候选叠加凑够 5%。生产改动必须回退；全部原始
JSON、CSV、Markdown 和专项正确性报告使用 `20260812_startup_*` 前缀保存。
