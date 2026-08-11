# model stable-event generation 候选拒绝报告

- 优化名称：未闭合 class/interface 顶层只在 lexer 接收新稳定 event 后重建模型
- 对照提交：`36f98f6`
- 候选提交：`f295152e5d996128c7078c3e00860975984f03d8`
- 候选是否包含样例特化：否；仅比较通用 lexer event generation

## 正确性门禁

`FAILED`。在 251 例画像的官方精确首错阶段，
`err_interface_sig_mismatch` 仍从官方 token 32 推迟到 token 33。

这表明某些尚未被增量 lexer 标记为稳定的完整源码前缀，已必须参与
接口签名检查。稳定 event 不是对所有语义事实成立的 dirty 边界。

- 未运行性能 A/B/A；
- 未针对失败的公开样例添加 token/名称/源码分支；
- 候选不作为后续 control。

## 最终判定

`REJECTED (CORRECTNESS)`。候选已回退。
