# 仓颉代码片段语义检查 — 提交前改造清单

## 一、整体判断

当前的技术路线（GBNF token 级语法 + XGrammar bitmask 查表 + 增量语义检查）**不需要推翻**。核心问题是：

- **架构正确**：O(1) bitmask 语法判定 + 栈式符号表语义检查，性能达标（~26μs/token）
- **I/O 不匹配**：比赛输入的是 **tiktoken BPE token**（`cl100k_base` 编码），不是词法 token
- **缺少适配层**：需要在 stdin → tiktoken 解码 → 增量 lex → XGrammar 之间加一层

改造思路：**加一个增量词法适配层**，把 tiktoken 碎片拼成完整的词法 token，再喂给现有的语法+语义检查管线。

---

## 二、改造清单

### P0-1: 新增增量词法适配层

**问题**：比赛通过 stdin 逐行输入 tiktoken BPE 子词 token ID（整数），这些 token **不按词法边界切分**。比如 `Int64` 可能被切成 `"Int"` + `"64"` 两个 token 分别输入。现有 lexer 无法处理这种碎片化输入。

**文件**：新建 `src/incremental_lexer.py`

**实现方案**：

```
stdin → tiktoken ID → decode → 拼入字符 buffer
                                    ↓
                         对 buffer 做增量词法分析
                                    ↓
                    产出完整的词法 Token（可能有 0~N 个）
                                    ↓
                    未完成的部分留在 buffer（等下一个 tiktoken 拼入）
```

核心逻辑：

- 维护一个字符串 buffer，每次收到 tiktoken 时 decode 后拼入 buffer
- 对 buffer 调用 CangjieLexer tokenize（或改造为增量模式）
- 完整 token 出队提交给语法/语义检查器
- 最后一个不完整的 token（如 `"Int"` 后面可能还有字母数字）保留在 buffer
- 判断"可续写"的关键：buffer 尾部如果是合法前缀（如未闭合的字符串、未完成的标识符），视为可续写

**预估**：~200 行

---

### P0-2: 改造 I/O 层（main.py）

**问题**：当前 main.py 读取 `.cj` 文件，输出多行格式化结果。比赛要求：
- 输入：stdin 逐行读 tiktoken token ID（整数）
- 输出：stdout 每行输出 `1`（可续写）或 `0`（不可续写）
- 输出 0 后程序终止，不再读取后续 token

**文件**：重写 `main.py`（或新建 `solution.py`）

**实现方案**：

```
import sys, tiktoken

enc = tiktoken.get_encoding("cl100k_base")

# 加载 import 上下文（见 P0-3）
ctx = load_context("context.json")

# 初始化增量 lexer + 语法检查器 + 语义检查器
inc_lexer = IncrementalLexer()
syn_checker = CangjieSyntaxChecker()
sem_checker = SemanticChecker(preload=ctx)  # 预注册全局符号

buffer = ""
for line in sys.stdin:
    tok_id = int(line.strip())
    buffer += enc.decode([tok_id])

    # 增量 lex：从 buffer 中切出完整词法 token
    lex_tokens, remaining = inc_lexer.feed(buffer)

    for lt in lex_tokens:
        # 语法检查
        if not syn_checker.accept(get_token_id(lt.type)):
            print(0, flush=True)
            sys.exit(0)
        # 语义检查
        if not sem_checker.process(lt).ok:
            print(0, flush=True)
            sys.exit(0)

    print(1, flush=True)
```

**注意**：
- 比赛文档说输出 1=可续写，0=不可续写
- 参考测试脚本 `token_interaction_test.py` 使用 0=OK, 1=ERROR（反过来的），本地测试时需要加 `--invert` 参数适配

**预估**：~100 行

---

### P0-3: 加载 import 上下文

**问题**：比赛提供预定义的全局变量、函数、类和接口。当前 semantic_checker 没有加载这些信息的机制。

**文件**：新建 `src/context_loader.py`

**实现方案**：

- 从 `context.json` 加载全局声明（格式见参考实现 `typechecker/typechecker/context.json`，1511 行）
- 在 SemanticChecker 初始化时预注册到全局作用域（`_stack[0]`）：
  - `global_variables` → `let name: Type` → 注册为 variable
  - `global_functions` → `func name(params): RetType` → 注册为 function，含 param_types, return_type
  - `nominals` (类声明) → `class Name<T> { fields, methods, constructors }` → 注册为 class
  - `interfaces` → `interface Name<T> { methods }` → 注册为 interface
