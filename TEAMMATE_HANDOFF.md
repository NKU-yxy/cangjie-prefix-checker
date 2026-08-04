# 仓颉前缀检查器：队友与 ChatGPT 交接文档

> 更新时间：2026-08-04
>
> 本文是当前项目的事实基线，也是给下一位开发者/ChatGPT 的启动上下文。接手时请先完整阅读本文，再查看 `ARCHITECTURE.md`、代码和测试。不要从头重写，也不要针对公开样例名称、固定源码或固定错误位置做特化。

## 0. 可直接复制给接手 ChatGPT 的任务说明

```text
你正在接手“2026 编译系统挑战赛——仓颉代码片段语义检查”项目。

请先完整阅读仓库根目录的 TEAMMATE_HANDOFF.md、ARCHITECTURE.md、比赛具体要求.md，
然后检查 agent/cpp-semantic-engine 分支和 98a8304 提交。当前版本已经 AC，任何改动都必须：

1. 保持公开 50 个错误样例在精确的首错 token index 报错；
2. 保持有效/修复样例的所有前缀可续写；
3. 不依赖公开文件名、固定错误位置或固定源码文本；
4. 保持 cl100k、逐字符、随机分片三种输入切分的结果一致；
5. 在官方 ARM Docker 中构建和测试；
6. 先新建开发分支，不修改两个 AC 备份分支；
7. 每完成一种语义规则，就增加 C++/Python 逐前缀差分测试；
8. 性能优化的核心目标是移除 C++ 入口中的 Python semantic worker，最终生产路径不得
   fork/exec Python、不得导入 tiktoken/Lark、不得反复扫描完整源码前缀。

开始工作前先跑基线测试并记录 p50/p95。请先给出你确认过的现状、准备修改的文件、
风险和验证方法，再实施。遇到公开样例与隐藏样例泛化冲突时，正确性优先。
```

## 1. 赛题和共同目标

程序逐个接收 `cl100k_base` token ID。每收到一个 ID，就必须立即判断当前仓颉源码前缀是否仍可能续写成合法程序，并输出一行结果；一旦首次判错，后续可以终止或持续返回错误状态。

当前公开 harness/项目默认协议是 `0=可续写、1=错误`；传入 `--competition-output` 时翻转为 `1=可续写、0=错误`。迁移入口时必须保持这一兼容行为，并以实际评测 harness 的调用参数为准。

需要同时检查：

- 增量词法与语法；
- 变量/函数/类/接口的作用域与先声明后使用；
- 可变性、类型兼容、运算符约束；
- 调用、重载、命名参数、构造器与成员；
- 泛型实参与类型变量统一；
- 接口实现、继承与签名匹配；
- lambda 的显式类型和上下文类型推导；
- 未完成字符串、标识符、数字和运算符等部分词法单元的可续写性。

官方数据包含 50 个公开样例和隐藏样例。功能正确且单例不超时才有功能分，性能分按排名计算。因此当前原则是：

1. 先保持 AC 和精确首错位置；
2. 再消除冷启动和完整前缀重放；
3. 禁止根据公开样例名、固定 token index 或源码常量硬编码。

## 2. 对话和决策摘要

项目最初公开样例虽能 AC，但单例通常约 `1.7–3.4s`。分析发现瓶颈不是 XGrammar 的单次 `accept_token`，而是每收到一个 LLM token 都对完整源码前缀做正则扫描、Lark 解析和类型检查：公开 50 例累计触发过约 5,575 次深检，Lark/类型检查约占热路径 83%。

随后采用两阶段策略：

1. Python 安全优化：生产 `fast` 路径停用 Lark 全前缀深检，保留保守的前缀语义检查；只保存最近 token；缓存声明和上下文；新增冷进程基准与差分测试。
2. C++ 混合入口：把 cl100k 解码和 XGrammar 字符级语法状态迁入 C++，语义暂时复用轻量 Python worker，以最低风险保持 AC。

这个策略把平台耗时从数秒降至约 `0.65s`，但 C++ 混合版相对 Python AC 版在官网只小幅领先。由此形成当前决定：**下一步真正值得投入的是把语义检查也迁入 C++，并移除生产链路中的 Python worker 和完整源码重复扫描。**

## 3. Git、分支与可恢复基线

远程仓库：

```text
https://gitlab.eduxiji.net/T2026100552010674/compiler2026.git
```

已有分支：

