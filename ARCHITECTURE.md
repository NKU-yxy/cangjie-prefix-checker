# 仓颉代码片段语义检查 — 架构交接文档

## 一、项目目录总览

```
XGrammar/
├── solution                 # build.sh 生成的 C++17 竞赛二进制
├── solution.py              # Python 差分 oracle / 安全回退入口
├── build.sh                 # 生成 cl100k 表并编译原生入口
├── cpp/solution.cpp         # 【入口】原生协议、token 解码、字符级 PDA
├── tools/generate_cl100k_table.py # 构建期生成 token ID→UTF-8 表
├── main.py                  # 离线测试 CLI（不再使用）
├── requirements.txt         # Python 依赖
├── context.json             # 竞赛提供的预加载符号表
├── torch.py                 # stub：免装真实 torch 就能 import xgrammar
├── transformers.py          # stub：免装真实 transformers
│
├── src/
│   ├── stream_checker.py    # 【核心】流式检查器，统领所有子模块
│   ├── native_semantic_worker.py # C++ 子进程使用的轻量语义 worker
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
│   ├── cangjie_token.gbnf   # Python oracle 使用的 token 级语法
│   └── cangjie.gbnf         # C++ 生产入口使用的字符级语法
│
├── third_party/cangjie_typechecker/  # 官方仓颉 typechecker（Lark 解析器）
│
├── benchmark/               # 性能基准测试
├── tests/                   # 单元测试
└── examples/                # 示例代码
```

## 二、核心调用链

默认 C++ 入口的一次完整 token 处理流程：

```
stdin: "1234\n"  （tiktoken token ID）

1. solution (cpp/solution.cpp)
   ├─ mmap/读取 generated/cl100k_base.bin
   ├─ token ID → 与 tiktoken.decode([id]) 一致的 UTF-8 片段
   ├─ NativeSyntaxChecker.accept(fragment)
   │    └─ XGrammar C++ GrammarMatcher + grammar/cangjie.gbnf
   └─ SemanticWorker.check(fragment)
        ├─ fork/exec 一次轻量 Python worker
        ├─ 十六进制管道传输任意 UTF-8 片段
        └─ PrefixSemanticChecker（预加载 context、声明缓存、类型/作用域检查）

stdout: "0"  （0=无错，1=有错；竞赛模式反之）
```

**任何环节返回 not OK，立即终止并输出错误信号，后续调用都短路返回。**

## 三、各文件详细说明

### 3.1 cpp/solution.cpp — 默认竞赛入口

- 直接读取 stdin 中的 cl100k token ID，不导入 tiktoken
- 使用构建期表恢复与 Python `decode([id])` 完全一致的文本
- 字符级 XGrammar PDA 在原生进程内增量推进，包含注释和不完整词法单元
- 语义规则复用轻量 worker，避免重复实现导致隐藏样例分叉
- `0=无错、1=有错` 协议及 `--competition-output` 保持兼容

### 3.2 solution.py — Python oracle

- 保留原 Python 全链路，用于 C++/Python 差分和紧急回退
- 从 stdin 逐行读取 tiktoken token ID
- 用 `cl100k_base` 解码为文本片段
- 喂给 `CangjieStreamChecker.feed_text()`
- 输出 `0`（前缀可续写）或 `1`（前缀不可续写）
- `--competition-output` 翻转约定（赛题要求 1=可续写）

### 3.3 src/stream_checker.py — Python 流式检查核心

**`CangjieStreamChecker`** 是整个系统的总调度器：

| 功能 | 方法 |
|------|------|
| 增量词法 | `IncrementalLexer.feed()` |
| 语法检查（O(1)） | `GrammarMatcher.accept_token()` + `_accept_complete_token()` |
| 部分 token 试探 | `_check_partial()` + `_trial_accept()` |
| 增量语义 | `IncrementalSemanticEngine.accept()/probe()` |
| 深度语义回退 | `LazyBatchSemanticValidator.validate_prefix()` |

语法检查使用 XGrammar 编译 GBNF 语法为 bitmask 自动机，每次 `accept_token` 是 O(1) 位运算。

### 3.4 src/incremental_lexer.py — 增量词法

**处理 LLM token 和仓颉词法 token 不对齐的核心问题。**

LLM 的 tiktoken 编码边界和仓颉词法 token 边界不对齐（例如 `Int` 和 `64` 可能分成两个 LLM token，但仓颉里 `Int64` 是一个类型名）。

