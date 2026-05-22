---
name: Cangjie XGrammar Project
description: Using XGrammar framework to implement syntax & semantic checking for Cangjie programming language
type: project
---

# Project: Cangjie Language Checker with XGrammar

**Goal**: Configure XGrammar (mlc-ai/xgrammar, MLSys 2025) for Cangjie (仓颉) programming language syntax & semantic checking.

**Status**: Syntax checking DONE. Semantic checker NOT STARTED.

## Completed Components

### 1. GBNF Grammar (`grammar/cangjie.gbnf`)
- Full Cangjie language syntax in GBNF format
- Covers: identifiers, keywords, literals (integer/float/string/rune/boolean), types (primitive/array/function/nullable/tuple), expressions (full precedence chain), statements (if/while/for/do-while/break/continue/return/throw/try/match), declarations (func/class/struct/enum/interface/extend/operator), program structure (package/import)
- Struct/object init: `Point { x: 0.0, y: 0.0 }`
- **Critical fix**: nested `{...}` blocks require RECURSIVE rules, not `*` operator (Earley parser ambiguity)

### 2. Cangjie Lexer (`src/lexer.py`)
- Regex-based lexer: 50+ token types (keywords, identifiers, literals, operators, delimiters)
- Handles: multi-line strings, rune literals, block comments with nesting, unterminated strings
- Class: `CangjieLexer`, Token types in `TokenType` enum

### 3. Syntax Checker (`src/syntax_checker.py`)
- `CangjieSyntaxChecker.check_token_by_token(code)` → `CheckResult`
- Token-by-token validation using XGrammar's GrammarMatcher in incremental mode
- check logic: `accept_string()` returns True → 1, False → 0, stop on first 0
- Comment preprocessing (strip `//` and `/* */` before grammar validation)

### 4. CLI (`main.py`)
- `python main.py <file.cj>` — check file
- `python main.py --code "..."` — check code string
- `python main.py --test` — run 15 built-in tests

### 5. Examples
- `examples/valid/geometry.cj` — Point class with distance calculation
- `examples/valid/factorial.cj` — recursive factorial
- `examples/invalid/missing_id.cj` — `var = 42` (missing identifier)
- `examples/invalid/dangling_operator.cj` — `return a +` (incomplete expression)

## Output Format
```
token: package myapp func main ( ) { var x = 42 }
结果：1, 1, 1, 1, 1, 1, 1, 1, 1, 1
```
- Each token outputs 1 (valid) or 0 (invalid)
- Stops at the first 0

## Key Technical Discoveries

### GBNF Constraints
- `\n`/`\r` CANNOT appear inside `[...]` character classes → use `"\n"`/`"\r"` string literals
- Rule names must be lowercase_with_underscores
- `root ::= ...` is the entry point

### Earley Parser Nested Block Ambiguity
- `block ::= "{" ws statement* ws "}"` is AMBIGUOUS for nested `{...}` blocks
- The `*` makes the parser greedily complete the outer block at the first `}`
- **Fix**: Use recursive rules: `statements ::= statement (ws statements)?`
- This applies to: `block`, `class_members`, `fields`, `interface_methods`

### Incremental Matcher
- `accept_string()` returns True = valid prefix, False = INVALID
- `is_terminated()` with `is_completed()` distinguishes complete vs partial
- Must use fresh matcher or feed chunks incrementally (not full re-parse each time)

## What's Left (TODO)

### Semantic Checker (`src/semantic_checker.py`) — NOT STARTED
- Type checking (variable types, expression types, function return types)
- Scope analysis (variable/function visibility, shadowing)
- Declaration checks (duplicate declarations, undefined references)
- Function call validation (argument count/types)
- Control flow analysis

### Potential Grammar Expansions
- Generics (`func f<T>(x: T): T`)
- Macros and metaprogramming (quote expressions)
- Concurrency (spawn/sync)
- Operator overloading (operator func)