| 用途 | 分支 | 提交 | 状态 |
|---|---|---:|---|
| 原始主线 | `main` | `cd4486b` | 不作为当前优化基线 |
| Python AC/优化版 | `agent/performance-semantic-engine` | `3232d5f` | 已推送 GitLab |
| C++ 混合 AC 版 | `agent/cpp-semantic-engine` | `98a8304` | 已推送 GitLab，推荐的开发起点 |

本地还存在标签 `python-ac-20260804` 和 `cpp-ac-20260804`；远端标签是否已推送需要在可访问 GitLab 的终端中确认。

`codex/team-handoff` 是从 C++ AC 提交 `98a8304` 创建、只增加本文和 README 入口的交接分支。推送该分支后，接手者可以直接从它创建开发分支，既保留本文又不改动 AC 分支：

```bash
cd "/Users/doufuru/Documents/编译大赛/XGrammar"
git fetch origin
git switch codex/team-handoff
git pull --ff-only
git switch -c feature/pure-cpp-semantic-engine
```

需要回到稳定版本时只需切换分支，不要使用 `git reset --hard` 覆盖未保存工作。

本机已有两个提交包，但压缩包本身不在 Git 仓库中：

```text
/Users/doufuru/Documents/编译大赛/XGrammar_submit_final.zip  # Python AC 版
/Users/doufuru/Documents/编译大赛/XGrammar_submit_cpp.zip    # C++ 混合 AC 版
```

## 4. 已完成工作

### 4.1 Python AC 版（3232d5f）

主要变化：

- 新增 `IncrementalSemanticEngine` 的状态模型：`ScopeFrame`、`TypeArena/TypeId`、`ExprFrame`、`CallFrame`、`ConstraintSet`、`checkpoint/rollback`；
- `fast` 生产路径不初始化或调用 Lark `BatchSemanticValidator`；
- `checkpoint` 仅在稳定语义提交点使用深检，`legacy` 作为差分 oracle；
- `_token_invalid_in_kw_context()` 只保存最近两个 token；
- 修复/增强 `context.json` 中变量、函数、重载、类、接口、成员和继承结构的加载；
- 强化部分 token、lambda、泛型、集合、接口和类型兼容规则；
- 新增真实冷进程 benchmark、legacy/new 差分和回归测试。

注意：`IncrementalSemanticEngine` 目前仍是“状态骨架 + PrefixSemanticChecker probe”。它还没有完全替代正则前缀检查器，不能把文件名理解成“所有语义规则都已经 token-once”。

### 4.2 C++ 混合 AC 版（98a8304）

生产调用链：

```text
token ID
  -> C++ TokenTable（generated/cl100k_base.bin）
  -> UTF-8 fragment
  -> C++ XGrammar 字符级 GrammarMatcher
  -> pipe（十六进制片段）
  -> Python native_semantic_worker.py
  -> IncrementalLexer + PrefixSemanticChecker
  -> 输出 0/1
```

已迁入 C++ 的部分：

- 竞赛 stdin/stdout 协议；
- cl100k token ID 到原始字节的运行时解码；
- XGrammar C++ GrammarCompiler/GrammarMatcher；
- 字符级增量语法状态；
- 遇错锁存和进程级短路。

仍在 Python 的部分：

- 仓颉稳定 token 的增量词法事件；
- context 的归一化和加载；
- 全部前缀语义规则、类型推断、lambda/泛型检查；
- 大量正则和字符串切分。

## 5. 当前性能事实

### 5.1 官网两次 AC 对比

Python AC 版（约 20:33 提交）与 C++ 混合版（约 21:50 提交）的 50 例配对统计：

| 指标 | Python AC | C++ 混合 AC | 变化 |
|---|---:|---:|---:|
| 平均耗时 | `0.65642s` | `0.64554s` | `-10.88ms`（约 `-1.66%`） |
| 中位数 | `0.658s` | `0.650s` | `-8ms`（约 `-1.22%`） |
| 更快/更慢样例数 | — | 33 / 17 | 有小幅收益，但存在平台噪声 |

短样例改善更明显，例如：

```text
err_duplicate_var:             0.596s -> 0.483s
err_return_type_mismatch:      0.585s -> 0.486s
err_interface_sig_mismatch:    0.593s -> 0.506s
err_interface_not_implemented: 0.593s -> 0.521s
```

结论：C++ 混合版有轻微优化迹象并保持 AC，但没有达到原先期望的数量级提升，官网得分仍为 25，尚未获得性能排名分。

### 5.2 本地官方 ARM Docker 基线

此前在官方 ARM Docker 生产路径上得到：

