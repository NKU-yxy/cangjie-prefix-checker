# context-API 差分 fuzz 报告

- 生成用例：540
- 偏差数：336
- 规则校验（官方 wrong/ 首错误索引）：44/50

## 偏差统计
- `HashMap` / `opt_method_on_plain`: 14
- `HashMap` / `arity_long`: 12
- `HashMap` / `missing_member`: 12
- `HashMap` / `reassign_type`: 12
- `String` / `arity_long`: 12
- `String` / `field_as_method`: 12
- `String` / `missing_member`: 12
- `String` / `opt_method_on_plain`: 12
- `HashSet` / `opt_method_on_plain`: 11
- `Array` / `index_type`: 10
- `Array` / `field_as_method`: 10
- `Array` / `opt_method_on_plain`: 10
- `String` / `ret_type`: 10
- `Array` / `arity_long`: 9
- `Array` / `missing_member`: 9
- `Array` / `reassign_type`: 9
- `HashSet` / `arity_long`: 9
- `HashSet` / `missing_member`: 9
- `HashSet` / `reassign_type`: 9
- `HashMap` / `arity_short`: 8
- `String` / `reassign_type`: 8
- `String` / `arg_type`: 8
- `String` / `arity_short`: 8
- `String` / `named_arg`: 8
- `String` / `ctor_arg`: 8
- `Array` / `arity_short`: 6
- `HashMap` / `arg_type`: 6
- `HashMap` / `named_arg`: 6
- `HashSet` / `arity_short`: 6
- `global` / `g_arity_long`: 6
- `Array` / `arg_type`: 5
- `Array` / `named_arg`: 5
- `Array` / `ctor_arg`: 5
- `HashSet` / `ret_type`: 5
- `global` / `g_arg`: 5
- `global` / `g_arg_mixed`: 5
- `HashMap` / `ret_type`: 4
- `HashSet` / `arg_type`: 4
- `HashSet` / `named_arg`: 4
- `HashSet` / `ctor_arg`: 4
- `HashMap` / `ctor_arg`: 3
- `global` / `g_rest_elem`: 2
- `global` / `g_arity_short`: 2
- `global` / `g_ret`: 2

