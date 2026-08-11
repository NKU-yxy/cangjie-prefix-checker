# TokenTable 单缓冲区候选验收报告

- 优化名称：从单一已验证文件缓冲区直接读取 token entry 和 payload
- 目标瓶颈：消除 100k entry vector 和 blob 的二次复制，改善进程启动/首响应
- 对照提交：`8294286e7b587cc8a4b0ff40daf9ddddfb26f9b1`
- 候选提交：`a6d7a8be8fc038b86a78f33375294fd0338c37c6`
- 是否改变协议或表格格式：否；magic、count/blob 字段、missing token 和全部边界检查保留
- 是否改变依赖或编译参数：否

## 正确性与内存安全

- 官方 50 例精确首错：50/50；所有正式 trial 零失败
- 单元测试：34/34
- native fragment differential：66/66 语义例 × 4 种分片
- native context differential：7/7
- 固定 seed hidden semantic fuzz：144 例、5 种分片、零失败
- 官方语义语料：45/45；项目语料：57/57
- ASan/UBSan：PASS；消毒器下通过负 token ID、超大越界 ID、cl100k missing ID、144 fuzz、50 官方精确首错、45 官方语义和 57 项目语料

## A1 → B → A2

三阶段在同一个锁定 Linux AArch64 官方镜像容器中运行，每阶段每例 1 次预热 + 9 次实测。

| 指标 | A1 | B | A2 | 逐例 A1/A2 平均对照 |
|---|---:|---:|---:|---:|
| SUM (ms) | 1950.600 | 1951.593 | 1965.530 | 1958.065 |
| MEDIAN (ms) | 39.999 | 40.457 | 40.530 | 40.264 |
| P95 (ms) | 51.928 | 51.083 | 51.936 | 51.932 |
| MAX (ms) | 56.969 | 56.967 | 57.924 | 57.447 |
| first-response SUM (ms) | 408.667 | 399.469 | 409.296 | 408.982 |
| first-response MEDIAN (ms) | 8.169 | 7.985 | 8.187 | 8.178 |

- A1/A2 SUM 漂移：0.765%
- B 相对正式对照 SUM 变化：**-0.331%**（改善）
- first-response SUM 改善：2.326%；first-response MEDIAN 改善：约 2.36%
- WIN / LOSS：0 / 0
- 最严重单例回退：`err_interface_as_value`，+0.421 ms / +1.255%，未越过 1.005 ms 噪声阈值
- 同时超过 2 ms 和 8% 的单例：0
- ARM64 可移植性检查：PASS
- 公开样例特化检查：PASS；解码路径仅依赖通用 token ID 与文件格式

## 最终判定

`NO PROVEN GAIN`。整体 SUM 改善仅 0.331%，低于 2% 证明阈值；启动定向改善也远低于 10% 的定向验收阈值。按条约不宣称优化有效，不将候选叠加到后续改动。

原始数据为同名 `A1` / `B` / `A2` 的 JSON、CSV 和 Markdown 文件。