```text
公开样例精确首错：50/50
first response p50: 20.19ms
total p50:          68.86ms
total p95:          87.85ms
max:                97.82ms
```

官网约 `0.65s` 与本地约 `0.07s` 差距很大，推测官网统计包含明显的容器/调度/构建外固定开销，或环境资源更紧。这个推测不是已证实事实，后续优化必须同时记录“进程内用时”和“官网端到端用时”。

## 6. 当前最重要的技术债和风险

### 6.1 名义上的 C++ 入口仍会启动 Python

`cpp/solution.cpp` 的 `SemanticWorker` 会 `fork/exec python3 src/native_semantic_worker.py`。因此仍然支付 Python 解释器、模块加载、正则和 IPC 的成本。它不是纯 C++ 单二进制。

### 6.2 worker 仍反复处理完整源码前缀

`src/native_semantic_worker.py` 每个片段执行：

```python
source_parts.append(fragment)
source = "".join(source_parts)
known_generic_heads.update(REGEX.findall(source))
checker.validate(source)
```

`PrefixSemanticChecker.validate(source)` 内部还有大量 `finditer/findall`、完整声明收集、表达式字符串解析。输入 token 越多，重复工作越多，整体仍接近 O(token 数 × 前缀长度)。

### 6.3 Python 增量语义引擎尚未覆盖全部规则

`IncrementalSemanticEngine.accept()` 当前主要维护作用域、声明、括号/调用框架等基础状态。真正复杂的调用匹配、表达式类型、泛型约束和 lambda 推导仍由 `PrefixSemanticChecker.probe()` 完成。不能直接删掉 probe。

### 6.4 正确性风险集中在“不完整前缀”

本题不是普通的完整程序 typecheck。以下前缀可能尚未完成，不能过早报错：

- 标识符前缀可能补全成可见符号；
- `Int` 可能继续成为 `Int64`；
- `1.`、`..`、`<`、`<=`、`<:` 等存在词法/语法歧义；
- 打开的字符串在第一个引号时已经具有 `String` 类型，但字面量尚未闭合；
- lambda 参数、泛型实参、命名参数和嵌套调用可能跨多个 cl100k token；
- 当前错误只有在“所有可能补全都非法”时才能提交。

纯 C++ 迁移最容易在这里对隐藏样例提前误报。

## 7. 推荐的纯 C++ 最终架构

```text
stdin token ID
  -> TokenTable: ID -> bytes
  -> IncrementalLexer: bytes -> stable TokenEvent + PartialLexeme
  -> NativeSyntaxChecker: 字符/PDA 语法状态
  -> IncrementalSemanticEngine
       |- Symbol/Scope stack
       |- TypeArena + type-property bitsets
       |- Declaration state
       |- Pratt/ExprFrame expression state
       |- CallFrame overload filtering
       |- ConstraintSet generic/lambda unification
       |- context database + subtype/interface closure
  -> probe(PartialLexeme) with checkpoint/rollback
  -> stdout
```

生产路径的完成标准：

- 不 `fork/exec` Python；
- 不在运行时导入 tiktoken、Lark、Pydantic、NumPy 或 Python xgrammar binding；
- 每个稳定仓颉 token 只进入语义状态机一次；
- `probe()` 只处理当前不稳定词法单元，不重新检查完整文件；
- 除维护必要的源码定位窗口外，不在每次输入时复制完整 source；
- 调试期可以保留 Python oracle，但不能进入默认 `solution` 热路径。

## 8. 建议实施顺序

### P0：建立不可破坏的基线

1. 从 `98a8304` 新建开发分支；
2. 在官方 ARM Docker 重新跑 50/50、单元测试和冷进程 benchmark；
3. 保存逐例首错 token index 与耗时 JSON；
4. 为每个公开错误样例准备一个最小修复版，确保所有前缀都不误报；
5. 保留 Python/C++ 同输入逐前缀差分工具。

任何一次改动如果无法通过精确首错回归，不得继续叠加优化。

### P1：C++ 增量词法层

新增建议文件：

```text
cpp/lexer.h
cpp/lexer.cpp
cpp/token.h
```

要求：

- 移植 `IncrementalLexer` 的“稳定 token + partial candidates”语义；
- 支持嵌套块注释、行注释、字符串、rune、raw identifier、数字、范围和多字符运算符；
- 维护小型未稳定缓冲，不重扫完整源文件；
- 对同一源码的 cl100k、逐字符和随机分片产生完全一致的 stable token 序列；
- 先只旁路运行，与 Python lexer 对比，不立即影响判定。