- context.json 应作为 `solution` 二进制同目录下的文件，或嵌入到源码中

**注意**：
- 比赛初赛和决赛可能提供不同的 context.json
- 建议通过环境变量或命令行参数指定 context.json 路径
- context.json 格式参见参考实现，包含 `schema_version`, `nominals`, `interfaces`, `global_functions`, `global_variables`

**预估**：~150 行

---

### P0-4: 语法检查器 — 支持前缀可续性判断

**问题**：现有 `matcher.accept_token()` 返回 True/False 判断的是"当前 token 在语法中是否合法"。但比赛要求判断"当前前缀**是否可以续写**为完整程序"。两者的区别是：

- `accept_token(IDENT)` 在一个需要 `:` 的位置返回 False（语法错误）
- 但如果前一个 token 是不完整的（如 buffer 残留），应该先等待更多输入

**文件**：修改 `src/syntax_checker.py`

**实现方案**：

语法检查需要分两层：
1. **完整 token 层**：lexer 产出的完整词法 token 用 `accept_token()` 检查，False 则返回 0
2. **buffer 残留层**：如果 buffer 中有未完成的 token（如 `"Int"` 可能是 `Int64`/`Int32` 的前缀），则视为可续写（返回 1）

具体改动：

```python
def check_prefix_continuable(self, completed_tokens, remaining_buffer):
    """检查前缀是否可续写。
    completed_tokens: 已确认完整的词法 token 列表
    remaining_buffer: buffer 中未完成的部分字符串
    """
    # 1. 所有完整 token 必须通过语法检查
    for token in completed_tokens:
        if not self.matcher.accept_token(get_token_id(token.type)):
            return False
    # 2. 如果有未完成的 buffer，用字符级检查验证它是否能被续写
    if remaining_buffer:
        return self._partial_buffer_continuable(remaining_buffer)
    return True
```

对于 `_partial_buffer_continuable`：用 XGrammar 的字符级 API 或简单的正则判断字符串是否可能是合法 token 的前缀（如 `"Int"` 是合法 IDENT 前缀，`"\""` 等待字符串闭合，`"!!"` 不可能合法 → 返回 False）。

**预估**：~80 行

---

### P0-5: 语义检查器 — 适配增量输入 + import 上下文

**问题**：
1. SemanticChecker 目前假设收到完整的 token 流，需要适配增量 lexer 的输出（每次只处理新增的完整 token）
2. 部分语义检查（如类型不匹配）在 token 输入过程中触发，时机正确；但 import 上下文的类/函数声明需要预注册

**文件**：修改 `src/semantic_checker.py`

**实现方案**：

1. **新增 `__init__` 参数**：接受 `preload_context`，在初始化时将全局变量/函数/类/接口注册到 `_stack[0]`
2. **增量处理接口不变**：`process(token)` 每次处理一个 token，状态机不需要改
3. **函数调用实参检查完善**（已知问题 5.4）：对于 `context.json` 中定义的全局函数，需要检查实参类型匹配
4. **泛型类型在表达式位置支持**（已知问题 5.2）：`Array<Int32>()` 需要语法和语义层面同时支持

**特别注意要修复的已知问题**：
- 运算符结果类型推导（比较→Bool, 算术→数值）—— 见 P1-1
- 函数调用实参类型检查 —— 见 P1-2
- 泛型类型在表达式位置的构造调用 —— 语法层支持

**预估**：~200 行（主要是 import 上下文集成 + 已知问题修复）

---

### P1-1: 完善运算符结果类型推导

**问题**（已知问题 5.1）：比较运算符（`>`, `<`, `==`, `!=`, `>=`, `<=`）的结果类型应为 `Bool`，逻辑运算符（`&&`, `||`）的结果类型也应为 `Bool`，但当前不推导。

**影响**：`if (a + b)` 应该报错（`if` 条件要求 Bool），但当前不报。比赛中这类错误必须检出。

**文件**：修改 `src/semantic_checker.py`

