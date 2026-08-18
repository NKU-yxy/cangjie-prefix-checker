# context-API 差分 fuzz 报告

- 生成用例：538
- 偏差数：11
- 规则校验（官方 wrong/ 首错误索引）：50/50

## 偏差统计
- `global` / `g_arity_long`: 4
- `global` / `g_arg_mixed`: 4
- `global` / `g_arg`: 3

## 前 60 条偏差明细
- print g_arity_long: gt=91 solution=94 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (6 tried); failures:
candidate[1] (String) -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_)
- print g_arg: gt=92 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (6 tried); failures:
candidate[1] (String) -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_)
- print g_arg_mixed: gt=92 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (6 tried); failures:
candidate[1] (String) -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_)
- eprint g_arity_long: gt=92 solution=95 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (4 tried); failures:
candidate[1] (String) -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_)
- eprint g_arg: gt=93 solution=92 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (4 tried); failures:
candidate[1] (String) -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_)
- eprint g_arg_mixed: gt=93 solution=92 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (4 tried); failures:
candidate[1] (String) -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_)
- min g_arity_long: gt=103 solution=100 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (T, T, Array<T>) -> T -> [E_CHECK_TOO_MANY_POSITI)
- max g_arity_long: gt=103 solution=100 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (T, T, Array<T>) -> T -> [E_CHECK_TOO_MANY_POSITI)
- abs g_arg_mixed: gt=91 solution=92 (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected Unit, got Int64)
- clamp g_arg: gt=92 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Float64, Float64, Float64) -> Float64 -> [E_SUBT)
- clamp g_arg_mixed: gt=92 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Float64, Float64, Float64) -> Float64 -> [E_SUBT)