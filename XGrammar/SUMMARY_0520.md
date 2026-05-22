# Cangjie Token-Level Syntax & Semantic Checker — 实现总结

日期: 2026-05-20

---

## 1. 项目概览

对仓颉（Cangjie）源码做**增量式 token 级语法 + 语义检查**，识别到第一个错误 token 立即停止，追求极致速度。

核心思路：用 XGrammar 的 `accept_token()` + bitmask 查表（O(1)）替代原始 `accept_string()` 的逐字符 Earley PDA（~0.5ms/char），配合增量语义检查器同步消费同一 token 流。

---

## 2. 已完成实现

### P0: Token 级基础设施

| 模块 | 文件 | 行数 | 说明 |
|------|------|------|------|
| Lexer | `src/lexer.py` | 567 | 仓颉词法分析器，114 种 token 类型，支持关键字/标识符/字面量/运算符/分隔符/注释/字符串 |
| Token 词汇表 | `src/token_vocab.py` | 236 | 111 个 vocab 项，TokenType → vocab string → XGrammar token_id 映射 |
| Token 级语法 | `grammar/cangjie_token.gbnf` | 269 | 完整仓颉 token 级 GBNF 语法，关键字/运算符/分隔符全部改为 token 引用 |
| Syntax Checker | `src/syntax_checker.py` | 272 | `accept_token()` 替代 `accept_string()`，GrammarCompiler + bitmask 查表，O(1) 判定 |

### P1: 语义检查

| 检查类型 | 文件 | 行数 | 说明 |
|----------|------|------|------|
| 栈式符号表 + 作用域 | `src/semantic_checker.py` | 672 | `{` push / `}` pop，声明注册/标识符查找/重复检测，O(1) 全部操作 |
| 类型推导与兼容性 | 同上 | — | 字面量类型、变量类型追踪、赋值兼容（int→float 提升等） |
| 上下文约束 | 同上 | — | break/continue 在循环内、return 在 func 内、main() 最多一次 |

### P2: 统一管线

| 模块 | 文件 | 行数 | 说明 |
|------|------|------|------|
| CLI + CheckResult | `main.py` + `src/syntax_checker.py` | 149 + 272 | 同时输出语法 + 语义两行结果，一次 lexer → 两个 checker 并行消费 |

### P3: 性能验证

| 模块 | 文件 | 行数 | 说明 |
|------|------|------|------|
| 346 行测试用例 | `benchmark/large_benchmark.cj` | 346 | 涵盖 package/import/enum/struct/interface/class/methods/control flow/match |
| Benchmark 脚本 | `benchmark/benchmark.py` | 443 | A/B 对比（字符级 vs Token 级），自动回归测试，保存 JSON 报告 |
| 性能报告 | `benchmark/benchmark_report.json` | 80 | 完整 benchmark 数据 |

---

## 3. 核心性能数据

```
┌──────────────────────┬─────────────────────┬─────────────────────┐
│                      │   字符级（旧方案）   │  Token 级（新方案）   │
├──────────────────────┼─────────────────────┼─────────────────────┤
│ 判定方式              │ accept_string()     │ accept_token()       │
│                      │ 逐字符 Earley PDA    │ Bitmask O(1) 查表    │
├──────────────────────┼─────────────────────┼─────────────────────┤
│ 大文件 (7427 char)    │ ~785 ms              │ ~47 ms               │
├──────────────────────┼─────────────────────┼─────────────────────┤
│ 1944 token 总计       │ ~798 ms              │ ~51 ms               │
├──────────────────────┼─────────────────────┼─────────────────────┤
│ 每 token 延迟         │ —                   │ 26.3 μs              │
├──────────────────────┼─────────────────────┼─────────────────────┤
│ 500-token 预估        │ —                   │ 13.16 ms (< 50 ms ✓) │
├──────────────────────┼─────────────────────┼─────────────────────┤
│ 加速比               │ —                   │ 15.6x                │
└──────────────────────┴─────────────────────┴─────────────────────┘
```

回归测试: **15/15 通过**，零回归。

---

## 4. 项目结构

