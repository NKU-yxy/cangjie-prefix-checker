# Behavioral Context Diff (V15 Patch 2)

- official context: `context_final.json` (106 members probed)
- runtime: `solution`

## Gate: runtime accept/reject == official accept/reject

**FAIL — 21 probe mismatches**

| owner | member | probe | official | runtime |
|-------|--------|-------|----------|---------|
| ArrayList | add | C | ACCEPT () | accept=False fire=30 |
| HashMap | size | B | REJECT (E_SYNTH_NOT_CALLABLE) | accept=True fire=None |
| HashMap | capacity | B | REJECT (E_SYNTH_NOT_CALLABLE) | accept=True fire=None |
| HashMap | size | B | REJECT (E_SYNTH_NOT_CALLABLE) | accept=True fire=None |
| HashMap | size | D | REJECT (E_SYNTH_NOT_CALLABLE) | accept=True fire=None |
| HashMap | capacity | B | REJECT (E_SYNTH_NOT_CALLABLE) | accept=True fire=None |
| HashMap | capacity | D | REJECT (E_SYNTH_NOT_CALLABLE) | accept=True fire=None |
| HashMap | add | C | ACCEPT () | accept=False fire=36 |
| HashMap | remove | C | ACCEPT () | accept=False fire=33 |
| HashSet | size | B | REJECT (E_SYNTH_NOT_CALLABLE) | accept=True fire=None |
| HashSet | capacity | B | REJECT (E_SYNTH_NOT_CALLABLE) | accept=True fire=None |
| HashSet | size | B | REJECT (E_SYNTH_NOT_CALLABLE) | accept=True fire=None |
| HashSet | size | D | REJECT (E_SYNTH_NOT_CALLABLE) | accept=True fire=None |
| HashSet | capacity | B | REJECT (E_SYNTH_NOT_CALLABLE) | accept=True fire=None |
| HashSet | capacity | D | REJECT (E_SYNTH_NOT_CALLABLE) | accept=True fire=None |
| HashSet | add | C | ACCEPT () | accept=False fire=27 |
| HashSet | remove | C | ACCEPT () | accept=False fire=27 |
| <global> | min | B | REJECT (E_CHECK_NO_MATCHING_CTOR) | accept=True fire=None |
| <global> | min | C | REJECT (E_SUBTYPE_MISMATCH) | accept=True fire=None |
| <global> | max | B | REJECT (E_CHECK_NO_MATCHING_CTOR) | accept=True fire=None |
| <global> | max | C | REJECT (E_SUBTYPE_MISMATCH) | accept=True fire=None |

## raw JSON kind vs official behavior kind

| owner | member | raw JSON | official behavior | note |
|-------|--------|----------|-------------------|------|
| Array | first | method | **field** |  |
| Array | last | method | **field** |  |
| ArrayList | of | static_method | **error** | A=E_SYNTH_NO_MEMBER B=E_SYNTH_NO_MEMBER C=E_SYNTH_NO_MEMBER |
| HashMap | size | field+method | **field** |  |
| HashMap | capacity | field+method | **field** |  |
| HashMap | size | field+method | **field** |  |
| HashMap | capacity | field+method | **field** |  |
| HashSet | size | field+method | **field** |  |
| HashSet | capacity | field+method | **field** |  |
| HashSet | size | field+method | **field** |  |
| HashSet | capacity | field+method | **field** |  |
| String | empty | static_field | **callable_field** | A and B both accepted |
| String | fromUtf8 | static_method | **method** |  |
| String | empty | static_method | **callable_field** | A and B both accepted |
| Collection | size | method | **field** |  |
| <global> | println | function | **method** |  |
| <global> | print | function | **method** |  |
| <global> | eprintln | function | **method** |  |
| <global> | eprint | function | **method** |  |
| <global> | min | function | **error** | generic_uninferable A=E_SUBTYPE_MISMATCH B=E_CHECK_NO_MATCHING_CTOR C=E_SUBTYPE_MISMATCH |
| <global> | max | function | **error** | generic_uninferable A=E_SUBTYPE_MISMATCH B=E_CHECK_NO_MATCHING_CTOR C=E_SUBTYPE_MISMATCH |
| <global> | abs | function | **method** |  |
| <global> | clamp | function | **method** |  |

23 members where official behavior differs from the raw JSON grouping (all listed above).

## runtime kind vs official behavior kind