**策略**：维护一个文本缓冲区，每次喂入新片段后，对**整个缓冲**重新做仓颉词法分析。然后通过 `_stable_split_offset()` 判断哪些 token 是"稳定的"（后续输入不会改变它们），只输出稳定部分。

`_stable_split_offset()` 检查：
- 未闭合结构（注释 `/*`、字符串 `"`、rune `'`、反引号）
- token 级不稳定（部分标识符 `Int` 可能是 `Int64`、`import` 等）
- 部分数字、部分运算符

### 3.5 src/lexer.py — 仓颉词法分析器

- 90+ `TokenType` 枚举（关键字、字面量、运算符、分隔符等）
- 基于有序正则表达式模式匹配
- 特殊处理：嵌套块注释 `/* /* */ */`、多行字符串、rune 字面量、原始标识符
- 提供字节偏移，支持后续定位

### 3.6 src/token_vocab.py — 词汇表映射

- 将 `TokenType` 映射为 XGrammar 词汇表中的整数 ID
- 构建 `TokenizerInfo` 供 `GrammarCompiler` 使用
- 词汇名与 `cangjie_token.gbnf` 中的 token 名对应

### 3.7 src/prefix_semantic_checker.py — 前缀语义检查（快速）

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

### 3.8 src/batch_semantic_validator.py — 深度语义验证（慢速）

默认 `fast` 生产路径不会初始化或调用此模块。它保留为 `checkpoint`（仅稳定
语句边界）和 `legacy`（差分 oracle）模式的惰性回退。

- 对前缀生成多种"补全候选项"（补括号、补分号、补 `0` 等）
- 每个候选项用 Lark 解析器 + typechecker 做完整的解析和类型检查
- 如果 typechecker 报错，通过 `_is_artificial_diagnostic()` 判断是否是补全引入的假错误
- 只要有一个候选项通过 typecheck，就认为前缀 OK

### 3.9 src/semantic_checker.py — 逐 token 增量语义检查

**作用域栈 + 状态机，O(1) 符号操作。**

- 维护 `ScopeStack`：每个 `{` push，每个 `}` pop
- 追踪声明、查找标识符、类型兼容性检查
- 处理泛型类型参数、构造函数签名、lambda 语义
- `process(token)` 是核心状态机（约 1300 行）

### 3.10 src/context_loader.py — 上下文加载

加载 `context.json`（竞赛提供的全局符号表），包含：
- 全局变量声明
- 全局函数声明
- 类和接口声明（含成员、方法、继承关系）

支持灵活的输入格式（dict/list，多种键名）。

### 3.11 辅助文件

| 文件 | 作用 |
|------|------|
| `torch.py` | stub，让 xgrammar 不装真实 PyTorch 也能 import |
| `transformers.py` | stub，让 xgrammar 不装真实 transformers 也能 import |
| `grammar/cangjie_token.gbnf` | token 级 GBNF 语法，包含完整仓颉子集语法规则 |
| `third_party/cangjie_typechecker/` | 官方仓颉 typechecker（Lark + 类型推断），被 `batch_semantic_validator` 调用 |

## 四、三种运行模式

```
原生 solution（默认） C++ token 解码 + C++ 字符 PDA + 轻量语义 worker
fast（Python oracle） token-once 状态 + 缓存 probe；生产路径 Lark 调用为 0
checkpoint          fast + 换行/分号/右花括号处的惰性官方 typechecker 回退
legacy              用于逐前缀差分的原深检模式
```

原生入口接受 `--semantic-mode` 以保持 harness 兼容；Python 调试入口可用该参数或
`CANGJIE_SEMANTIC_MODE` 切换。遇到新规则时先用 Python `legacy` 做 oracle，再差分
原生入口。

## 五、关键依赖

```
构建期：
  C++17 编译器          — 编译 cpp/solution.cpp
  tiktoken>=0.7.0      — 生成 cl100k_base.bin，运行时不导入
  lark>=1.1.0          — third_party typechecker 的解析器
  xgrammar==0.2.1      — 链接 C++ 共享库，运行时不导入 Python binding
  numpy, pydantic      — xgrammar 传递依赖

外部文件：
  context.json         — 预导入符号表
  grammar/cangjie_token.gbnf — token 级语法规则
```
