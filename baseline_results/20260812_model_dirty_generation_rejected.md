# model dirty generation 候选拒绝报告

- 优化名称：将未闭合 class/interface 顶层的模型重建从每 token 改为语义提交字符驱动
- 对照提交：`11ea516`
- 候选提交：`2df242c872b9e2829f56e952a4b0b7d42d528d98`
- 候选是否包含样例特化：否；只使用通用 `)`、换行、`;`、`}` 和 brace 事件

## 正确性门禁

`FAILED`。在全语料画像的官方精确首错阶段，
`err_interface_sig_mismatch` 的首错从官方 token 32 推迟到 token 33。

该失败说明“名义声明只在这些提交字符刷新”并不对所有前缀成立。
按测试条约：

- 未运行任何性能 A/B/A；
- 未针对该公开样例增加特殊刷新分支；
- 未修改官方首错位置、context 或 grammar；
- 候选不作为后续 control。

## 最终判定

`REJECTED (CORRECTNESS)`。候选已回退。
