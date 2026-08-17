# 当前最佳版本相对初赛 baseline：官方 50 例直接累计 A/B/A

- 测试日期：2026-08-13
- 初赛 baseline：`b40791c7104be19196f5c045c17a297103ae1267`
- 当前 accepted 版本：`68d780d54c25883b4e05c3f3562b315750b38af0`
- 当前 HEAD `1fe3f04` 的生产文件与 `68d780d` 完全一致
- 官方样例：`88336c400e7a4a671424e3e6c46c0866c8c0af93`
- 协议：fresh process、逐 token stdin/stdout、精确官方首错
- 顺序：先进行一整轮稳定化 A/B/A，再在同一容器和同一组二进制中执行正式 A1/B/A2
- 每阶段：1 次预热 + 9 次实测
- 正确性：A1/B/A2 均为 50/50，failed trial 均为 0

## 核心结果

| 指标 | 初赛 A1/A2 合成 control | 当前版本 | 改善 |
|---|---:|---:|---:|
| SUM | 1930.374 ms | 1531.869 ms | 20.644% |
| MEDIAN | 39.783 ms | 31.465 ms | 20.908% |
| P95 | 50.844 ms | 38.847 ms | 23.595% |
| MAX | 55.994 ms | 42.011 ms | 24.973% |

- A1/A2 SUM 漂移：1.147%
- A1/A2 MEDIAN 漂移：1.298%
- 逐例相对漂移中位数：1.156%
- WIN / LOSS：47 / 0
- 严重单例回退：0
- 任意正回退：0

## 每个官方样例

control 为该例 A1 与 A2 的 9 次实测中位数之平均；当前为 B 的 9 次实测中位数。

