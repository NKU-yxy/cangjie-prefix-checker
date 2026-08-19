# Patch 3: Valid-Program Prefix Corpus — 扫描报告

- 语料规模：**1497** 个官方 ACCEPT 程序（members 106 个，语法节点 41 个，泛型来源 10 个）
- 过早拒绝（early fire）：**244** 个程序
- 语义 cell 聚类：**7** 个

## 门禁检查

- 每 member ≥8 种 use shapes：✅（min=0；官方 error 成员豁免 3 个）
- 语法节点每类 ≥2 嵌套上下文：✅
- 全部程序官方 ACCEPT：✅（按构造，生成时过滤）
- 语料规模：1497；过早拒绝程序数：244

## 语义 cell 聚类（fire 事件）

| cell | 计数 | 示例程序 | message |
|---|---|---|---|
| local/value/statement recv=- | 237 | Array__size__array_element, Array__size__index_result, Array__size__array_repeat | `array element type mismatch` |
| method/value/member_sel recv=HashSet | 2 | HashSet__add__method_ref, HashSet__remove__method_ref | `ambiguous overloaded member reference` |
| method/value/member_sel recv=ArrayList | 1 | ArrayList__add__method_ref | `ambiguous overloaded member reference` |
| method/value/member_sel recv=HashMap | 1 | HashMap__remove__method_ref | `ambiguous overloaded member reference` |
| function/call/assign_rhs recv=- | 1 | global__clamp__binary | `argument type mismatch` |
| primitive/value/statement recv=- | 1 | syntax__array_index_literal | `variable initializer type mismatch` |
| unknown/value/member_sel recv=0 | 1 | generic__g_expected_ret | `unknown receiver type` |

## 过早拒绝程序清单（Patch 4 输入）

