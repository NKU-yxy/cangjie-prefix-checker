# context-API 差分 fuzz 报告

- 生成用例：540
- 偏差数：107
- 规则校验（官方 wrong/ 首错误索引）：42/50

## 偏差统计
- `HashMap` / `opt_method_on_plain`: 14
- `HashMap` / `arity_long`: 12
- `HashMap` / `missing_member`: 12
- `HashMap` / `reassign_type`: 12
- `HashMap` / `arity_short`: 8
- `global` / `g_arity_long`: 7
- `HashMap` / `arg_type`: 6
- `HashMap` / `named_arg`: 6
- `global` / `g_arg`: 5
- `global` / `g_arg_mixed`: 5
- `HashMap` / `ret_type`: 4
- `HashMap` / `ctor_arg`: 3
- `global` / `g_ret`: 3
- `Array` / `arity_long`: 2
- `Array` / `reassign_type`: 2
- `global` / `g_rest_elem`: 2
- `global` / `g_arity_short`: 2
- `String` / `arity_long`: 1
- `String` / `ret_type`: 1

## 前 60 条偏差明细
- Array.swap arity_long: gt=95 solution=92 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64, Int64) -> Unit -> [E_CHECK_TOO_MANY_POSIT)
- Array.swap reassign_type: gt=98 solution=94 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Unit)
- Array.slice arity_long: gt=95 solution=92 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64, Int64) -> Array<Int64> -> [E_CHECK_TOO_MA)
- Array.slice reassign_type: gt=98 solution=94 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Array<Int64>)
- HashMap.size arity_long: gt=93 solution=85 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- HashMap.size ret_type: gt=98 solution=85 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- HashMap.size missing_member: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member reverse on HashMap<String, Int64>)
- HashMap.size opt_method_on_plain: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on HashMap<String, Int64>)
- HashMap.size reassign_type: gt=95 solution=85 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- HashMap.capacity arity_long: gt=93 solution=85 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- HashMap.capacity ret_type: gt=98 solution=85 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- HashMap.capacity missing_member: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member reverse on HashMap<String, Int64>)
- HashMap.capacity opt_method_on_plain: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on HashMap<String, Int64>)
- HashMap.capacity reassign_type: gt=95 solution=85 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- HashMap.get arg_type: gt=94 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (String) -> Optional<Int64> -> [E_SUBTYPE_MISMATC)
- HashMap.get arity_short: gt=92 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (String) -> Optional<Int64> -> [E_CHECK_ARG_MISMA)
- HashMap.get arity_long: gt=94 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (String) -> Optional<Int64> -> [E_CHECK_TOO_MANY_)
- HashMap.get named_arg: gt=93 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (String) -> Optional<Int64> -> [E_CHECK_UNKNOWN_N)
- HashMap.get missing_member: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member reverse on HashMap<String, Int64>)
- HashMap.get opt_method_on_plain: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on HashMap<String, Int64>)
- HashMap.get reassign_type: gt=97 solution=85 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Optional<Int64>)
- HashMap.add arg_type: gt=94 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (2 tried); failures:
candidate[1] (String, Int64) -> Unit -> [E_SUBTYPE_MISMATCH][s)
- HashMap.add arity_short: gt=94 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (2 tried); failures:
candidate[1] (String, Int64) -> Unit -> [E_CHECK_ARG_MISMATCH])
- HashMap.add arity_long: gt=97 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (2 tried); failures:
candidate[1] (String, Int64) -> Unit -> [E_CHECK_TOO_MANY_POSI)
- HashMap.add named_arg: gt=93 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (2 tried); failures:
candidate[1] (String, Int64) -> Unit -> [E_CHECK_UNKNOWN_NAMED)
- HashMap.add missing_member: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member reverse on HashMap<String, Int64>)
- HashMap.add opt_method_on_plain: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on HashMap<String, Int64>)
- HashMap.add ctor_arg: gt=107 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (4 tried); failures:
candidate[1] () -> HashMap<String, Int64> -> [E_CHECK_TOO_MANY)
- HashMap.add reassign_type: gt=100 solution=85 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Unit)
- HashMap.add arity_short: gt=92 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (2 tried); failures:
candidate[1] (String, Int64) -> Unit -> [E_CHECK_ARG_MISMATCH])
- HashMap.add opt_method_on_plain: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on HashMap<String, Int64>)
- HashMap.remove arg_type: gt=94 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (2 tried); failures:
candidate[1] (String) -> Unit -> [E_SUBTYPE_MISMATCH][subtype])
- HashMap.remove arity_short: gt=92 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (2 tried); failures:
candidate[1] (String) -> Unit -> [E_CHECK_ARG_MISMATCH][check])
- HashMap.remove arity_long: gt=94 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (2 tried); failures:
candidate[1] (String) -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_)
- HashMap.remove named_arg: gt=93 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (2 tried); failures:
candidate[1] (String) -> Unit -> [E_CHECK_UNKNOWN_NAMED_ARG][c)
- HashMap.remove missing_member: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member reverse on HashMap<String, Int64>)
- HashMap.remove opt_method_on_plain: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on HashMap<String, Int64>)
- HashMap.remove reassign_type: gt=97 solution=85 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Unit)
- HashMap.remove arity_short: gt=92 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (2 tried); failures:
candidate[1] (String) -> Unit -> [E_CHECK_ARG_MISMATCH][check])
- HashMap.remove opt_method_on_plain: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on HashMap<String, Int64>)
- HashMap.addIfAbsent arg_type: gt=96 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (String, Int64) -> Bool -> [E_SUBTYPE_MISMATCH][s)
- HashMap.addIfAbsent arity_short: gt=96 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (String, Int64) -> Bool -> [E_CHECK_ARG_MISMATCH])
- HashMap.addIfAbsent arity_long: gt=99 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (String, Int64) -> Bool -> [E_CHECK_TOO_MANY_POSI)
- HashMap.addIfAbsent ret_type: gt=106 solution=85 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected Int64, got Bool)
- HashMap.addIfAbsent named_arg: gt=95 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (String, Int64) -> Bool -> [E_CHECK_UNKNOWN_NAMED)
- HashMap.addIfAbsent missing_member: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member reverse on HashMap<String, Int64>)
- HashMap.addIfAbsent opt_method_on_plain: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on HashMap<String, Int64>)
- HashMap.addIfAbsent ctor_arg: gt=107 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (4 tried); failures:
candidate[1] () -> HashMap<String, Int64> -> [E_CHECK_TOO_MANY)
- HashMap.addIfAbsent reassign_type: gt=102 solution=85 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Bool)
- HashMap.keys arity_long: gt=93 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> KeysView<String> -> [E_CHECK_TOO_MANY_POSIT)
- HashMap.keys missing_member: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member reverse on HashMap<String, Int64>)
- HashMap.keys opt_method_on_plain: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on HashMap<String, Int64>)
- HashMap.keys reassign_type: gt=95 solution=85 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got KeysView<String>)
- HashMap.values arity_long: gt=93 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> ValuesView<Int64> -> [E_CHECK_TOO_MANY_POSI)
- HashMap.values missing_member: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member reverse on HashMap<String, Int64>)
- HashMap.values opt_method_on_plain: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on HashMap<String, Int64>)
- HashMap.values reassign_type: gt=95 solution=85 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got ValuesView<Int64>)
- HashMap.clone arity_long: gt=93 solution=85 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> HashMap<String, Int64> -> [E_CHECK_TOO_MANY)
- HashMap.clone missing_member: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member reverse on HashMap<String, Int64>)
- HashMap.clone opt_method_on_plain: gt=97 solution=85 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on HashMap<String, Int64>)