### P2：C++ context 与类型数据库

新增建议文件：

```text
cpp/type_system.h/.cpp
cpp/context_loader.h/.cpp
cpp/symbol_table.h/.cpp
```

核心结构：

```text
TypeId: 32-bit integer
TypeKind: primitive / nominal / generic-var / function / tuple / unknown
TypeArena: structural interning
Symbol: kind + TypeId + mutable + overload set/member table
ScopeFrame: parent + local symbols + function/loop/class/lambda flags
NominalInfo: type params + fields + methods + constructors + supers
```

预计算类型性质：

- 数值、整数、浮点、有序、可比较；
- 可迭代、可索引；
- 子类型传递闭包；
- 接口实现关系；
- 成员和重载索引。

context 可能由评测环境提供，不能只把当前 `context.json` 的内容硬编码进二进制。可以选择：

1. C++ 运行时解析兼容格式的 JSON；或
2. 如果确认平台构建阶段即可得到最终 context，则由 `build.sh` 生成紧凑二进制表。

在赛题机制没有确认前，优先采用运行时兼容加载或同时支持两种方式。

### P3：声明、作用域和控制流规则

优先迁移确定性最高、风险最低的规则：

- undefined name + 可见符号前缀 Trie；
- duplicate variable/parameter；
- `let` 禁止重新赋值，`var` 可赋值；
- break/continue 的 loop context；
- return 与当前函数/lambda context；
- class/interface 作用域和 `this`；
- 变量、函数、类、接口先声明后使用。

此阶段仍可让 Python worker检查未迁移规则，但 C++ 已经判定的规则必须做差分并记录命中率。

### P4：表达式与调用类型检查

建议使用增量 Pratt parser 或等价的 `ExprFrame` 状态，不要把 Python 正则逐条翻译成 C++ 正则。

覆盖顺序：

1. 字面量、标识符、括号、数组；
2. 一元 `-`、`!`；
3. 算术、取模、逻辑、等值、关系、range；
4. 赋值和期望类型传播；
5. 索引、成员、方法；
6. 函数/构造器/重载、位置与命名参数；
7. for iterable 与 pattern 类型。

每个 frame 在收到闭合 token 时提交类型；未闭合时保留候选状态。类型判断尽量使用 `TypeId` 和位集，不重复比较字符串。

### P5：泛型和 lambda

最后迁移高风险部分：

- 显式泛型 arity 和实参替换；
- 从普通实参向类型变量生成约束；
- 从期望函数类型向 lambda 参数传播类型；
- lambda 返回值与期望返回类型统一；
- 高阶函数、接口回调、类静态成员中的 lambda；
- 模糊推断只有在所有合法候选均失败时才报错。

`ConstraintSet` 至少需要：

```text
bind(type_variable, actual_type)
unify(expected, actual)
substitute(type)
checkpoint()/rollback()
candidate-specific constraints
```

重载候选应增量过滤，但在输入未完成时不能因为当前候选为空就立即报错；先结合 `PartialLexeme` 判断是否存在合法补全。

### P6：切断 Python worker

只有满足下列条件才移除 `SemanticWorker`：

- 公开错误样例精确首错 50/50；
- 所有对应修复样例零误报；
- 项目完整测试全部通过；
- context 变体测试通过；
- lambda/泛型专项差分通过；
- 随机分片不改变结果；
- 默认 `solution` 进程树中没有 `python3`。

删除 worker 后保留 Python 版作为测试 oracle 和紧急回退分支，不要删除 `agent/performance-semantic-engine`。

## 9. 如果时间仍然非常紧：低风险中间优化

纯 C++ 语义引擎工作量大。如果只剩几个小时，可先在混合版减少 Python 调用和全量扫描，但必须用精确首错差分证明安全：

1. C++/Python lexer 只在产生 stable token 或语义敏感 partial 时触发深语义检查；
2. 对当前 active line、active expression、当前声明和打开的 block 建立追加式缓存；
3. 声明索引只在新声明稳定时更新，不重复 `finditer` 全文件；
4. 预编译所有固定正则；
5. 为 visible symbols 建前缀 Trie，partial identifier 只做 Trie 查询；
6. 对打开字符串直接以 `String` 候选类型 probe；
7. IPC 合并不可影响逐 token 输出，因此只能合并内部计算，不能延迟 stdout。

禁止简单地“每 N 个 token 检查一次”或只在换行/分号检查，因为 undefined、字符串、成员、lambda 等错误可能要求更早的精确位置。

## 10. 测试和验收矩阵

### 10.1 必跑命令

