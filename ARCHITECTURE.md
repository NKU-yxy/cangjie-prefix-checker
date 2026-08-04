# 仓颉代码片段语义检查 — 架构交接文档

## 一、项目目录总览

```
XGrammar/
├── solution.py              # 【入口】竞赛 stdin/stdout 协议
├── build.sh                 # 提交时平台执行的构建脚本
├── main.py                  # 离线测试 CLI（不再使用）
├── requirements.txt         # Python 依赖
├── context.json             # 竞赛提供的预加载符号表
├── torch.py                 # stub：免装真实 torch 就能 import xgrammar
├── transformers.py          # stub：免装真实 transformers
│
├── src/
│   ├── stream_checker.py    # 【核心】流式检查器，统领所有子模块
│   ├── incremental_lexer.py # 增量词法分析器：处理 token 边界不对齐
│   ├── lexer.py             # 仓颉词法分析器（正则驱动，90+ TokenType）
│   ├── token_vocab.py       # TokenType → XGrammar 词汇表 ID 映射
│   ├── incremental_semantic_engine.py # token-once 作用域/类型/调用/约束状态
│   ├── prefix_semantic_checker.py # 追加式缓存的语义 probe
│   ├── batch_semantic_validator.py # 仅 checkpoint/legacy 回退时使用
│   ├── semantic_checker.py  # 逐 token 增量语义检查器（token-by-token）
│   ├── syntax_checker.py    # 离线语法+语义检查器（check_token_by_token）
│   └── context_loader.py    # 加载 context.json，解析预导入符号
│
├── grammar/
│   ├── cangjie_token.gbnf   # token 级 GBNF 语法（运行时使用）
│   └── cangjie.gbnf         # 字符级 GBNF 语法（备用）
│
├── third_party/cangjie_typechecker/  # 官方仓颉 typechecker（Lark 解析器）
│
├── benchmark/               # 性能基准测试
├── tests/                   # 单元测试
└── examples/                # 示例代码
```

## 二、核心调用链

一次完整的 token 处理流程（从 stdin 读到输出 0/1）：

```
stdin: "1234\n"  （tiktoken token ID）

1. solution.py: main()
   │
   ├─ tiktoken.decode([1234])  → "func"  （解码为文本片段）
   │
   └─ checker.feed_text("func")
      │
      └── CangjieStreamChecker.feed_text()     [stream_checker.py]
          │
          ├─ 累加文本: self._source_prefix += "func"
          │
          ├─[1] IncrementalLexer.feed("func")  [incremental_lexer.py]
          │       │
          │       ├─ CangjieLexer.tokenize()     [lexer.py]
          │       ├─ _stable_split_offset()      确定哪些 token 已稳定
          │       └─ 返回 IncrementalLexResult(tokens=[...], ...)
          │
          ├─[2] 对每个稳定 token → _accept_complete_token()
          │       │
          │       ├─ get_token_id(type)          [token_vocab.py]
          │       ├─ GrammarMatcher.accept_token(id)  [xgrammar]
          │       └─ _token_invalid_in_kw_context()   关键字上下文检查
          │
          ├─[3] _check_partial()  检查不完整 token 是否合法
          │       └─ _trial_accept()  克隆 matcher 试探候选 token
          │
          ├─[4] IncrementalSemanticEngine           [incremental_semantic_engine.py]
          │       │
          │       ├─ accept(TokenEvent)    稳定词法 token 只消费一次
          │       ├─ probe(PartialLexeme)  不提交地检查不完整词法单元
          │       ├─ checkpoint()/rollback()
          │       └─ PrefixSemanticChecker（声明/函数/类缓存后做保守 probe）
          │
          │       PrefixSemanticChecker 包含：
          │       ├─ _build_context()      只在结构变化时刷新声明缓存
          │       ├─ _check_duplicate_param()
          │       ├─ _check_break_continue()
          │       ├─ _check_condition_prefix()
          │       ├─ _check_for_prefix()
          │       ├─ _check_call_prefix()
          │       ├─ _check_member_and_index_prefix()
          │       ├─ _check_var_assignment_prefix()
          │       ├─ _check_return_prefix()
          │       └─ ... 等 ~10 项正则检查
          │
          └─[5] _check_semantic_prefix()  fast 默认路径直接跳过
                │
                └─ checkpoint/legacy 模式才惰性创建 BatchSemanticValidator
                      │
                      ├─ _candidates()     生成候选补全（补括号、加分号）
                      ├─ typechecker.parser.parse()   [third_party/]
                      └─ typechecker.checker.typecheck_tree()
                           │
                           └─ _is_artificial_diagnostic()  过滤补全引入的假错误

stdout: "0"  （0=无错，1=有错；竞赛模式反之）
```

**任何环节返回 not OK，立即终止并输出错误信号，后续调用都短路返回。**

## 三、各文件详细说明

### 3.1 solution.py — 竞赛入口

- 从 stdin 逐行读取 tiktoken token ID
- 用 `cl100k_base` 解码为文本片段
- 喂给 `CangjieStreamChecker.feed_text()`
- 输出 `0`（前缀可续写）或 `1`（前缀不可续写）
- `--competition-output` 翻转约定（赛题要求 1=可续写）

### 3.2 src/stream_checker.py — 流式检查核心

**`CangjieStreamChecker`** 是整个系统的总调度器：

| 功能 | 方法 |
|------|------|
| 增量词法 | `IncrementalLexer.feed()` |
| 语法检查（O(1)） | `GrammarMatcher.accept_token()` + `_accept_complete_token()` |
| 部分 token 试探 | `_check_partial()` + `_trial_accept()` |
| 增量语义 | `IncrementalSemanticEngine.accept()/probe()` |
| 深度语义回退 | `LazyBatchSemanticValidator.validate_prefix()` |