**实现方案**：
- `_COMPARISON_OPS` 和 `_LOGICAL_OPS` 已定义，但只是打标记 `_expr_has_comparison = True`
- `_resolve_expr_type()` 已实现 comparison→Bool 转换
- 需要在子表达式边界（遇 `)`、`,`、`;` 时）正确触发转换
- 补充：算术运算符结果类型推导（两个 Int64 → Int64，两个 Float64 → Float64）

**预估**：~60 行

---

### P1-2: 完善函数调用实参类型检查

**问题**（已知问题 5.4）：调用函数时不检查实参类型是否与形参匹配。

**影响**：`add("hello", true)` 传错类型，当前检查器不报错。比赛中这类语义错误必须检出。

**文件**：修改 `src/semantic_checker.py`

**实现方案**：
- `_check_call_args()` 已有基础实现，需要补充：
  - 对 context.json 中定义的全局函数也生效
  - 完善类型兼容性矩阵（不仅是 int→float 提升）
  - 检查参数个数匹配

**预估**：~80 行

---

### P1-3: 语法规则补齐（GBNF vs 比赛子集）

**问题**：当前 `cangjie_token.gbnf` 覆盖了仓颉子集的大部分，但需要逐项核对比附子集语法描述中的所有规则是否都支持。

**需要检查的能力清单**：

| 语法特性 | 当前状态 | 需要做什么 |
|----------|----------|-----------|
| 基本类型 (Int8-64, Float32-64, Bool, Rune) | 部分支持 | 补充 Int8/Int16/Int32/Float32 等 |
| String, Array\<T\> | 支持 | — |
| 函数类型 `(T1,T2)->TRet` | 支持 | — |
| 元组类型 `(T1, T2, ...)` | 支持 | — |
| 运算符 (算术/比较/逻辑/一元) | 支持 | — |
| 属性访问 `expr.id` | 支持 | — |
| 索引访问 `expr[idx]` | 支持 | — |
| 函数调用 `f(args)` | 支持 | — |
| 命名参数 `id: expr` | 未确认 | 检查 GBNF 是否支持 |
| 数组字面量 `[1, 2, 3]` | 支持 | — |
| if/else 表达式 | 支持 | — |
| while 循环 | 支持 | — |
| for-in 循环 | 支持 | — |
| for-range 循环 | 部分支持 | 检查 `..` 和 `..=` 语法 |
| break/continue/return | 支持 | — |
| 块表达式 | 支持 | — |
| Lambda 表达式 | 部分支持 | 语义检查有，GBNF 需确认 |
| var/let 声明 | 支持 | — |
| func 声明 | 支持 | — |
| class 声明（含继承、泛型） | 支持 | — |
| interface 声明（含继承） | 支持 | — |
| 泛型类型参数标注 | 支持 | — |
| 泛型类型推导（省略类型参数） | 未完全支持 | P1-4 |

**文件**：`grammar/cangjie_token.gbnf`

**预估**：~100 行（查漏补缺）

---

### P1-4: Lambda 表达式完善

**问题**（比赛用例 15% 涉及 lambda）：当前 lambda 语义检查已有基础实现（`_lambda_pending_params`, `_in_lambda_prefix` 等），但需要验证：
- lambda 参数类型标注可省略的情况
- lambda 嵌套
- lambda 作为函数实参
- lambda 返回值类型推导

**文件**：修改 `src/semantic_checker.py`

**预估**：~80 行

---

### P1-5: 泛型类型推导完善

**问题**（比赛用例 15% 涉及泛型推导）：当泛型函数调用时不标注类型参数，需要从实参类型反推。

当前 `_check_call_args()` 已有基础的类型绑定逻辑（`type_bindings`），需要验证和补充：
- 多个泛型参数的推导
- 泛型参数在返回类型中的推导
- 泛型参数不一致时的报错

**文件**：修改 `src/semantic_checker.py`

**预估**：~60 行

---

### P2-1: 编写 build.sh

**问题**：Docker 提交要求提供 `build.sh`，编译产物为 `solution` 二进制。

**环境**：
- Docker 镜像：`zhanbohua/cjchecker:v1`
- OS：Ubuntu 22.04 (ARM)
- 服务器架构：鲲鹏 920 ARM

**文件**：新建 `build.sh`

**方案选择**：

方案 A — PyInstaller（推荐）：
```bash
#!/bin/bash
pip install pyinstaller tiktoken xgrammar lark
pyinstaller --onefile --name solution solution.py
```