| owner | member | runtime kind | official behavior | match |
|-------|--------|--------------|-------------------|-------|
| Array | size | field | field | yes |
| Array | get | method | method | yes |
| Array | fill | method | method | yes |
| Array | swap | method | method | yes |
| Array | slice | method | method | yes |
| Array | clone | method | method | yes |
| Array | concat | method | method | yes |
| Array | reverse | method | method | yes |
| Array | first | field (F1 moved) | field | yes |
| Array | last | field (F1 moved) | field | yes |
| Array | indexOf | method | method | yes |
| ArrayList | size | field | field | yes |
| ArrayList | capacity | field | field | yes |
| ArrayList | isEmpty | method | method | yes |
| ArrayList | add | method | method | yes |
| ArrayList | remove | method | method | yes |
| ArrayList | clear | method | method | yes |
| ArrayList | clone | method | method | yes |
| ArrayList | reserve | method | method | yes |
| ArrayList | reverse | method | method | yes |
| ArrayList | toArray | method | method | yes |
| ArrayList | get | method | method | yes |
| ArrayList | of | static_method | error | **NO** |
| HashMap | size | field+method | field | **NO** |
| HashMap | capacity | field+method | field | **NO** |
| HashMap | size | field+method | field | **NO** |
| HashMap | capacity | field+method | field | **NO** |
| HashMap | get | method | method | yes |
| HashMap | add | method | method | yes |
| HashMap | remove | method | method | yes |
| HashMap | addIfAbsent | method | method | yes |
| HashMap | keys | method | method | yes |
| HashMap | values | method | method | yes |
| HashMap | clone | method | method | yes |
| HashMap | clear | method | method | yes |
| HashMap | replace | method | method | yes |
| HashMap | contains | method | method | yes |
| HashSet | size | field+method | field | **NO** |
| HashSet | capacity | field+method | field | **NO** |
| HashSet | size | field+method | field | **NO** |
| HashSet | capacity | field+method | field | **NO** |
| HashSet | add | method | method | yes |
| HashSet | contains | method | method | yes |
| HashSet | remove | method | method | yes |
| HashSet | reserve | method | method | yes |
| HashSet | clone | method | method | yes |
| HashSet | toArray | method | method | yes |
| HashSet | clear | method | method | yes |
| String | size | field | field | yes |
| String | empty | static_method | callable_field | **NO** |
| String | isEmpty | method | method | yes |
| String | startsWith | method | method | yes |
| String | endsWith | method | method | yes |
| String | contains | method | method | yes |
| String | concat | method | method | yes |
| String | clone | method | method | yes |
| String | get | method | method | yes |
| String | replace | method | method | yes |
| String | trimAscii | method | method | yes |
| String | hashCode | method | method | yes |
| String | compare | method | method | yes |
| String | indexOf | method | method | yes |
| String | fromUtf8 | static_method | method | **NO** |
| String | empty | static_method | callable_field | **NO** |
| Optional | getOrThrow | method | method | yes |
| Optional | isSome | method | method | yes |
| Optional | isNone | method | method | yes |
| Optional | orElse | method | method | yes |
| KeysView | size | method | method | yes |
| ValuesView | size | method | method | yes |
| Range | size | method | method | yes |
| ArrayStack | size | field | field | yes |
| ArrayStack | capacity | field | field | yes |
| ArrayStack | isEmpty | method | method | yes |
| ArrayStack | add | method | method | yes |
| ArrayStack | peek | method | method | yes |
| ArrayStack | remove | method | method | yes |
| ArrayStack | clear | method | method | yes |
| ArrayStack | reserve | method | method | yes |
| ArrayStack | toArray | method | method | yes |
| ArrayDeque | size | field | field | yes |
| ArrayDeque | capacity | field | field | yes |
| ArrayDeque | isEmpty | method | method | yes |
| ArrayDeque | addFirst | method | method | yes |
| ArrayDeque | addLast | method | method | yes |
| ArrayDeque | removeFirst | method | method | yes |
| ArrayDeque | removeLast | method | method | yes |
| ArrayDeque | clear | method | method | yes |
| ArrayDeque | reserve | method | method | yes |
| ArrayDeque | toArray | method | method | yes |
| Collection | size | method | field | **NO** |
| Stack | add | method | method | yes |
| Stack | peek | method | method | yes |
| Stack | remove | method | method | yes |
| Deque | addFirst | method | method | yes |
| Deque | addLast | method | method | yes |
| Deque | removeFirst | method | method | yes |
| Deque | removeLast | method | method | yes |
| <global> | println | function | method | **NO** |
| <global> | print | function | method | **NO** |
| <global> | eprintln | function | method | **NO** |
| <global> | eprint | function | method | **NO** |
| <global> | min | function | error | **NO** |
| <global> | max | function | error | **NO** |
| <global> | abs | function | method | **NO** |
| <global> | clamp | function | method | **NO** |

21 runtime/model kind mismatches vs official behavior.

## receiver shape (non-identifier receivers)

The A/B/C/D probes above bind the receiver to an identifier. The literal/call receiver form is a separate runtime limitation: member access on a non-identifier receiver does not resolve (calibration: receiver grab produced `3` for `[1, 2, 3].size`).  This section documents that gap — it is NOT part of the per-member gate.

| owner | stmt | declared | official | runtime |
|-------|------|----------|----------|---------|
| Array | `[1, 2, 3].size` | Int64 | ACCEPT () | accept=False fire=22 | **GAP** |
| ArrayList | `ArrayList<Int64>().size` | Int64 | ACCEPT () | accept=True fire=None | match |
| ArrayStack | `ArrayStack<Int64>().size` | Int64 | ACCEPT () | accept=True fire=None | match |
| ArrayDeque | `ArrayDeque<Int64>().size` | Int64 | ACCEPT () | accept=True fire=None | match |
| HashMap | `HashMap<String, Int64>().size` | Int64 | ACCEPT () | accept=True fire=None | match |
| HashSet | `HashSet<String>().size` | Int64 | ACCEPT () | accept=True fire=None | match |
| String | `"abc".size` | Int64 | ACCEPT () | accept=True fire=None | match |
| Optional | `Array<Int64>(1, 0).first.getOrThrow()` | Int64 | ACCEPT () | accept=False fire=20 | **GAP** |
| KeysView | `HashMap<String, Int64>().keys().size()` | Int64 | ACCEPT () | accept=True fire=None | match |
| ValuesView | `HashMap<String, Int64>().values().size()` | Int64 | ACCEPT () | accept=True fire=None | match |
| Range | `0..10.size()` | Int64 | REJECT (E_CHECK_RANGE_EXPECTED) | accept=False fire=13 | match |

## skipped

- Equatable: no concrete implementor in final context — members not probeable through a receiver
- Hashable: no concrete implementor in final context — members not probeable through a receiver
