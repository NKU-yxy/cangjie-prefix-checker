# G4-029 长标识符稳健性独立验收报告

## 最终结论

冻结候选 `029531cecaea28b765455559805fe45c31011b54` 对 G4 长标识符稳健性课题的定向验收结论为 **ACCEPTED / RELEASE-READY**。全部正式门禁均为 PASS，最终证据清单无 blocker。

这一结论限于锁定的仓颉语法、工具链、ARM64 官方镜像及测试协议。官方 50 例的通用性能分类仍为 **NO PROVEN GAIN**：A/B/A 的总耗时改善为 0.717%，低于预注册的 2% “proven gain” 阈值；这不影响 G4 定向保护门禁通过。

## 冻结绑定

- 候选提交：`029531cecaea28b765455559805fe45c31011b54`
- 候选树：`cbb1d3fc1136ed622dbf3bd4612b4bbe86107e55`
- 候选 `cpp/solution.cpp` SHA-256：`b8fdd70f0d71f37e0ebb93fd8388d1a70dcca6b54aecf14f02a0c84f56170838`
- 候选生产 ELF SHA-256：`52119143688b0f2c92deb0ef019c7ee6c5deba8830c5011daa5b2fdd5554b594`
- 对照提交：`f5f2468c343e7ccc18d48cba0eab0a10920ee1c6`
- 对照生产 ELF SHA-256：`5d9b87076929726411a65d93e5fe1988a71f41ebbcf541c52843f1397c4c4110`
- 官方 ARM64 镜像：`sha256:980dd9f2ede4f0132e9c71c71c1d6553cafd5de7cf1977c2ffe97a5ab34b8c90`

## 正式证据摘要

- 默认生产正确性、ASan/LSan/UBSan、单 CPU 与多 CPU 启动/并发门禁全部通过。
- 完整 legacy shadow：2050 个矩阵运行、5660 个补充布局运行和 28 个生命周期场景，0 mismatch。
- 有限商/滚动窗口/oracle 审计：8190 个有限类别词、3131 个滚动窗口检查、22804 个 XGrammar 比较及 9 个事务 API 比较，0 mismatch。该结果是锁定语法边界内的证据，不宣称为任意语法的普适证明。
- post-gates 保护性测试：378 个 solution 进程、40 个 G4 检查全部通过；4 KiB 标识符候选约 24–25 ms，而对照达到 30 s 超时。
- 正式官方 50 例 A/B/A：1500 个进程（含 warmup）、1350 个计时运行全部正确；A1/A2 SUM 漂移 0.318%，候选相对对照 SUM 改善 0.717%，保护门禁 PASS；通用性能分类为 NO PROVEN GAIN。
- 默认镜像 entrypoint 打包烟测：`course_grader` 返回 `AC`、50/50，容器和验证器均退出 0，结论 RELEASE-READY。
- 静态反特化与最小包闭包审计通过；生产运行时差异仅为 `cpp/solution.cpp`，未发现官方用例名、位置、长度或宿主/计时探测特化。

已知边界：仓库中预先存在的 vendored reference snapshot 没有独立证明完整的上游 LICENSE/NOTICE；G4 没有新增依赖或许可证差异，最小生产闭包不受此项影响。release-smoke run-003 验证的是冻结提交的 git-archive 导出；若最终赛事提交包的成员或字节与该导出不同，应对最终确切包再运行一次同协议 smoke。

A/B/A run-002 启动前在正式 artifact contract 之外观察到的三次宿主 CPU idle 分别为 78.70%、90.13% 和 89.72%；首个低值对应 `duetexpertd` 瞬时约 100% CPU。这组三点没有写入冻结 artifact contract，因此不应表述为独立 CPU-idle 时间序列门禁全绿。合同内环境准入由显式 `host_quiescent` latch 负责，计时有效性由 A1/A2 的 SUM 漂移 0.318% 与 MEDIAN 漂移 0.0555%（均低于 3%）判定，最终正式门禁为 PASS。

## 证据分层与可验证性

`evidence/formal/` 中仅收录 post-gate 且允许贡献结论的正式 PASS 证据。早期、pre-gate 或 invalid 尝试保留在 `evidence/supplemental/`，其 `may_contribute=false`，不能参与最终结论。

`inventory.json` 绑定每棵证据树、原始证据清单、二进制、生成表、最小源闭包及 control-to-candidate 完整 diff。`CONTENT_SHA256SUMS` 覆盖包内除自身外的所有普通文件。解压后运行：

```sh
python3 tools/verify_archive.py .
```

发布目录中的外部 `.sha256` 文件绑定完整确定性 `tar.gz`。归档器固定路径顺序、mtime、uid/gid、权限和 gzip 时间戳；两个独立 stage 的产物必须逐字节相同后方可发布。