| 样例 | 初赛 control | 当前版本 | 节省 | 改善 |
|---|---:|---:|---:|---:|
| err_undefined | 47.547 ms | 37.929 ms | 9.619 ms | 20.230% |
| err_assign_let | 55.994 ms | 42.011 ms | 13.983 ms | 24.973% |
| err_arity | 46.455 ms | 36.101 ms | 10.354 ms | 22.288% |
| err_if_not_bool | 39.723 ms | 32.277 ms | 7.446 ms | 18.745% |
| err_break | 46.654 ms | 35.950 ms | 10.704 ms | 22.944% |
| err_type_mismatch | 45.259 ms | 35.999 ms | 9.260 ms | 20.460% |
| err_continue_outside_loop | 47.449 ms | 36.906 ms | 10.543 ms | 22.219% |
| err_return_type_mismatch | 11.954 ms | 11.152 ms | 0.802 ms | 6.711% |
| err_duplicate_var | 13.944 ms | 12.647 ms | 1.296 ms | 9.297% |
| err_arraylist_toarray_assign | 42.839 ms | 34.074 ms | 8.765 ms | 20.461% |
| err_unary_minus_non_numeric | 40.619 ms | 32.340 ms | 8.279 ms | 20.383% |
| err_eq_incomparable | 37.616 ms | 30.105 ms | 7.511 ms | 19.969% |
| err_rel_mixed_numeric | 35.714 ms | 28.886 ms | 6.828 ms | 19.118% |
| err_mod_non_int64 | 33.547 ms | 27.778 ms | 5.769 ms | 17.197% |
| err_range_non_int | 35.843 ms | 29.216 ms | 6.627 ms | 18.489% |
| err_for_not_iterable | 33.929 ms | 27.988 ms | 5.941 ms | 17.510% |
| err_for_pattern_map_bad | 39.843 ms | 31.096 ms | 8.747 ms | 21.954% |
| err_array_index_not_int64 | 45.918 ms | 36.098 ms | 9.820 ms | 21.387% |
| err_array_fill_type | 44.243 ms | 34.207 ms | 10.036 ms | 22.683% |
| err_string_contains_arg | 42.340 ms | 33.203 ms | 9.137 ms | 21.580% |
| err_ctor_call_mismatch | 42.888 ms | 33.906 ms | 8.982 ms | 20.943% |
| err_generic_arity | 42.543 ms | 33.136 ms | 9.408 ms | 22.113% |
| err_interface_not_implemented | 14.747 ms | 13.765 ms | 0.981 ms | 6.654% |
| err_interface_sig_mismatch | 13.370 ms | 12.561 ms | 0.808 ms | 6.046% |
| err_no_member | 37.809 ms | 29.997 ms | 7.812 ms | 20.661% |
| err_unknown_named_arg | 39.102 ms | 31.140 ms | 7.962 ms | 20.361% |
| err_index_non_array | 33.952 ms | 28.182 ms | 5.770 ms | 16.995% |
| err_unary_not_non_bool | 32.295 ms | 26.627 ms | 5.668 ms | 17.552% |
| err_while_not_bool | 35.076 ms | 28.688 ms | 6.388 ms | 18.211% |
| err_arraylist_add_type | 40.373 ms | 31.972 ms | 8.400 ms | 20.807% |
| err_hashmap_key_type | 41.042 ms | 31.942 ms | 9.099 ms | 22.171% |
| err_bound_var_mismatch | 36.009 ms | 28.890 ms | 7.119 ms | 19.770% |
| err_rel_unordered | 36.074 ms | 28.986 ms | 7.088 ms | 19.648% |
| err_interface_as_value | 33.571 ms | 27.181 ms | 6.390 ms | 19.035% |
| err_arith_non_numeric | 44.058 ms | 33.635 ms | 10.424 ms | 23.659% |
| err_lambda_arg_arity_explicit | 41.339 ms | 32.104 ms | 9.235 ms | 22.339% |
| err_lambda_return_type_explicit | 39.406 ms | 31.118 ms | 8.288 ms | 21.032% |
| err_lambda_zero_body_explicit | 34.403 ms | 27.501 ms | 6.902 ms | 20.063% |
| err_lambda_hof_explicit | 50.844 ms | 38.847 ms | 11.996 ms | 23.595% |
| err_lambda_interface_callback_explicit | 50.885 ms | 40.491 ms | 10.394 ms | 20.426% |
| err_lambda_in_class_static_explicit | 37.445 ms | 29.840 ms | 7.605 ms | 20.309% |
| err_lambda_param_narrow_explicit | 39.020 ms | 30.998 ms | 8.021 ms | 20.557% |
| err_lambda_infer_ambiguous_1 | 37.947 ms | 30.124 ms | 7.823 ms | 20.616% |
| err_lambda_infer_ambiguous_2 | 44.116 ms | 33.898 ms | 10.219 ms | 23.163% |
| err_lambda_infer_wrong_return_1 | 34.316 ms | 26.809 ms | 7.507 ms | 21.876% |
| err_lambda_infer_wrong_return_2 | 43.154 ms | 32.683 ms | 10.471 ms | 24.265% |
| err_lambda_infer_collection_1 | 40.432 ms | 31.790 ms | 8.642 ms | 21.375% |
| err_lambda_infer_collection_2 | 42.061 ms | 32.932 ms | 9.130 ms | 21.706% |
| err_lambda_infer_class_helper | 39.004 ms | 30.166 ms | 8.838 ms | 22.659% |
| err_lambda_infer_interface_helper | 45.659 ms | 35.995 ms | 9.664 ms | 21.166% |

## 口径说明

这是官网公开 50 例在锁定官方 Linux AArch64 镜像中的本地复现时间，不是已关闭官网服务器重新测得的时间。官网历史单例约 223–310 ms，包含平台、调度和外部 harness 固定开销，不能与本表毫秒值直接相减。

正式 A1/B/A2 前先完成一整轮同规格 A/B/A，使宿主从短时高频状态进入稳定持续负载。此前两次未稳定试跑的 A1/A2 漂移约 21%，均按合同判 INVALID 并隔离保存，没有纳入本报告。正式轮漂移 1.147%，低于 3% 上限。