| id | fire@token | min_fire@token | shape |
|---|---|---|---|
| Array__size__array_element | 32 | 32 | array_element |
| Array__size__index_result | 32 | 32 | index_result |
| Array__size__array_repeat | 32 | 32 | array_repeat |
| Array__first__array_element | 34 | 34 | array_element |
| Array__first__index_result | 34 | 34 | index_result |
| Array__first__array_repeat | 34 | 34 | array_repeat |
| Array__last__array_element | 34 | 34 | array_element |
| Array__last__index_result | 34 | 34 | index_result |
| Array__last__array_repeat | 34 | 34 | array_repeat |
| Array__get__array_element | 34 | 34 | array_element |
| Array__get__index_result | 34 | 34 | index_result |
| Array__get__array_repeat | 34 | 34 | array_repeat |
| Array__fill__array_element | 31 | 31 | array_element |
| Array__fill__index_result | 31 | 31 | index_result |
| Array__fill__array_repeat | 31 | 31 | array_repeat |
| Array__swap__array_element | 31 | 31 | array_element |
| Array__swap__index_result | 31 | 31 | index_result |
| Array__swap__array_repeat | 31 | 31 | array_repeat |
| Array__reverse__array_element | 31 | 31 | array_element |
| Array__reverse__index_result | 31 | 31 | index_result |
| Array__reverse__array_repeat | 31 | 31 | array_repeat |
| Array__indexOf__array_element | 34 | 34 | array_element |
| Array__indexOf__index_result | 34 | 34 | index_result |
| Array__indexOf__array_repeat | 34 | 34 | array_repeat |
| ArrayList__size__array_element | 27 | 27 | array_element |
| ArrayList__size__index_result | 27 | 27 | index_result |
| ArrayList__size__array_repeat | 27 | 27 | array_repeat |
| ArrayList__capacity__array_element | 27 | 27 | array_element |
| ArrayList__capacity__index_result | 27 | 27 | index_result |
| ArrayList__capacity__array_repeat | 27 | 27 | array_repeat |
| ArrayList__isEmpty__array_element | 27 | 27 | array_element |
| ArrayList__isEmpty__index_result | 27 | 27 | index_result |
| ArrayList__isEmpty__array_repeat | 27 | 27 | array_repeat |
| ArrayList__add__array_element | 26 | 26 | array_element |
| ArrayList__add__index_result | 26 | 26 | index_result |
| ArrayList__add__method_ref | 30 | 30 | method_ref |
| ArrayList__add__array_repeat | 26 | 26 | array_repeat |
| ArrayList__remove__array_element | 26 | 26 | array_element |
| ArrayList__remove__index_result | 26 | 26 | index_result |
| ArrayList__remove__array_repeat | 26 | 26 | array_repeat |
| ArrayList__clear__array_element | 26 | 26 | array_element |
| ArrayList__clear__index_result | 26 | 26 | index_result |
| ArrayList__clear__array_repeat | 26 | 26 | array_repeat |
| ArrayList__reserve__array_element | 26 | 26 | array_element |
| ArrayList__reserve__index_result | 26 | 26 | index_result |
| ArrayList__reserve__array_repeat | 26 | 26 | array_repeat |
| ArrayList__reverse__array_element | 26 | 26 | array_element |
| ArrayList__reverse__index_result | 26 | 26 | index_result |
| ArrayList__reverse__array_repeat | 26 | 26 | array_repeat |
| ArrayList__toArray__array_element | 28 | 28 | array_element |
| ArrayList__toArray__index_result | 28 | 28 | index_result |
| ArrayList__toArray__array_repeat | 28 | 28 | array_repeat |
| ArrayList__get__array_element | 29 | 29 | array_element |
| ArrayList__get__index_result | 29 | 29 | index_result |
| ArrayList__get__array_repeat | 29 | 29 | array_repeat |
| HashMap__size__array_element | 31 | 31 | array_element |
| HashMap__size__index_result | 31 | 31 | index_result |
| HashMap__size__array_repeat | 31 | 31 | array_repeat |
| HashMap__capacity__array_element | 31 | 31 | array_element |
| HashMap__capacity__index_result | 31 | 31 | index_result |
| HashMap__capacity__array_repeat | 31 | - | array_repeat |
| HashMap__get__array_element | 33 | - | array_element |
| HashMap__get__index_result | 33 | - | index_result |
| HashMap__get__array_repeat | 33 | - | array_repeat |
| HashMap__add__array_element | 30 | - | array_element |
| HashMap__add__index_result | 30 | - | index_result |
| HashMap__add__array_repeat | 30 | - | array_repeat |
| HashMap__remove__array_element | 30 | - | array_element |
| HashMap__remove__index_result | 30 | - | index_result |
| HashMap__remove__method_ref | 33 | - | method_ref |
| HashMap__remove__array_repeat | 30 | - | array_repeat |
| HashMap__addIfAbsent__array_element | 31 | - | array_element |
| HashMap__addIfAbsent__index_result | 31 | - | index_result |
| HashMap__addIfAbsent__array_repeat | 31 | - | array_repeat |
| HashMap__keys__array_element | 33 | - | array_element |
| HashMap__keys__index_result | 33 | - | index_result |
| HashMap__keys__array_repeat | 33 | - | array_repeat |
| HashMap__values__array_element | 34 | - | array_element |
| HashMap__values__index_result | 34 | - | index_result |
| HashMap__values__array_repeat | 34 | - | array_repeat |
| HashMap__clear__array_element | 30 | - | array_element |
| HashMap__clear__index_result | 30 | - | index_result |
| HashMap__clear__array_repeat | 30 | - | array_repeat |
| HashMap__replace__array_element | 30 | - | array_element |
| HashMap__replace__index_result | 30 | - | index_result |
| HashMap__replace__array_repeat | 30 | - | array_repeat |
| HashMap__contains__array_element | 31 | - | array_element |
| HashMap__contains__index_result | 31 | - | index_result |
| HashMap__contains__array_repeat | 31 | - | array_repeat |
| HashSet__size__array_element | 25 | - | array_element |
| HashSet__size__index_result | 25 | - | index_result |
| HashSet__size__array_repeat | 25 | - | array_repeat |
| HashSet__capacity__array_element | 25 | - | array_element |
| HashSet__capacity__index_result | 25 | - | index_result |
| HashSet__capacity__array_repeat | 25 | - | array_repeat |
| HashSet__add__array_element | 25 | - | array_element |
| HashSet__add__index_result | 25 | - | index_result |
| HashSet__add__method_ref | 27 | - | method_ref |
| HashSet__add__array_repeat | 25 | - | array_repeat |
| HashSet__contains__array_element | 25 | - | array_element |
| HashSet__contains__index_result | 25 | - | index_result |
| HashSet__contains__array_repeat | 25 | - | array_repeat |
| HashSet__remove__array_element | 25 | - | array_element |
| HashSet__remove__index_result | 25 | - | index_result |
| HashSet__remove__method_ref | 27 | - | method_ref |
| HashSet__remove__array_repeat | 25 | - | array_repeat |
| HashSet__reserve__array_element | 24 | - | array_element |
| HashSet__reserve__index_result | 24 | - | index_result |
| HashSet__reserve__array_repeat | 24 | - | array_repeat |
| HashSet__toArray__array_element | 25 | - | array_element |
| HashSet__toArray__index_result | 25 | - | index_result |
| HashSet__toArray__array_repeat | 25 | - | array_repeat |
| HashSet__clear__array_element | 24 | - | array_element |
| HashSet__clear__index_result | 24 | - | index_result |
| HashSet__clear__array_repeat | 24 | - | array_repeat |
| String__size__array_element | 23 | - | array_element |
| String__size__index_result | 23 | - | index_result |
| String__size__array_repeat | 23 | - | array_repeat |
| String__isEmpty__array_element | 23 | - | array_element |
| String__isEmpty__index_result | 23 | - | index_result |
| String__isEmpty__array_repeat | 23 | - | array_repeat |
| String__startsWith__array_element | 23 | - | array_element |
| String__startsWith__index_result | 23 | - | index_result |
| String__startsWith__array_repeat | 23 | - | array_repeat |
| String__endsWith__array_element | 23 | - | array_element |
| String__endsWith__index_result | 23 | - | index_result |
| String__endsWith__array_repeat | 23 | - | array_repeat |
| String__contains__array_element | 23 | - | array_element |
| String__contains__index_result | 23 | - | index_result |
| String__contains__array_repeat | 23 | - | array_repeat |
| String__get__array_element | 25 | - | array_element |
| String__get__index_result | 25 | - | index_result |
| String__get__array_repeat | 25 | - | array_repeat |
| String__hashCode__array_element | 23 | - | array_element |
| String__hashCode__index_result | 23 | - | index_result |
| String__hashCode__array_repeat | 23 | - | array_repeat |
| String__compare__array_element | 23 | - | array_element |
| String__compare__index_result | 23 | - | index_result |
| String__compare__array_repeat | 23 | - | array_repeat |
| String__indexOf__array_element | 25 | - | array_element |
| String__indexOf__index_result | 25 | - | index_result |
| String__indexOf__array_repeat | 25 | - | array_repeat |
| Optional__getOrThrow__array_element | 44 | - | array_element |
| Optional__getOrThrow__index_result | 44 | - | index_result |
| Optional__getOrThrow__array_repeat | 44 | - | array_repeat |
| Optional__isSome__array_element | 44 | - | array_element |
| Optional__isSome__index_result | 44 | - | index_result |
| Optional__isSome__array_repeat | 44 | - | array_repeat |
| Optional__isNone__array_element | 44 | - | array_element |
| Optional__isNone__index_result | 44 | - | index_result |
| Optional__isNone__array_repeat | 44 | - | array_repeat |
| Optional__orElse__array_element | 44 | - | array_element |
| Optional__orElse__index_result | 44 | - | index_result |
| Optional__orElse__array_repeat | 44 | - | array_repeat |
| KeysView__size__array_element | 31 | - | array_element |
| KeysView__size__index_result | 31 | - | index_result |
| KeysView__size__array_repeat | 31 | - | array_repeat |
| ValuesView__size__array_element | 32 | - | array_element |
| ValuesView__size__index_result | 32 | - | index_result |
| ValuesView__size__array_repeat | 32 | - | array_repeat |
| Range__size__array_element | 28 | - | array_element |
| Range__size__index_result | 28 | - | index_result |
| Range__size__array_repeat | 28 | - | array_repeat |
| ArrayStack__size__array_element | 29 | - | array_element |
| ArrayStack__size__index_result | 29 | - | index_result |
| ArrayStack__size__array_repeat | 29 | - | array_repeat |
| ArrayStack__capacity__array_element | 29 | - | array_element |
| ArrayStack__capacity__index_result | 29 | - | index_result |
| ArrayStack__capacity__array_repeat | 29 | - | array_repeat |
| ArrayStack__isEmpty__array_element | 29 | - | array_element |
| ArrayStack__isEmpty__index_result | 29 | - | index_result |
| ArrayStack__isEmpty__array_repeat | 29 | - | array_repeat |
| ArrayStack__add__array_element | 28 | - | array_element |
| ArrayStack__add__index_result | 28 | - | index_result |
| ArrayStack__add__array_repeat | 28 | - | array_repeat |
| ArrayStack__peek__array_element | 31 | - | array_element |
| ArrayStack__peek__index_result | 31 | - | index_result |
| ArrayStack__peek__array_repeat | 31 | - | array_repeat |
| ArrayStack__remove__array_element | 31 | - | array_element |
| ArrayStack__remove__index_result | 31 | - | index_result |
| ArrayStack__remove__array_repeat | 31 | - | array_repeat |
| ArrayStack__clear__array_element | 28 | - | array_element |
| ArrayStack__clear__index_result | 28 | - | index_result |
| ArrayStack__clear__array_repeat | 28 | - | array_repeat |
| ArrayStack__reserve__array_element | 28 | - | array_element |
| ArrayStack__reserve__index_result | 28 | - | index_result |
| ArrayStack__reserve__array_repeat | 28 | - | array_repeat |
| ArrayStack__toArray__array_element | 30 | - | array_element |
| ArrayStack__toArray__index_result | 30 | - | index_result |
| ArrayStack__toArray__array_repeat | 30 | - | array_repeat |
| ArrayDeque__size__array_element | 29 | - | array_element |
| ArrayDeque__size__index_result | 29 | - | index_result |
| ArrayDeque__size__array_repeat | 29 | - | array_repeat |
| ArrayDeque__capacity__array_element | 29 | - | array_element |
| ArrayDeque__capacity__index_result | 29 | - | index_result |
| ArrayDeque__capacity__array_repeat | 29 | - | array_repeat |
| ArrayDeque__isEmpty__array_element | 29 | - | array_element |
| ArrayDeque__isEmpty__index_result | 29 | - | index_result |
| ArrayDeque__isEmpty__array_repeat | 29 | - | array_repeat |
| ArrayDeque__addFirst__array_element | 28 | - | array_element |
| ArrayDeque__addFirst__index_result | 28 | - | index_result |
| ArrayDeque__addFirst__array_repeat | 28 | - | array_repeat |
| ArrayDeque__addLast__array_element | 28 | - | array_element |
| ArrayDeque__addLast__index_result | 28 | - | index_result |
| ArrayDeque__addLast__array_repeat | 28 | - | array_repeat |
| ArrayDeque__removeFirst__array_element | 31 | - | array_element |
| ArrayDeque__removeFirst__index_result | 31 | - | index_result |
| ArrayDeque__removeFirst__array_repeat | 31 | - | array_repeat |
| ArrayDeque__removeLast__array_element | 31 | - | array_element |
| ArrayDeque__removeLast__index_result | 31 | - | index_result |
| ArrayDeque__removeLast__array_repeat | 31 | - | array_repeat |
| ArrayDeque__clear__array_element | 28 | - | array_element |
| ArrayDeque__clear__index_result | 28 | - | index_result |
| ArrayDeque__clear__array_repeat | 28 | - | array_repeat |
| ArrayDeque__reserve__array_element | 28 | - | array_element |
| ArrayDeque__reserve__index_result | 28 | - | index_result |
| ArrayDeque__reserve__array_repeat | 28 | - | array_repeat |
| ArrayDeque__toArray__array_element | 30 | - | array_element |
| ArrayDeque__toArray__index_result | 30 | - | index_result |
| ArrayDeque__toArray__array_repeat | 30 | - | array_repeat |
| Stack__add__array_element | 28 | - | array_element |
| Stack__add__index_result | 28 | - | index_result |
| Stack__add__array_repeat | 28 | - | array_repeat |
| Stack__peek__array_element | 31 | - | array_element |
| Stack__peek__index_result | 31 | - | index_result |
| Stack__peek__array_repeat | 31 | - | array_repeat |
| Stack__remove__array_element | 31 | - | array_element |
| Stack__remove__index_result | 31 | - | index_result |
| Stack__remove__array_repeat | 31 | - | array_repeat |
| Deque__addFirst__array_element | 28 | - | array_element |
| Deque__addFirst__index_result | 28 | - | index_result |
| Deque__addFirst__array_repeat | 28 | - | array_repeat |
| Deque__addLast__array_element | 28 | - | array_element |
| Deque__addLast__index_result | 28 | - | index_result |
| Deque__addLast__array_repeat | 28 | - | array_repeat |
| Deque__removeFirst__array_element | 31 | - | array_element |
| Deque__removeFirst__index_result | 31 | - | index_result |
| Deque__removeFirst__array_repeat | 31 | - | array_repeat |
| Deque__removeLast__array_element | 31 | - | array_element |
| Deque__removeLast__index_result | 31 | - | index_result |
| Deque__removeLast__array_repeat | 31 | - | array_repeat |
| global__clamp__binary | 30 | - | binary |
| syntax__array_index_literal | 19 | - | array_index_literal |
| generic__g_expected_ret | 22 | - | g_expected_ret |
