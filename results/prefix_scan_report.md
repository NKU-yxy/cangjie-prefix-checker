# Patch 3: Valid-Program Prefix Corpus — 扫描报告

- 语料规模：**1497** 个官方 ACCEPT 程序（members 106 个，语法节点 41 个，泛型来源 10 个）
- 过早拒绝（early fire）：**38** 个程序
- 语义 cell 聚类：**7** 个

## 门禁检查

- 每 member ≥8 种 use shapes：✅（min=0；官方 error 成员豁免 3 个）
- 语法节点每类 ≥2 嵌套上下文：✅
- 全部程序官方 ACCEPT：✅（按构造，生成时过滤）
- 语料规模：1497；过早拒绝程序数：38

## 语义 cell 聚类（fire 事件）

| cell | 计数 | 示例程序 | message |
|---|---|---|---|
| local/value/assign_rhs recv=- | 31 | Array__size__postfix, ArrayList__size__postfix, ArrayList__capacity__postfix | `variable initializer type mismatch` |
| method/value/member_sel recv=HashSet | 2 | HashSet__add__method_ref, HashSet__remove__method_ref | `ambiguous overloaded member reference` |
| method/value/member_sel recv=ArrayList | 1 | ArrayList__add__method_ref | `ambiguous overloaded member reference` |
| method/value/member_sel recv=HashMap | 1 | HashMap__remove__method_ref | `ambiguous overloaded member reference` |
| function/call/assign_rhs recv=- | 1 | global__clamp__binary | `argument type mismatch` |
| primitive/value/statement recv=- | 1 | syntax__array_index_literal | `variable initializer type mismatch` |
| unknown/value/member_sel recv=0 | 1 | generic__g_expected_ret | `unknown receiver type` |

## 过早拒绝程序清单（Patch 4 输入）

| id | fire@token | min_fire@token | shape |
|---|---|---|---|
| Array__size__postfix | 28 | - | postfix |
| ArrayList__size__postfix | 23 | - | postfix |
| ArrayList__capacity__postfix | 23 | - | postfix |
| ArrayList__isEmpty__postfix | 23 | - | postfix |
| ArrayList__add__method_ref | 30 | - | method_ref |
| HashMap__size__postfix | 27 | - | postfix |
| HashMap__capacity__postfix | 27 | - | postfix |
| HashMap__size__read_postfix | 27 | - | read_postfix |
| HashMap__capacity__read_postfix | 27 | - | read_postfix |
| HashMap__remove__method_ref | 33 | - | method_ref |
| HashMap__addIfAbsent__postfix | 27 | - | postfix |
| HashMap__contains__postfix | 27 | - | postfix |
| HashSet__size__postfix | 21 | - | postfix |
| HashSet__capacity__postfix | 21 | - | postfix |
| HashSet__size__read_postfix | 21 | - | read_postfix |
| HashSet__capacity__read_postfix | 21 | - | read_postfix |
| HashSet__add__postfix | 21 | - | postfix |
| HashSet__add__method_ref | 27 | - | method_ref |
| HashSet__contains__postfix | 21 | - | postfix |
| HashSet__remove__postfix | 21 | - | postfix |
| HashSet__remove__method_ref | 27 | - | method_ref |
| Optional__getOrThrow__postfix | 40 | - | postfix |
| Optional__isSome__postfix | 40 | - | postfix |
| Optional__isNone__postfix | 40 | - | postfix |
| Optional__orElse__postfix | 40 | - | postfix |
| KeysView__size__postfix | 27 | - | postfix |
| ValuesView__size__postfix | 28 | - | postfix |
| Range__size__postfix | 24 | - | postfix |
| ArrayStack__size__postfix | 25 | - | postfix |
| ArrayStack__capacity__postfix | 25 | - | postfix |
| ArrayStack__isEmpty__postfix | 25 | - | postfix |
| ArrayDeque__size__postfix | 25 | - | postfix |
| ArrayDeque__capacity__postfix | 25 | - | postfix |
| ArrayDeque__isEmpty__postfix | 25 | - | postfix |
| Collection__size__read_postfix | 23 | - | read_postfix |
| global__clamp__binary | 30 | - | binary |
| syntax__array_index_literal | 19 | - | array_index_literal |
| generic__g_expected_ret | 22 | - | g_expected_ret |
