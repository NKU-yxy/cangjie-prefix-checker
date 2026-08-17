# context-API 差分 fuzz 报告

- 生成用例：475
- 偏差数：34
- 规则校验（官方 wrong/ 首错误索引）：50/50

## 偏差统计
- `HashMap` / `arity_long`: 6
- `ArrayList` / `arity_long`: 5
- `HashSet` / `arity_long`: 5
- `ArrayStack` / `arity_long`: 5
- `ArrayDeque` / `arity_long`: 5
- `Array` / `arity_long`: 4
- `String` / `arity_long`: 4

## 前 60 条偏差明细
- Array.clone arity_long: gt=91 solution=92 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Array<Int64> -> [E_CHECK_TOO_MANY_POSITIONA)
- Array.reverse arity_long: gt=91 solution=92 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS][)
- Array.first arity_long: gt=91 solution=92 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Optional<Int64>)
- Array.last arity_long: gt=91 solution=92 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Optional<Int64>)
- ArrayList.isEmpty arity_long: gt=92 solution=93 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Bool -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS][)
- ArrayList.clear arity_long: gt=92 solution=93 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS][)
- ArrayList.clone arity_long: gt=92 solution=93 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> ArrayList<Int64> -> [E_CHECK_TOO_MANY_POSIT)
- ArrayList.reverse arity_long: gt=92 solution=93 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS][)
- ArrayList.toArray arity_long: gt=92 solution=93 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Array<Int64> -> [E_CHECK_TOO_MANY_POSITIONA)
- HashMap.size arity_long: gt=93 solution=94 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- HashMap.capacity arity_long: gt=93 solution=94 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- HashMap.keys arity_long: gt=93 solution=94 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> KeysView<String> -> [E_CHECK_TOO_MANY_POSIT)
- HashMap.values arity_long: gt=93 solution=94 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> ValuesView<Int64> -> [E_CHECK_TOO_MANY_POSI)
- HashMap.clone arity_long: gt=93 solution=94 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> HashMap<String, Int64> -> [E_CHECK_TOO_MANY)
- HashMap.clear arity_long: gt=93 solution=94 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS][)
- HashSet.size arity_long: gt=86 solution=87 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- HashSet.capacity arity_long: gt=86 solution=87 (oracle: TypeCheckError: [E_SYNTH_NOT_CALLABLE][synth] not callable Int64)
- HashSet.clone arity_long: gt=86 solution=87 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> HashSet<Int64> -> [E_CHECK_TOO_MANY_POSITIO)
- HashSet.toArray arity_long: gt=86 solution=87 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Array<Int64> -> [E_CHECK_TOO_MANY_POSITIONA)
- HashSet.clear arity_long: gt=86 solution=87 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS][)
- String.isEmpty arity_long: gt=82 solution=83 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Bool -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS][)
- String.clone arity_long: gt=82 solution=83 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> String -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS)
- String.trimAscii arity_long: gt=83 solution=84 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> String -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS)
- String.hashCode arity_long: gt=82 solution=83 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Int64 -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS])
- ArrayStack.isEmpty arity_long: gt=88 solution=89 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Bool -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS][)
- ArrayStack.peek arity_long: gt=88 solution=89 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Optional<Int64> -> [E_CHECK_TOO_MANY_POSITI)
- ArrayStack.remove arity_long: gt=88 solution=89 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Optional<Int64> -> [E_CHECK_TOO_MANY_POSITI)
- ArrayStack.clear arity_long: gt=88 solution=89 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS][)
- ArrayStack.toArray arity_long: gt=88 solution=89 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Array<Int64> -> [E_CHECK_TOO_MANY_POSITIONA)
- ArrayDeque.isEmpty arity_long: gt=90 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Bool -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS][)
- ArrayDeque.removeFirst arity_long: gt=91 solution=92 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Optional<Int64> -> [E_CHECK_TOO_MANY_POSITI)
- ArrayDeque.removeLast arity_long: gt=91 solution=92 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Optional<Int64> -> [E_CHECK_TOO_MANY_POSITI)
- ArrayDeque.clear arity_long: gt=90 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Unit -> [E_CHECK_TOO_MANY_POSITIONAL_ARGS][)
- ArrayDeque.toArray arity_long: gt=90 solution=91 (oracle: TypeCheckError: [E_CHECK_NO_MATCHING_CTOR][check] no matching call candidate (1 tried); failures:
candidate[1] () -> Array<Int64> -> [E_CHECK_TOO_MANY_POSITIONA)