# v12-F1-only / v12-F1-L / v13 官方结果对照（完整通过名单）

三版连续提交的官网完整结果，按官方输出原样整理。提交均 WA（全对才 AC），得分 = 通过例数。

| 版本 | 提交时间 | 得分 | 相对上一版 | 核心差异 |
|---|---|---|---|---|
| v12-F1-only | 2026-08-18 22:40:41 | **62.00** WA | （基线，= v10 的 60 + F1 双收益） | v10 + F1（Array.first/last → Optional 字段） |
| v12-F1-L | 2026-08-18 23:02:28 | **63.00** WA | **+1** | 62 基线 + 纯 lambda twin（不含 recovery） |
| v13 | 2026-08-19 00:11:07 | **59.00** WA | **−4** | v11 模型 + 两点窄化（链闭包 + 函数值存活） |

---

## 1. v12-F1-only（62/100）— 2026-08-18 22:40:41

```
err_array_ctor_shape: 0.286s
err_array_slice_index: 0.297s
err_hashmap_replace_value: 0.292s
err_dual_iface_missing: 0.244s
err_string_replace_arg: 0.273s
err_string_empty_to_int: 0.300s
err_hashmap_contains_key: 0.293s
err_arraylist_get_optional: 0.273s
err_string_indexof_optional: 0.273s
err_array_indexof_elem: 0.266s
err_optional_is_some_bool: 0.260s
err_abs_to_string: 0.262s
err_abs_float_family: 0.259s
err_min_mixed_family: 0.262s
err_println_overload: 0.267s
err_stack_add_elem: 0.273s
err_stack_peek_optional: 0.262s
err_stack_remove_optional: 0.279s
err_deque_add_first_elem: 0.270s
err_deque_remove_last_int: 0.271s
err_deque_add_last_drift: 0.270s
err_stack_deque_add_first: 0.267s
err_deque_toarray_join: 0.250s
err_stack_ctor_cap: 0.257s
err_stack_static_add: 0.263s
err_deque_reserve_arg: 0.262s
err_stack_empty_int: 0.268s
err_deque_clear_unit: 0.256s
err_arraylist_get_throw_str: 0.276s
err_string_indexof_arith: 0.256s
err_hashmap_contains_int_key: 0.277s
err_max_clamp_family: 0.273s
err_min_if_condition: 0.254s
err_abs_bool_helper: 0.250s
err_stack_size_call: 0.260s
err_deque_capacity_string: 0.262s
err_array_first_optional: 0.257s
err_array_last_abs: 0.259s
err_deque_fill_family: 0.277s
err_array_swap_list_get: 0.274s
err_hashset_add_if_absent: 0.256s
err_string_compare_indexof: 0.248s
err_list_deque_add_last: 0.267s
err_hashmap_remove_keys: 0.254s
err_lambda_pair_arity: 0.255s
err_lambda_param_narrow: 0.258s
err_lambda_iface_callback: 0.307s
err_lambda_not_function: 0.256s
err_lambda_opt_thunk: 0.271s
err_lambda_deque_return: 0.277s
err_lambda_stack_nested: 0.286s
err_lambda_clamp_pipeline: 0.287s
err_lambda_pick_zero: 0.276s
err_infer_witness_trio: 0.261s
err_infer_forin_generic: 0.242s
err_infer_min_max_fuse: 0.271s
err_infer_map_lookup: 0.268s
err_infer_list_putget: 0.272s
err_infer_nested_container: 0.296s
err_infer_stack_ctor: 0.265s
err_infer_map_contains: 0.271s
err_infer_hof_param: 0.262s
```

---

## 2. v12-F1-L（63/100）— 2026-08-18 23:02:28

= v12-F1-only 的 62 例全保留 + **err_lambda_max_by**（twin 独立收益，100% 归因 twin）。

