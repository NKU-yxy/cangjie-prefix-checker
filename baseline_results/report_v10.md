# context-API 差分 fuzz 报告

- 生成用例：540
- 偏差数：171
- 规则校验（官方 wrong/ 首错误索引）：30/50

## 偏差统计
- `HashMap` / `opt_method_on_plain`: 14
- `HashMap` / `arity_long`: 12
- `HashMap` / `missing_member`: 12
- `HashMap` / `reassign_type`: 12
- `ArrayList` / `field_as_method`: 10
- `ArrayList` / `opt_method_on_plain`: 10
- `ArrayList` / `missing_member`: 9
- `ArrayList` / `reassign_type`: 9
- `ArrayList` / `arity_long`: 8
- `HashMap` / `arity_short`: 8
- `global` / `g_arity_long`: 7
- `HashMap` / `arg_type`: 6
- `HashMap` / `named_arg`: 6
- `ArrayList` / `arity_short`: 5
- `global` / `g_arg`: 5
- `global` / `g_arg_mixed`: 5
- `ArrayList` / `arg_type`: 4
- `ArrayList` / `named_arg`: 4
- `ArrayList` / `ctor_arg`: 4
- `HashMap` / `ret_type`: 4
- `HashMap` / `ctor_arg`: 3
- `global` / `g_ret`: 3
- `Array` / `arity_long`: 2
- `Array` / `reassign_type`: 2
- `global` / `g_rest_elem`: 2
- `global` / `g_arity_short`: 2
- `ArrayList` / `ret_type`: 1
- `String` / `arity_long`: 1
- `String` / `ret_type`: 1

## 前 60 条偏差明细
- Array.swap arity_long: gt=95 solution=92 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64, Int64) -> Unit -> [E_CHECK_TOO_MANY_POSIT)
- Array.swap reassign_type: gt=98 solution=94 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Unit)
- Array.slice arity_long: gt=95 solution=92 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64, Int64) -> Array<Int64> -> [E_CHECK_TOO_MA)
- Array.slice reassign_type: gt=98 solution=94 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Array<Int64>)
- ArrayList.isEmpty arity_long: gt=92 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Bool -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS][)
- ArrayList.isEmpty ret_type: gt=98 solution=63 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected Int64, got Bool)
- ArrayList.isEmpty field_as_method: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- ArrayList.isEmpty missing_member: gt=96 solution=63 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member first on ArrayList<Int64>)
- ArrayList.isEmpty opt_method_on_plain: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on ArrayList<Int64>)
- ArrayList.isEmpty reassign_type: gt=94 solution=63 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Bool)
- ArrayList.add arg_type: gt=93 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (4 tried); failures:
candidate[1] (Int64) -> Unit -> [E_SUBTYPE_MISMATCH][subtype] )
- ArrayList.add arity_short: gt=91 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (4 tried); failures:
candidate[1] (Int64) -> Unit -> [E_CHECK_ARG_MISMATCH][check] )
- ArrayList.add named_arg: gt=92 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (4 tried); failures:
candidate[1] (Int64) -> Unit -> [E_CHECK_UNKNOWN_NAMED_ARG][ch)
- ArrayList.add field_as_method: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- ArrayList.add missing_member: gt=96 solution=63 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member first on ArrayList<Int64>)
- ArrayList.add opt_method_on_plain: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on ArrayList<Int64>)
- ArrayList.add ctor_arg: gt=102 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (3 tried); failures:
candidate[1] () -> ArrayList<Int64> -> [E_CHECK_TOO_MANY_POSIT)
- ArrayList.add reassign_type: gt=96 solution=63 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Unit)
- ArrayList.add arity_short: gt=91 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (4 tried); failures:
candidate[1] (Int64) -> Unit -> [E_CHECK_ARG_MISMATCH][check] )
- ArrayList.add field_as_method: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- ArrayList.add opt_method_on_plain: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on ArrayList<Int64>)
- ArrayList.remove arg_type: gt=93 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64) -> Unit -> [E_SUBTYPE_MISMATCH][subtype] )
- ArrayList.remove arity_short: gt=91 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64) -> Unit -> [E_CHECK_ARG_MISMATCH][check] )
- ArrayList.remove arity_long: gt=93 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64) -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_A)
- ArrayList.remove named_arg: gt=92 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64) -> Unit -> [E_CHECK_UNKNOWN_NAMED_ARG][ch)
- ArrayList.remove field_as_method: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- ArrayList.remove missing_member: gt=96 solution=63 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member first on ArrayList<Int64>)
- ArrayList.remove opt_method_on_plain: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on ArrayList<Int64>)
- ArrayList.remove ctor_arg: gt=102 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (3 tried); failures:
candidate[1] () -> ArrayList<Int64> -> [E_CHECK_TOO_MANY_POSIT)
- ArrayList.remove reassign_type: gt=96 solution=63 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Unit)
- ArrayList.clear arity_long: gt=92 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS][)
- ArrayList.clear field_as_method: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- ArrayList.clear missing_member: gt=96 solution=63 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member first on ArrayList<Int64>)
- ArrayList.clear opt_method_on_plain: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on ArrayList<Int64>)
- ArrayList.clear reassign_type: gt=94 solution=63 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Unit)
- ArrayList.clone arity_long: gt=92 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> ArrayList<Int64> -> [E_CHECK_TOO_MANY_POSIT)
- ArrayList.clone field_as_method: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- ArrayList.clone missing_member: gt=96 solution=63 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member first on ArrayList<Int64>)
- ArrayList.clone opt_method_on_plain: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on ArrayList<Int64>)
- ArrayList.clone reassign_type: gt=94 solution=63 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got ArrayList<Int64>)
- ArrayList.reserve arg_type: gt=93 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64) -> Unit -> [E_SUBTYPE_MISMATCH][subtype] )
- ArrayList.reserve arity_short: gt=91 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64) -> Unit -> [E_CHECK_ARG_MISMATCH][check] )
- ArrayList.reserve arity_long: gt=93 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64) -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_A)
- ArrayList.reserve named_arg: gt=92 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64) -> Unit -> [E_CHECK_UNKNOWN_NAMED_ARG][ch)
- ArrayList.reserve field_as_method: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- ArrayList.reserve missing_member: gt=96 solution=63 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member first on ArrayList<Int64>)
- ArrayList.reserve opt_method_on_plain: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on ArrayList<Int64>)
- ArrayList.reserve ctor_arg: gt=102 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (3 tried); failures:
candidate[1] () -> ArrayList<Int64> -> [E_CHECK_TOO_MANY_POSIT)
- ArrayList.reserve reassign_type: gt=96 solution=63 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Unit)
- ArrayList.reverse arity_long: gt=92 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS][)
- ArrayList.reverse field_as_method: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- ArrayList.reverse missing_member: gt=96 solution=63 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member first on ArrayList<Int64>)
- ArrayList.reverse opt_method_on_plain: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on ArrayList<Int64>)
- ArrayList.reverse reassign_type: gt=94 solution=63 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Unit)
- ArrayList.toArray arity_long: gt=92 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Array<Int64> -> [E_CHECK_TOO_MANY_POSITIONA)
- ArrayList.toArray field_as_method: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- ArrayList.toArray missing_member: gt=96 solution=63 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member first on ArrayList<Int64>)
- ArrayList.toArray opt_method_on_plain: gt=97 solution=63 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on ArrayList<Int64>)
- ArrayList.toArray reassign_type: gt=94 solution=63 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Array<Int64>)
- ArrayList.get arg_type: gt=93 solution=63 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64) -> Optional<Int64> -> [E_SUBTYPE_MISMATCH)