# 2026-08-04 23:49 平台性能结果

## 结果摘要

- 提交时间：2026-08-04 23:49:30
- 功能结果：AC
- 总分：25.00
- 当前源码基线：`98a8304 add native C++ competition entry`
- 提交包：`XGrammar_submit_final.zip`
- 提交包 SHA-256：`b9d4e8e6949c16f7c7e577087c43e484e8f9c61eb24421542455654d9960717b`

本次平台耗时平均约 `0.340s`，中位数 `0.3425s`，最小 `0.261s`，最大 `0.398s`。与此前约 `0.65s` 的结果相比，端到端耗时已经明显下降，同时保持全部功能测试通过。

## 每例耗时

```text
err_undefined: 0.397s
err_assign_let: 0.398s
err_arity: 0.364s
err_if_not_bool: 0.343s
err_break: 0.359s
err_type_mismatch: 0.360s
err_continue_outside_loop: 0.362s
err_return_type_mismatch: 0.262s
err_duplicate_var: 0.266s
err_arraylist_toarray_assign: 0.352s
err_unary_minus_non_numeric: 0.340s
err_eq_incomparable: 0.338s
err_rel_mixed_numeric: 0.332s
err_mod_non_int64: 0.328s
err_range_non_int: 0.334s
err_for_not_iterable: 0.328s
err_for_pattern_map_bad: 0.349s
err_array_index_not_int64: 0.366s
err_array_fill_type: 0.362s
err_string_contains_arg: 0.348s
err_ctor_call_mismatch: 0.355s
err_generic_arity: 0.349s
err_interface_not_implemented: 0.267s
err_interface_sig_mismatch: 0.261s
err_no_member: 0.334s
err_unknown_named_arg: 0.342s
err_index_non_array: 0.325s
err_unary_not_non_bool: 0.322s
err_while_not_bool: 0.330s
err_arraylist_add_type: 0.342s
err_hashmap_key_type: 0.344s
err_bound_var_mismatch: 0.331s
err_rel_unordered: 0.330s
err_interface_as_value: 0.324s
err_arith_non_numeric: 0.352s
err_lambda_arg_arity_explicit: 0.349s
err_lambda_return_type_explicit: 0.341s
err_lambda_zero_body_explicit: 0.324s
err_lambda_hof_explicit: 0.383s
err_lambda_interface_callback_explicit: 0.384s
err_lambda_in_class_static_explicit: 0.344s
err_lambda_param_narrow_explicit: 0.341s
err_lambda_infer_ambiguous_1: 0.338s
err_lambda_infer_ambiguous_2: 0.352s
err_lambda_infer_wrong_return_1: 0.321s
err_lambda_infer_wrong_return_2: 0.356s
err_lambda_infer_collection_1: 0.340s
err_lambda_infer_collection_2: 0.353s
err_lambda_infer_class_helper: 0.345s
err_lambda_infer_interface_helper: 0.357s
```

## 可复现验证

提交包从全新目录解压后可执行：

- `build.sh` 成功生成原生 `solution`；
- 单元测试 `30/30`；
- 公开错误样例精确差分 `50/50`；
- 官方语义语料 `45/45`；
- 项目测试语料 `57/57`。

当前生产入口是 C++ token 解码与 XGrammar 语法检查，语义规则仍由常驻 Python worker 提供。后续若继续优化，必须保留本提交作为回退基线，并以逐前缀差分验证任何纯 C++ 语义迁移。
