# v14-AORTA 官方结果记录（2026-08-19 07:17:40 提交）

- 交付物：`cangjie-checker_v14_AORTA_20260819.zip`（861,885 B，sha256
  `1e4a334fd452e389fd969c777b591fd080fb49ffd660ed9ade8bdddba456f6b6`）
- 得分 **59.00**，判题 **WA**
- 通过 59/100；全部耗时 0.240–0.304 s，均值 0.266 s，无超时（5 s 限制余量充足）
- 基线对照：v12-F1-L = 63 → v14-AORTA = **59，净 −4，低于基线**

## 官网通过名单（59 例，含官网单例耗时，按官网报告顺序）

```text
err_array_ctor_shape: 0.282s
err_array_slice_index: 0.295s
err_hashmap_replace_value: 0.290s
err_dual_iface_missing: 0.241s
err_string_replace_arg: 0.270s
err_string_empty_to_int: 0.299s
err_hashmap_contains_key: 0.289s
err_arraylist_get_optional: 0.274s
err_string_indexof_optional: 0.271s
err_array_indexof_elem: 0.262s
err_optional_is_some_bool: 0.258s
err_abs_float_family: 0.256s
err_min_mixed_family: 0.260s
err_println_overload: 0.263s
err_stack_add_elem: 0.271s
err_stack_peek_optional: 0.258s
err_stack_remove_optional: 0.275s
err_deque_add_first_elem: 0.267s
err_deque_remove_last_int: 0.268s
err_deque_add_last_drift: 0.266s
err_stack_deque_add_first: 0.260s
err_stack_toarray_string: 0.263s
err_deque_toarray_join: 0.247s
err_stack_ctor_cap: 0.252s
err_stack_static_add: 0.258s
err_deque_reserve_arg: 0.257s
err_stack_empty_int: 0.267s
err_deque_clear_unit: 0.254s
err_string_indexof_arith: 0.255s
err_hashmap_contains_int_key: 0.273s
err_max_clamp_family: 0.272s
err_min_if_condition: 0.250s
err_stack_size_call: 0.257s
err_array_first_optional: 0.253s
err_deque_fill_family: 0.272s
err_array_swap_list_get: 0.271s
err_hashset_add_if_absent: 0.252s
err_string_compare_indexof: 0.243s
err_list_deque_add_last: 0.262s
err_hashmap_remove_keys: 0.250s
err_lambda_pair_arity: 0.252s
err_lambda_param_narrow: 0.253s
err_lambda_iface_callback: 0.304s
err_lambda_not_function: 0.255s
err_lambda_opt_thunk: 0.269s
err_lambda_deque_return: 0.274s
err_lambda_stack_nested: 0.282s
err_lambda_max_by: 0.273s
err_lambda_clamp_pipeline: 0.284s
err_lambda_pick_zero: 0.275s
err_infer_witness_trio: 0.255s
err_infer_forin_generic: 0.240s
err_infer_min_max_fuse: 0.269s
err_infer_map_lookup: 0.264s
err_infer_list_putget: 0.273s
err_infer_nested_container: 0.295s
err_infer_stack_ctor: 0.263s
err_infer_map_contains: 0.271s
err_infer_hof_param: 0.261s
```

统计：count 59 · sum 15.695 s · mean 0.266 s · median 0.264 s · min 0.240 / max 0.304 s。

## 三分核对（vs v12-F1-L 63/100）：−5 / +1（59 = 63 − 5 + 1，集合闭合 ✓）

diff（v12 名单 `results/v12_official_passes.txt` + err_lambda_max_by ↔ v14 名单）：

| 方向 | 用例 | 归因（假说，待验证） |
|---|---|---|
| − | err_abs_bool_helper | F1 族：v12 相对 v11 找回的 4 个 String/helper 之一 |
| − | err_abs_to_string | 同上 |
| − | err_arraylist_get_throw_str | 同上 |
| − | err_deque_capacity_string | 同上 |
| − | err_array_last_abs | F1 第二收益（Array.last + abs 组合形态） |
| + | err_stack_toarray_string | 窄 recovery 单点收益兑现（见下） |

## 关键结论

1. **丢失 5 例 = 恰为 v12 相对 v11 的全部 +5**（v12-F1-only 记录：「v12 独有
   5 = 4 个 String/helper 找回（abs_bool_helper/abs_to_string/get_throw_str/
   capacity_string）+ err_array_last_abs」）——v14 的 patch 0-8 把 F1 在隐藏集
   上的增益**全部清零**，F1 族是本次回退的完整载体。
2. **err_stack_toarray_string 通过 = v12-F1-L 预留判别标尺兑现**：该例 v11
   （全 recovery）独有、两个无 recovery 的 v12 变体均无；v14 不含全 recovery，
   但 Patch 5 的 LetRhsRecoverable（模型 BFS ≤32 状态）恰是「窄 recovery 单点
   收益」提交方向——v12-F1-L 记录原句「narrow-recovery 保留 stack_toarray_
   string 单点收益成为提交 3 候选方向」应验。recovery 归因确认：窄 recovery
   拿得到该例，且无 v11 全 recovery 的 −4 连带损失。
3. **5 例均不在本地 wrong/wrong2**（本地集 + official-reference + reference-
   upstream 全搜零命中）——本地 100/100 门禁对这 6 个用例（5 丢失 + 1 新增）
   零区分力，隐藏集变体与本地集来源不同。

## 回退根因（假说，未证实）

- v14 相对 v12-F1-L 唯一改动判定路径的 patch 是 **Patch 5**（激活：let-decl
  裸标识符 RHS 的 defer/fire 重锚定，LetRhsRecoverable + Dead 提前 fire，
  Patch 5 文档「生产路径唯一行为变化」）；Patch 6 与 v12-F1-L 行为字节等价
  （仅注释），Patch 1-4 shadow/无行为变化，Patch 7-8 打包性能。
- F1 族（first/last 字段 + abs/toString 恢复路径）与 let-RHS 标识符判定强相关
  → 最大嫌疑 = Patch 5 在隐藏变体上把 F1 家族的 gold 锚点 defer 过头或提前
  fire。**未证实**：需本地重建这 5 类形态（官方 typechecker 打标差分）定位。
- 假设官方隐藏集跨提交不变（59 = 63 − 5 + 1 精确闭合支持；官网只报通过名单，
  无法直接验证）。

## 决策（Plan 13：net < 0）

- **v14-AORTA 不升基线；v12-F1-L 63/100 保持官方基线**。
- 机制净账 = −4（F1 族 5 例回退 − 窄 recovery 1 例收益）。
- 下一步候选（待用户指示）：
  1. 重建 5 例形态差分（abs/toString/get_throw/capacity/last 族 × let-RHS
     标识符），官方 typechecker 打标定位 Patch 5 回归位点；
  2. 若确认 Patch 5 回归 → v15 = v12-F1-L + 修正版 Patch 5（或回退其 let-RHS
     重锚定部分，保留其余激活）。