方案 B — Nuitka：
```bash
#!/bin/bash
pip install nuitka tiktoken xgrammar lark
nuitka --standalone --onefile --output-filename=solution solution.py
```

方案 C — zipapp + 内嵌依赖（更轻量但需要目标环境预装依赖）：
```bash
#!/bin/bash
# 如果 Docker 镜像已预装 xgrammar, tiktoken 等
pip install -r requirements.txt
cp solution.py solution
chmod +x solution
```

**注意**：
- 需要确认 Docker 镜像中是否已预装 `xgrammar`, `tiktoken` 等依赖
- `context.json` 需要打包进二进制或放在同目录
- GBNF 语法文件也需要打包

**预估**：~20 行

---

### P2-2: 编写 requirements.txt

**文件**：新建 `requirements.txt`

```
xgrammar>=0.1.0
tiktoken>=0.7.0
lark>=1.1.0
```

**预估**：~5 行

---

### P2-3: 本地测试验证

**验证流程**：

1. 用参考测试脚本 `token_interaction_test.py` 测试 `solution.py`：
   ```bash
   python3 scripts/token_interaction_test.py err_assign_let.cj \
     --cmd python3 solution.py --invert
   ```

2. 遍历所有公开的 wrong 用例，确保每个都在正确的 token 位置输出 0

3. 遍历所有公开的正确用例，确保始终输出 1

4. 跑 benchmark 确保 500 token < 50ms（当前已达标）

**预估**：测试脚本 ~50 行

---

## 三、改造顺序（推荐）

```
第 1 天：P0-1（增量 lexer）+ P0-2（I/O 层）
         → 先让骨架跑通，能用参考脚本测试

第 2 天：P0-3（context 加载）+ P0-4（前缀可续性）
         → 语法+语义检查能对简单用例给出正确结果

第 3 天：P0-5（语义检查器适配）+ P1-1（运算符类型推导）
         → 能通过大部分 70% 基础用例

第 4 天：P1-2（实参检查）+ P1-3（语法规则补齐）
         → 覆盖面提升

第 5 天：P1-4（Lambda）+ P1-5（泛型推导）+ P2-1/2（build.sh）
         → 全部功能到位

第 6 天：P2-3（全面测试 + 性能优化 + Debug）
         → 提交就绪
```

---

## 四、输出约定说明

| 场景 | 比赛要求 | 本地测试脚本 |
|------|---------|-------------|
| 可续写 | 输出 `1` | 期望 `0` |
| 不可续写 | 输出 `0` | 期望 `1` |

本地测试时通过 `--invert` 参数反转输出，或在 `solution.py` 中加环境变量控制。

---

## 五、文件变更总览

| 操作 | 文件 | 说明 |
|------|------|------|
| **新建** | `src/incremental_lexer.py` | 增量词法适配层 |
| **新建** | `src/context_loader.py` | import 上下文加载 |
| **新建** | `solution.py` | 比赛入口（stdin/stdout 协议） |
| **新建** | `build.sh` | Docker 编译脚本 |
| **新建** | `requirements.txt` | Python 依赖 |
| **修改** | `src/syntax_checker.py` | 增量 token 检查 + 前缀可续性 |
| **修改** | `src/semantic_checker.py` | import 上下文集成 + 运算符类型推导 + 实参检查 + lambda + 泛型 |
| **修改** | `grammar/cangjie_token.gbnf` | 补充缺失语法规则 |
| **不改** | `src/lexer.py` | 现有 lexer 作为增量 lexer 的底层引擎 |
| **不改** | `src/token_vocab.py` | TokenType→ID 映射不变 |

总计：约 **1200 行新增 + 400 行修改**。

---

## 六、风险点

1. **XGrammar 能否在 ARM Ubuntu 上运行**：XGrammar 是 Python 包，底层可能有 C++ 扩展。需确认 ARM 兼容性（PyPI 通常提供 manylinux aarch64 wheel）。

2. **PyInstaller 打包 XGrammar**：XGrammar 的 C++ 扩展可能需要特殊处理。备选方案是用 `--onedir` 而非 `--onefile`。

3. **tiktoken cache**：tiktoken 首次运行会下载编码文件。需确认 Docker 环境是否有网络，或提前将 cache 打包进去。

4. **context.json 精确格式**：参考实现展示了格式，但初赛和决赛的 context.json 内容不同，solution 需支持通过参数指定路径。