```bash
./build.sh
python3 -m unittest discover -s tests -v
python3 main.py --test
```

冷进程公开集基准：

```bash
python3 benchmark/production_benchmark.py \
  --solution ./solution \
  --mode fast \
  --official-root ../cangjie-fragment-checker
```

官方 ARM Docker 的完整命令见 `LOCAL_TESTING_GUIDE.md`。不要只看预热后的 Python 类级 benchmark。

### 10.2 正确性门槛

- 官方公开 50 个 wrong 样例：精确 token index 50/50；
- 对应最小修复样例：全部前缀可续写；
- 项目 `main.py --test`：全部通过；
- 单元测试：当前发现 30 项，其中本机没有重建 native binary 时可能跳过 2 项；官方构建后 native 测试也必须运行；
- 额外官方/项目样例：此前曾达到 45/45 和 57/57，应继续保持；
- C++ 与 Python oracle：每个输入前缀一致；
- cl100k、逐字符、随机分片：结果一致。

### 10.3 性能门槛

每次记录：

- 冷启动至首响应；
- 单例总耗时；
- p50/p95/max；
- 输入 token 数和 stable 仓颉 token 数；
- Python worker 启动次数；
- 完整源码扫描次数；
- C++ semantic `accept/probe` 次数。

最终目标：

- 生产路径 Python 启动次数为 0；
- Lark 调用次数为 0；
- 完整源码重检次数为 0；
- 语义主路径复杂度接近 O(stable token 数)；
- 官方 ARM 环境保持 AC，并相对混合版显著降低进程内 p50/p95。

### 10.4 建议新增测试

- 每条语义规则一对 invalid/valid 样例；
- 每个公开错误样例的最小修复版；
- 多层 block、shadowing、同名重载和默认参数；
- 多接口继承、泛型接口、错误方法签名；
- 嵌套 lambda、零参数 lambda、高阶 lambda、类型变量只在返回值出现；
- 字符串/rune/注释跨任意分片；
- Unicode 标识符或 UTF-8 跨 token 字节边界（若赛题子集允许）；
- 深嵌套表达式和长文件，验证不出现 O(n²) 退化；
- ASan/UBSan 构建，检查 C++ 生命周期和越界。

## 11. 关键文件导航

| 文件 | 接手时重点 |
|---|---|
| `cpp/solution.cpp` | C++ 入口、TokenTable、XGrammar matcher、Python worker 生命周期、协议 |
| `src/native_semantic_worker.py` | 当前最直接的冷启动与全前缀重扫来源 |
| `src/prefix_semantic_checker.py` | 现有语义行为 oracle；规则完整但正则/字符串驱动，不宜原样翻译 |
| `src/incremental_semantic_engine.py` | 目标状态模型的 Python 骨架 |
| `src/incremental_lexer.py` | C++ lexer 必须保持一致的 stable/partial 语义 |
| `src/context_loader.py` | context 兼容格式和归一化规则 |
| `grammar/cangjie.gbnf` | C++ 字符级语法 |
| `grammar/cangjie_token.gbnf` | Python token 级语法/oracle |
| `benchmark/production_benchmark.py` | 冷进程、逐 token、精确首错基准 |
| `benchmark/differential_check.py` | 新旧/C++-Python 逐前缀差分入口 |
| `tests/` | 当前回归集；迁移一种规则就补一组测试 |

## 12. 开发纪律和交付要求

1. 保留每个可工作的提交，提交信息写清迁移了哪类规则；
2. 不在 AC 备份分支上直接改；
3. 不提交本地 `.venv`、生成二进制、缓存或评测日志；
4. 不为了微基准牺牲首错位置和隐藏样例泛化；
5. 第三方依赖、官方 typechecker 和 XGrammar 的来源/许可证要在设计文档与源码中标注；
6. 每次提交都说明：改了什么、为何安全、跑了哪些测试、性能前后数据；
7. C++ 版本未达到全量差分前，Python AC 版始终作为 oracle 和回退方案。

## 13. 接手后的第一个可执行任务

建议第一张任务卡只做一件事：**实现旁路的 C++ IncrementalLexer，并证明它与 Python lexer 在所有切分方式下产生同样的 stable token 与 partial candidates。**

原因是纯 C++ 语义引擎必须消费仓颉词法 token，而当前 C++ XGrammar 字符 matcher 不会向语义层暴露这种 token 事件。先解决这一层，后续作用域、类型和调用状态才能逐规则迁移，并且每一步都可与现有 Python oracle 差分验证。
