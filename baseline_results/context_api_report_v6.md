# context-API 差分 fuzz 报告

- 生成用例：540
- 偏差数：22
- 规则校验（官方 wrong/ 首错误索引）：0/0

## 偏差统计
- `global` / `g_arity_long`: 6
- `global` / `g_arg`: 5
- `global` / `g_arg_mixed`: 5
- `global` / `g_rest_elem`: 2
- `global` / `g_arity_short`: 2
- `global` / `g_ret`: 2

## 前 60 条偏差明细
- println g_arity_long: gt=91 solution=89 (oracle: ParseError: No terminal matches ''' in the current parser context, at line 19 col 13

    println('a', 1)
            ^
Expected one of: 
	* CONTINUE
	* BANG
	*)
- print g_arity_long: gt=91 solution=94 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (6 tried); failures:
candidate[1] (String) -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_)
- print g_arity_long: gt=91 solution=89 (oracle: ParseError: No terminal matches ''' in the current parser context, at line 19 col 11

    print('a', 1)
          ^
Expected one of: 
	* CONTINUE
	* BANG
	* _WH)
- eprint g_arity_long: gt=92 solution=95 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (4 tried); failures:
candidate[1] (String) -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_)
- min g_arg: gt=89 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (T, T, Array<T>) -> T -> [E_SUBTYPE_MISMATCH][sub)
- min g_arg_mixed: gt=89 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (T, T, Array<T>) -> T -> [E_SUBTYPE_MISMATCH][sub)
- min g_rest_elem: gt=97 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (T, T, Array<T>) -> T -> [E_SUBTYPE_MISMATCH][sub)
- min g_arity_short: gt=94 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (T, T, Array<T>) -> T -> [E_CHECK_ARG_MISMATCH][c)
- min g_arity_long: gt=100 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (T, T, Array<T>) -> T -> [E_CHECK_TOO_MANY_POSITI)
- min g_ret: gt=106 solution=96 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (T, T, Array<T>) -> T -> [E_SUBTYPE_MISMATCH][sub)
- max g_arg: gt=89 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (T, T, Array<T>) -> T -> [E_SUBTYPE_MISMATCH][sub)
- max g_arg_mixed: gt=89 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (T, T, Array<T>) -> T -> [E_SUBTYPE_MISMATCH][sub)
- max g_rest_elem: gt=97 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (T, T, Array<T>) -> T -> [E_SUBTYPE_MISMATCH][sub)
- max g_arity_short: gt=94 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (T, T, Array<T>) -> T -> [E_CHECK_ARG_MISMATCH][c)
- max g_arity_long: gt=100 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (T, T, Array<T>) -> T -> [E_CHECK_TOO_MANY_POSITI)
- max g_ret: gt=106 solution=96 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (T, T, Array<T>) -> T -> [E_SUBTYPE_MISMATCH][sub)
- abs g_arg: gt=89 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (2 tried); failures:
candidate[1] (Int64) -> Int64 -> [E_SUBTYPE_MISMATCH][subtype])
- abs g_arg_mixed: gt=89 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (2 tried); failures:
candidate[1] (Int64) -> Int64 -> [E_SUBTYPE_MISMATCH][subtype])
- abs g_arg: gt=89 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (2 tried); failures:
candidate[1] (Int64) -> Int64 -> [E_SUBTYPE_MISMATCH][subtype])
- abs g_arg_mixed: gt=90 solution=None (oracle: TypeCheckError: [E_SUBTYPE_MISMATCH][subtype] expected Unit, got Int64)
- clamp g_arg: gt=89 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Float64, Float64, Float64) -> Float64 -> [E_SUBT)
- clamp g_arg_mixed: gt=90 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] (Float64, Float64, Float64) -> Float64 -> [E_SUBT)