## 前 60 条偏差明细
- Array.get arg_type: gt=92 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64) -> Optional<Int64> -> [E_SUBTYPE_MISMATCH)
- Array.get arity_short: gt=90 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64) -> Optional<Int64> -> [E_CHECK_ARG_MISMAT)
- Array.get arity_long: gt=92 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64) -> Optional<Int64> -> [E_CHECK_TOO_MANY_P)
- Array.get named_arg: gt=91 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64) -> Optional<Int64> -> [E_CHECK_UNKNOWN_NA)
- Array.get index_type: gt=96 solution=80 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected Int64, got Bool)
- Array.get field_as_method: gt=96 solution=80 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- Array.get missing_member: gt=95 solution=80 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isEmpty on Array<Int64>)
- Array.get opt_method_on_plain: gt=95 solution=80 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on Array<Int64>)
- Array.get ctor_arg: gt=101 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (3 tried); failures:
candidate[1] (Int64, Int64) -> Array<Int64> -> [E_CHECK_ARG_MI)
- Array.get reassign_type: gt=95 solution=80 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Optional<Int64>)
- Array.fill arg_type: gt=92 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64) -> Unit -> [E_SUBTYPE_MISMATCH][subtype] )
- Array.fill arity_short: gt=90 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64) -> Unit -> [E_CHECK_ARG_MISMATCH][check] )
- Array.fill arity_long: gt=92 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64) -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_A)
- Array.fill named_arg: gt=91 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64) -> Unit -> [E_CHECK_UNKNOWN_NAMED_ARG][ch)
- Array.fill index_type: gt=96 solution=80 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected Int64, got Bool)
- Array.fill field_as_method: gt=96 solution=80 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- Array.fill missing_member: gt=95 solution=80 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isEmpty on Array<Int64>)
- Array.fill opt_method_on_plain: gt=95 solution=80 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on Array<Int64>)
- Array.fill ctor_arg: gt=101 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (3 tried); failures:
candidate[1] (Int64, Int64) -> Array<Int64> -> [E_CHECK_ARG_MI)
- Array.fill reassign_type: gt=95 solution=80 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Unit)
- Array.swap arg_type: gt=92 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64, Int64) -> Unit -> [E_SUBTYPE_MISMATCH][su)
- Array.swap arity_short: gt=92 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64, Int64) -> Unit -> [E_CHECK_ARG_MISMATCH][)
- Array.swap arity_long: gt=95 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64, Int64) -> Unit -> [E_CHECK_TOO_MANY_POSIT)
- Array.swap named_arg: gt=91 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64, Int64) -> Unit -> [E_CHECK_UNKNOWN_NAMED_)
- Array.swap index_type: gt=96 solution=80 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected Int64, got Bool)
- Array.swap field_as_method: gt=96 solution=80 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- Array.swap missing_member: gt=95 solution=80 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isEmpty on Array<Int64>)
- Array.swap opt_method_on_plain: gt=95 solution=80 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on Array<Int64>)
- Array.swap ctor_arg: gt=101 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (3 tried); failures:
candidate[1] (Int64, Int64) -> Array<Int64> -> [E_SUBTYPE_MISM)
- Array.swap reassign_type: gt=98 solution=80 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Unit)
- Array.slice arg_type: gt=92 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64, Int64) -> Array<Int64> -> [E_SUBTYPE_MISM)
- Array.slice arity_short: gt=92 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64, Int64) -> Array<Int64> -> [E_CHECK_ARG_MI)
- Array.slice arity_long: gt=95 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64, Int64) -> Array<Int64> -> [E_CHECK_TOO_MA)
- Array.slice named_arg: gt=91 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Int64, Int64) -> Array<Int64> -> [E_CHECK_UNKNOW)
- Array.slice index_type: gt=96 solution=80 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected Int64, got Bool)
- Array.slice field_as_method: gt=96 solution=80 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- Array.slice missing_member: gt=95 solution=80 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isEmpty on Array<Int64>)
- Array.slice opt_method_on_plain: gt=95 solution=80 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on Array<Int64>)
- Array.slice ctor_arg: gt=101 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (3 tried); failures:
candidate[1] (Int64, Int64) -> Array<Int64> -> [E_SUBTYPE_MISM)
- Array.slice reassign_type: gt=98 solution=80 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Array<Int64>)
- Array.clone arity_long: gt=91 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Array<Int64> -> [E_CHECK_TOO_MANY_POSITIONA)
- Array.clone index_type: gt=96 solution=80 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected Int64, got Bool)
- Array.clone field_as_method: gt=96 solution=80 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- Array.clone missing_member: gt=95 solution=80 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isEmpty on Array<Int64>)
- Array.clone opt_method_on_plain: gt=95 solution=80 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on Array<Int64>)
- Array.clone reassign_type: gt=93 solution=80 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Array<Int64>)
- Array.concat arity_short: gt=90 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Array<Int64>) -> Array<Int64> -> [E_CHECK_ARG_MI)
- Array.concat index_type: gt=96 solution=80 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected Int64, got Bool)
- Array.concat field_as_method: gt=96 solution=80 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- Array.concat opt_method_on_plain: gt=95 solution=80 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on Array<Int64>)
- Array.reverse arity_long: gt=91 solution=80 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS][)
- Array.reverse index_type: gt=96 solution=80 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected Int64, got Bool)
- Array.reverse field_as_method: gt=96 solution=80 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- Array.reverse missing_member: gt=95 solution=80 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isEmpty on Array<Int64>)
- Array.reverse opt_method_on_plain: gt=95 solution=80 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isSome on Array<Int64>)
- Array.reverse reassign_type: gt=93 solution=80 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected String, got Unit)
- Array.first arity_long: gt=91 solution=80 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Optional<Int64>)
- Array.first index_type: gt=96 solution=80 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected Int64, got Bool)
- Array.first field_as_method: gt=96 solution=80 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- Array.first missing_member: gt=95 solution=80 (oracle: TypeCheckError: [E_SYNTH_NO_MEMBER][synth] no member isEmpty on Array<Int64>)