```
XGrammar/
├── grammar/
│   ├── cangjie.gbnf               # 原始字符级 GBNF 语法（参考用）
│   └── cangjie_token.gbnf         # Token 级 GBNF 语法（主力使用）
├── src/
│   ├── __init__.py
│   ├── lexer.py                   # 仓颉词法分析器（114 TokenType, 567 行）
│   ├── token_vocab.py             # Token → vocab 映射（111 项, 236 行）
│   ├── syntax_checker.py          # Token 级语法检查器 + CheckResult（272 行）
│   └── semantic_checker.py        # 增量语义检查器（672 行）
├── examples/
│   ├── valid/factorial.cj         # 示例: 阶乘
│   ├── valid/geometry.cj          # 示例: 几何类
│   ├── invalid/missing_id.cj      # 反例: 缺少标识符
│   └── invalid/dangling_operator.cj # 反例: 运算符残缺
├── benchmark/
│   ├── large_benchmark.cj         # 346 行仓颉代码（1772 token）
│   ├── benchmark.py               # A/B 性能对比脚本
│   └── benchmark_report.json      # 性能数据报告
├── main.py                        # CLI 入口
├── Plan_0519.md                   # 原始计划
└── SUMMARY_0520.md                # 本总结
```

---

## 5. 已知问题与局限性

### 5.1 类型推导不完整

当前语义检查器对**运算符结果类型**不做推导。例如：

```cangjie
func test(): Bool {
    return a >= b;  // 语法 OK，语义 OK（因为 >= 结果类型未追踪）
}
```

`a >= b` 应推导出 `Bool`，但检查器不做运算符类型推导，仅在此基础上依赖 `_STATEMENT_START_TOKENS` 处的延迟类型检查。这意味着：

- **不会误报错误**（不会把正确代码判错）
- **部分类型不匹配无法检测**（需要运算符结果类型参与后续检查的场景）

### 5.2 泛型类型仅限 type 位置

`Array<Int32>` 在类型注解位置（变量声明、函数参数、返回类型）解析正常，但在表达式位置（如 `Array<Int32>()` 构造调用）不通过语法检查。原因是 token 级语法的 `primary` 规则不包含 type 引用。

```cangjie
// 能过
var x: Array<Int32> = ...;

// 不能过（语法错误）
var x = Array<Int32>();
```

### 5.3 隐式 main() 重复检测不完整

带 `func` 关键字的 `func main()` 重复声明能正确检测，但无关键字的 `main() {}` 形式（`main_decl` 语法规则）在第二次出现时无法检测到重复。

```cangjie
// 能检测
func main() {}  func main() {}  // Duplicate declaration ✓

// 无法检测
main() {}  main() {}  // 第二个 main 在作用域中被找到，跳过重复检查 ✗
```

### 5.4 函数调用实参不做类型检查

调用函数时，传入的实参不校验是否与形参类型匹配：

```cangjie
func add(a: Int32, b: Int32): Int32 { return a + b; }
func main() {
    add("hello", true);  // 语法 OK，语义 OK（但明显类型错误）
}
```

### 5.5 多字符运算符后缺少分号导致类型检查漏报

`var i: Int32 = 1`  后若无分号，`_expected_type` 会残留在 `"Int32"`。当下一条语句是 `_STATEMENT_START_TOKENS`（如 `while`, `if`, `var` 等）时，`_are_types_compatible` 能兜底处理（同类型族判为兼容），但若非整数族则可能误判。已通过在所有语句末尾加分号规避。

### 5.6 不支持嵌套函数

Cangjie token 级语法将 `func_decl` 限定为 `top_level_item`，不允许在函数体内声明嵌套函数。这是语法层面的设计选择，与仓颉语言规范一致。

---

## 6. 后续改进方向

| 优先级 | 内容 | 难度 |
|--------|------|------|
| 中 | 完善运算符类型推导（比较→Bool, 算术→数值类型等） | 中 |
| 低 | 表达式位置支持泛型构造调用 | 中 |
| 低 | 隐式 main() 重复检测修复 | 低 |
| 低 | 函数调用实参类型检查 | 中 |
| 低 | 支持更多仓颉语法（extension, operator overload, lambda） | 高 |