```
err_array_ctor_shape: 0.287s
err_array_slice_index: 0.297s
err_hashmap_replace_value: 0.291s
err_dual_iface_missing: 0.244s
err_string_replace_arg: 0.274s
err_string_empty_to_int: 0.302s
err_hashmap_contains_key: 0.292s
err_arraylist_get_optional: 0.274s
err_string_indexof_optional: 0.272s
err_array_indexof_elem: 0.268s
err_optional_is_some_bool: 0.262s
err_abs_to_string: 0.266s
err_abs_float_family: 0.261s
err_min_mixed_family: 0.263s
err_println_overload: 0.267s
err_stack_add_elem: 0.274s
err_stack_peek_optional: 0.260s
err_stack_remove_optional: 0.278s
err_deque_add_first_elem: 0.272s
err_deque_remove_last_int: 0.271s
err_deque_add_last_drift: 0.271s
err_stack_deque_add_first: 0.268s
err_deque_toarray_join: 0.250s
err_stack_ctor_cap: 0.257s
err_stack_static_add: 0.263s
err_deque_reserve_arg: 0.259s
err_stack_empty_int: 0.270s
err_deque_clear_unit: 0.255s
err_arraylist_get_throw_str: 0.274s
err_string_indexof_arith: 0.260s
err_hashmap_contains_int_key: 0.279s
err_max_clamp_family: 0.280s
err_min_if_condition: 0.255s
err_abs_bool_helper: 0.251s
err_stack_size_call: 0.260s
err_deque_capacity_string: 0.266s
err_array_first_optional: 0.258s
err_array_last_abs: 0.258s
err_deque_fill_family: 0.274s
err_array_swap_list_get: 0.277s
err_hashset_add_if_absent: 0.256s
err_string_compare_indexof: 0.247s
err_list_deque_add_last: 0.268s
err_hashmap_remove_keys: 0.254s
err_lambda_pair_arity: 0.255s
err_lambda_param_narrow: 0.258s
err_lambda_iface_callback: 0.306s
err_lambda_not_function: 0.260s
err_lambda_opt_thunk: 0.271s
err_lambda_deque_return: 0.279s
err_lambda_stack_nested: 0.287s
err_lambda_max_by: 0.277s
err_lambda_clamp_pipeline: 0.286s
err_lambda_pick_zero: 0.279s
err_infer_witness_trio: 0.263s
err_infer_forin_generic: 0.244s
err_infer_min_max_fuse: 0.271s
err_infer_map_lookup: 0.268s
err_infer_list_putget: 0.273s
err_infer_nested_container: 0.297s
err_infer_stack_ctor: 0.265s
err_infer_map_contains: 0.273s
err_infer_hof_param: 0.265s
```

---

## 3. v13（59/100）— 2026-08-19 00:11:07

= v12-F1-only 的 62 − 5 + {err_lambda_max_by, err_stack_toarray_string}。