语法检查使用 XGrammar 编译 GBNF 语法为 bitmask 自动机，每次 `accept_token` 是 O(1) 位运算。

### 3.3 src/incremental_lexer.py — 增量词法

**处理 LLM token 和仓颉词法 token 不对齐的核心问题。**

LLM 的 tiktoken 编码边界和仓颉词法 token 边界不对齐（例如 `Int` 和 `64` 可能分成两个 LLM token，但仓颉里 `Int64` 是一个类型名）。

**策略**：维护一个文本缓冲区，每次喂入新片段后，对**整个缓冲**重新做仓颉词法分析。然后通过 `_stable_split_offset()` 判断哪些 token 是"稳定的"（后续输入不会改变它们），只输出稳定部分。

`_stable_split_offset()` 检查：
- 未闭合结构（注释 `/*`、字符串 `"`、rune `'`、反引号）
- token 级不稳定（部分标识符 `Int` 可能是 `Int64`、`import` 等）
- 部分数字、部分运算符

### 3.4 src/lexer.py — 仓颉词法分析器

- 90+ `TokenType` 枚举（关键字、字面量、运算符、分隔符等）
- 基于有序正则表达式模式匹配
- 特殊处理：嵌套块注释 `/* /* */ */`、多行字符串、rune 字面量、原始标识符
- 提供字节偏移，支持后续定位

### 3.5 src/token_vocab.py — 词汇表映射

- 将 `TokenType` 映射为 XGrammar 词汇表中的整数 ID
- 构建 `TokenizerInfo` 供 `GrammarCompiler` 使用
- 词汇名与 `cangjie_token.gbnf` 中的 token 名对应

### 3.6 src/prefix_semantic_checker.py — 前缀语义检查（快速）

由 `IncrementalSemanticEngine.probe()` 调用。函数、接口、类和当前函数元数据按
追加源码增量缓存，只有 `{` / `}` 等结构变化时才重建相应声明索引；不再每次
重扫全部声明。

通过正则从源代码文本中提取符号表，然后检查：

1. `_check_duplicate_param` — 函数参数名重复
2. `_check_interface_method_prefix` — 接口方法实现匹配
3. `_check_break_continue` — break/continue 在循环外
4. `_check_condition_prefix` — if/while 条件表达式
5. `_check_for_prefix` — for 循环的迭代对象
6. `_check_generic_arity_prefix` — 泛型参数数量
7. `_check_call_prefix` — 函数调用参数类型
8. `_check_member_and_index_prefix` — 成员访问和索引
9. `_check_var_assignment_prefix` — 变量赋值类型
10. `_check_return_prefix` — 返回类型匹配

### 3.7 src/batch_semantic_validator.py — 深度语义验证（慢速）

默认 `fast` 生产路径不会初始化或调用此模块。它保留为 `checkpoint`（仅稳定
语句边界）和 `legacy`（差分 oracle）模式的惰性回退。

- 对前缀生成多种"补全候选项"（补括号、补分号、补 `0` 等）
- 每个候选项用 Lark 解析器 + typechecker 做完整的解析和类型检查
- 如果 typechecker 报错，通过 `_is_artificial_diagnostic()` 判断是否是补全引入的假错误
- 只要有一个候选项通过 typecheck，就认为前缀 OK

### 3.8 src/semantic_checker.py — 逐 token 增量语义检查

**作用域栈 + 状态机，O(1) 符号操作。**

- 维护 `ScopeStack`：每个 `{` push，每个 `}` pop
- 追踪声明、查找标识符、类型兼容性检查
- 处理泛型类型参数、构造函数签名、lambda 语义
- `process(token)` 是核心状态机（约 1300 行）

### 3.9 src/context_loader.py — 上下文加载

加载 `context.json`（竞赛提供的全局符号表），包含：
- 全局变量声明
- 全局函数声明
- 类和接口声明（含成员、方法、继承关系）

支持灵活的输入格式（dict/list，多种键名）。

### 3.10 辅助文件

| 文件 | 作用 |
|------|------|
| `torch.py` | stub，让 xgrammar 不装真实 PyTorch 也能 import |
| `transformers.py` | stub，让 xgrammar 不装真实 transformers 也能 import |
| `grammar/cangjie_token.gbnf` | token 级 GBNF 语法，包含完整仓颉子集语法规则 |
| `third_party/cangjie_typechecker/` | 官方仓颉 typechecker（Lark + 类型推断），被 `batch_semantic_validator` 调用 |

## 四、三种运行模式

```
fast（默认）        token-once 状态 + 缓存 probe；生产路径 Lark 调用为 0
checkpoint          fast + 换行/分号/右花括号处的惰性官方 typechecker 回退
legacy              用于逐前缀差分的原深检模式
```

可用 `--semantic-mode` 或 `CANGJIE_SEMANTIC_MODE` 切换。提交默认使用 `fast`；
遇到新语义规则时先用 `legacy` 做 oracle，再把规则迁入在线引擎。

## 五、关键依赖

```
Python 包：
  tiktoken>=0.7.0      — cl100k_base 解码
  lark>=1.1.0          — third_party typechecker 的解析器
  xgrammar==0.2.1      — GBNF 语法编译 + O(1) token 接受检查
  numpy, pydantic      — xgrammar 传递依赖

外部文件：
  context.json         — 预导入符号表
  grammar/cangjie_token.gbnf — token 级语法规则
```