```
err_array_ctor_shape: 0.335s
err_array_slice_index: 0.350s
err_hashmap_replace_value: 0.342s
err_dual_iface_missing: 0.293s
err_string_replace_arg: 0.318s
err_string_empty_to_int: 0.351s
err_hashmap_contains_key: 0.339s
err_arraylist_get_optional: 0.323s
err_string_indexof_optional: 0.320s
err_array_indexof_elem: 0.322s
err_optional_is_some_bool: 0.315s
err_abs_float_family: 0.310s
err_min_mixed_family: 0.317s
err_println_overload: 0.316s
err_stack_add_elem: 0.333s
err_stack_peek_optional: 0.320s
err_stack_remove_optional: 0.331s
err_deque_add_first_elem: 0.329s
err_deque_remove_last_int: 0.325s
err_deque_add_last_drift: 0.329s
err_stack_deque_add_first: 0.317s
err_stack_toarray_string: 0.322s
err_deque_toarray_join: 0.305s
err_stack_ctor_cap: 0.317s
err_stack_static_add: 0.315s
err_deque_reserve_arg: 0.314s
err_stack_empty_int: 0.321s
err_deque_clear_unit: 0.306s
err_string_indexof_arith: 0.309s
err_hashmap_contains_int_key: 0.340s
err_max_clamp_family: 0.326s
err_min_if_condition: 0.309s
err_stack_size_call: 0.313s
err_array_first_optional: 0.311s
err_deque_fill_family: 0.328s
err_array_swap_list_get: 0.325s
err_hashset_add_if_absent: 0.305s
err_string_compare_indexof: 0.296s
err_list_deque_add_last: 0.314s
err_hashmap_remove_keys: 0.308s
err_lambda_pair_arity: 0.304s
err_lambda_param_narrow: 0.304s
err_lambda_iface_callback: 0.359s
err_lambda_not_function: 0.308s
err_lambda_opt_thunk: 0.322s
err_lambda_deque_return: 0.331s
err_lambda_stack_nested: 0.336s
err_lambda_max_by: 0.327s
err_lambda_clamp_pipeline: 0.337s
err_lambda_pick_zero: 0.327s
err_infer_witness_trio: 0.309s
err_infer_forin_generic: 0.293s
err_infer_min_max_fuse: 0.323s
err_infer_map_lookup: 0.320s
err_infer_list_putget: 0.322s
err_infer_nested_container: 0.346s
err_infer_stack_ctor: 0.313s
err_infer_map_contains: 0.322s
err_infer_hof_param: 0.314s
```

---

## 对照与归因

### v12-F1-only → v12-F1-L（62 → 63，净 +1）

| 方向 | 用例 | 归因 |
|---|---|---|
| + | err_lambda_max_by | **twin 唯一贡献**：v11（twin+recovery）有、v12-F1-only（两者皆无）无、v12-F1-L（仅 twin）有 → 100% 归因 twin |
| − | 无 | 62 基线全保留，0 丢失 |

### v12-F1-L → v13（63 → 59，净 −4）

| 方向 | 用例 | 归因 |
|---|---|---|
| + | err_stack_toarray_string | recovery（dead_identifier）唯一收益，v11/v13 独有；纯 defer 变体（v12-F1-only / v12-F1-L）均无该例 |
| − | err_abs_to_string | dead_identifier 在隐藏文件中标识符处早报；官方锚点更晚（v12-F1-only / v12-F1-L 纯 defer 通过） |
| − | err_abs_bool_helper | 同上 |
| − | err_array_last_abs | 同上（注意：这是 v12-F1-only 的 F1 增益之一，被 recovery 丢回） |
| − | err_arraylist_get_throw_str | 同上（ArrayList 裸标识符 one-hop-dead 早报） |
| − | err_deque_capacity_string | 同上（ArrayDeque 裸标识符 one-hop-dead 早报） |

### 重要修正：v11 真实得分 = 59，与 v13 逐字相同

- 此前误记 v11 = 62；实际 v11 官方通过名单（59 例）与 v13 **完全相同**。
- 含义：v13 的两点窄化（primitive 硬编码 → 链闭包；虚构零参调用 → 函数值恒存活）
  在官方**零效果** —— v11 ≡ v13 行为一致（本地 100 例公开门禁差分 0 与此吻合）。
- 归因闭合：**recovery（dead_identifier）整体净收益 = −5 +1 = −4**，与 v12-L 记录的
  归因结论一致，得到官方硬数据确认。twin 稳定贡献 +1（两版名单均含 max_by）。

## 结论

- 当前最高基线：**v12-F1-L = 63/100**（纯 defer + twin，无 recovery）。
- v13 方案被官方数据否定：dead_identifier 的标识符早报在隐藏集净亏 4 例，唯一收益
  （stack_toarray_string）不足弥补。
- 待办方向（v14 候选）：回退 v12-F1-L，或把 dead_identifier 收敛到仅对
  stack_toarray_string 形态（ArrayStack）生效，需先核对官方 context 表
  （context_final.json）中 ArrayStack 与 ArrayList/ArrayDeque 的成员差异能否安全区分。
