# 仓颉代码片段前缀语义检查器

> 2026 年全国大学生计算机系统能力大赛——编译系统挑战赛
> 队伍：圆周运动
>
> 队伍编号：T2026100552010674
>
> 学校：南开大学

## 0. 原视频链接
因为Gitlab上传对文件大小有所限制，于是上传的讲解视频进行了压缩，原先高清的讲解视频链接如下：
通过网盘分享的文件：T2026100552010674_圆周运动_讲解视频_高清版本.mp4
链接: https://pan.baidu.com/s/19iBwn5oMeXHBQ_7GzI058g?pwd=g568 提取码: g568

## 1. 项目简介

本项目是一个面向仓颉语言子集的流式前缀检查器。评测程序会逐个输入 `cl100k_base` token ID，检查器需要在每个 token 到达后立即判断：

- 当前源码前缀是否仍可能续写成语法和语义合法的仓颉程序；
- 或者已经出现无法通过后续输入修复的错误。

项目默认输出协议为：

```text
0 = 当前前缀仍可续写
1 = 当前前缀已确定错误
```

使用 `--competition-output` 参数时，输出翻转为赛题约定：

```text
1 = 当前前缀仍可续写
0 = 当前前缀已确定错误
```

默认生产入口在构建后为运行时纯 C++ 实现。

## 2. 当前状态

当前结果：

- 公开错误样例精确首错 `50/50`；
- 官方语义语料 `45/45`；
- 项目语料 `57/57`；
- 固定原生分片差分 `66/66 × 4`；
- context 变体 `7/7`；
- Python 单元测试 `34/34`；
- `360` 个隐藏样例式随机程序、`1800` 次分片执行，失败 `0`；
- `180` 个合法程序在所有观测前缀上零误报；
- 真实 `solution` 协议随机样例 `48/48`；
- ASan/UBSan 随机样例 `24 × 5`通过。


## 3. 核心能力

当前实现覆盖：

- cl100k token ID 到原始字节的本地解码；
- UTF-8 跨 token 分片；
- 嵌套块注释、行注释、字符串、数字、标识符和多字符运算符的增量词法处理；
- XGrammar 字符级语法状态；
- 变量、参数、函数、类、接口和 lambda 作用域；
- `let` / `var` 可变性检查；
- `break` / `continue` / `return` 上下文；
- if/while Bool 条件；
- for 可迭代性和 HashMap 绑定模式；
- 一元、二元、range、数组、索引和成员访问；
- 函数、方法、构造器、重载、命名参数和默认参数；
- 泛型实参、类型变量统一和 lambda 期望类型传播；
- 接口实现、方法签名匹配、传递泛型接口继承；
- 未完成标识符和部分词法单元的保守试探。

## 4. 运行时架构

```text
stdin: cl100k token ID
        │
        ▼
generated/cl100k_base.bin
token ID → 原始字节
        │
        ├─→ XGrammar 字符级语法状态
        │
        └─→ C++ IncrementalLexer
               │
               ▼
          NativeSemanticChecker
          作用域 / 类型 / 调用 / lambda / 泛型 / 接口
               │
               ▼
stdout: 0/1
```

构建阶段允许 Python 生成 token/context 二进制表。生产 `solution` 运行时只在当前 C++ 进程内执行语法和语义检查。

## 5. 目录结构

```text
XGrammar/
├── build.sh
├── solution                 # 构建前是启动脚本；构建后是 C++ 二进制
├── solution.py              # Python 调试/oracle 入口
├── context.json
├── cpp/
│   ├── solution.cpp           # 竞赛协议、token 解码和 XGrammar 语法状态
│   ├── native_semantic.cpp    # C++ 词法和语义引擎
│   └── native_semantic.h
├── grammar/
│   ├── cangjie.gbnf          # C++ 生产入口字符级语法
│   └── cangjie_token.gbnf    # Python oracle token 级语法
├── generated/                # build.sh 生成，不应作为源码提交
├── tools/
│   ├── generate_cl100k_table.py
│   ├── generate_context_table.py
│   └── native_semantic_driver.cpp
├── benchmark/
│   ├── differential_check.py
│   ├── native_fragment_differential.py
│   ├── native_context_differential.py
│   ├── hidden_semantic_fuzz.py
│   └── production_benchmark.py
├── tests/
├── src/                      # Python oracle、历史实现和回归支持
└── third_party/cangjie_typechecker/
```

## 6. 获取源码

项目仓库：[https://gitlab.eduxiji.net/T2026100552010674/project3230617-388044.git](https://gitlab.eduxiji.net/T2026100552010674/project3230617-388044.git)

仓库只维护 `master` 分支。推荐使用以下命令获取完整源码：

```bash
git clone --branch master --single-branch https://gitlab.eduxiji.net/T2026100552010674/project3230617-388044.git
cd project3230617-388044
```

已有本地仓库时，可更新 `master` 分支：

```bash
git switch master
git pull --ff-only origin master
```

## 7. 环境与依赖

### 7.1 竞赛运行环境

项目最终功能和性能结果来自赛题限定环境：

| 项目 | 配置 |
|---|---|
| 镜像 ID | `0522_cangjie_fragment_checker` |
| Docker 镜像 | `docker.educg.net/compiler_system_challenge/cjchecker:20260522` |
| 操作系统 | Ubuntu 22.04 |
| 服务器架构 | ARM |

本地构建需要：

- Python 3.9 或更高版本；
- `pip`；
- 支持 C++17 的 `c++`、`g++` 或 `clang++`；
- Linux 或 macOS；
- 首次安装依赖时可访问 Python 软件源。

### 7.2 `requirements.txt`

仓库根目录的 `requirements.txt` 包含构建、测试和 Python 差分工具所需依赖：

```text
tiktoken>=0.7.0
lark>=1.1.0
apache-tvm-ffi>=0.1.9
pydantic>=2.0
numpy>=1.24
typing-extensions>=4.9.0
```

安装依赖：

```bash
python3 -m pip install --user -r requirements.txt
```

`build.sh` 还会检查 XGrammar C++ 头文件和共享库；环境中缺少 XGrammar 时，脚本会安装固定版本 `xgrammar==0.2.1`。仅希望构建竞赛程序时，也可以直接执行 `build.sh`，由脚本检查并补齐生产依赖。

## 8. 构建

在项目根目录执行：

```bash
chmod +x build.sh
./build.sh
```

构建脚本会完成以下工作：

1. 检查并安装必要的 Python 构建依赖；
2. 生成 `cl100k_base` token 二进制查表；
3. 将 `context.json` 转换为原生上下文表；
4. 使用 C++17 和 `-O3` 编译纯 C++ 检查器；
5. 将项目根目录的 `solution` 更新为可执行文件。

构建产物：

```text
solution
generated/cl100k_base.bin
generated/context.bin
```

可检查 `solution` 的文件类型：

```bash
file solution
```

Linux 环境应显示 ELF，macOS 环境应显示 Mach-O。评测和性能测试均应在成功执行 `build.sh` 后进行。

## 9. 启动与输入输出协议

### 9.1 输入格式

`solution` 从标准输入逐行读取十进制 `cl100k_base` token ID，并为每个 token 输出一行判断结果。输入内容是 token ID 序列，直接输入仓颉源码文本无法得到正确结果。

基本启动命令：

```bash
./solution
```

使用文件提供 token ID：

```bash
./solution < token_ids.txt
```

### 9.2 默认协议：当前公开评测 harness

默认模式与当前公开评测 harness 一致：

| 输出 | 含义 |
|---:|---|
| `0` | 当前源码前缀仍可继续补全 |
| `1` | 已发现不可恢复的语法或语义错误 |

启动命令：

```bash
./solution < token_ids.txt
```

检查器在首次确定错误时输出 `1`，随后结束当前输入处理。当前平台 AC 结果使用这一协议。

### 9.3 赛题文字协议：`--competition-output`

若官方评测采用赛题说明中的约定，即 `1` 表示可继续、`0` 表示错误，请添加 `--competition-output`：

```bash
./solution --competition-output < token_ids.txt
```

| 输出 | 含义 |
|---:|---|
| `1` | 当前源码前缀仍可继续补全 |
| `0` | 已发现不可恢复的语法或语义错误 |

`--competition-output` 只翻转输出数字，不改变词法、语法、语义判断及首错位置。提交或部署时应根据官方评测程序采用的协议选择启动命令：当前公开 harness 使用默认模式；采用赛题文字协议时使用 `--competition-output`。

### 9.4 指定上下文表

默认从项目根目录读取 `generated/context.bin`。需要显式指定时使用：

```bash
./solution --context generated/context.bin < token_ids.txt
```

原生入口接收 `.bin` 上下文表。修改 `context.json` 后应重新执行 `./build.sh`，生成对应的 `generated/context.bin`。

## 10. 快速运行示例

下面的命令将一段仓颉程序编码为 `cl100k_base` token ID：

```bash
python3 - <<'PY' > /tmp/cangjie_tokens.txt
import tiktoken

source = """main(): Unit {
    let value: Int64 = 42
    println(value)
}
"""

encoding = tiktoken.get_encoding("cl100k_base")
for token_id in encoding.encode(source):
    print(token_id)
PY
```

使用当前公开 harness 的默认协议运行：

```bash
./solution < /tmp/cangjie_tokens.txt
```

该合法程序的每轮输出均为 `0`。若评测采用赛题文字协议，则运行：

```bash
./solution --competition-output < /tmp/cangjie_tokens.txt
```

此时该合法程序的每轮输出均为 `1`。

## 11. 测试与验证

构建完成后，可运行核心回归：

```bash
python3 -m unittest discover -s tests
python3 benchmark/native_fragment_differential.py
python3 benchmark/native_context_differential.py
python3 benchmark/hidden_semantic_fuzz.py --seed 20260805 --cases-per-family 12 --solution ./solution
```

仓库还提供 `113` 个固定综合样例，覆盖 `47` 个完整合法程序、`56` 个已提交错误和
`10` 个仍可继续补全的截断前缀。运行器会复核完整程序标签，并通过真实
`cl100k_base` 逐 token 协议检查首次拒绝和安全前缀：

```bash
python3 tools/run_comprehensive_cases.py --solution ./solution
python3 tools/run_comprehensive_cases.py --solution ./solution --check-competition-output
```

样例分类、筛选方式、JSON 报告和确定性重新生成方法见
[`test_cases/comprehensive/README.md`](test_cases/comprehensive/README.md)。

若已在项目同级目录准备竞赛配套的 `cangjie-fragment-checker` 仓库，可运行公开样例精确首错差分和冷进程性能测试：

```bash
python3 benchmark/differential_check.py --solution ./solution
python3 benchmark/production_benchmark.py --solution ./solution
```

测试脚本默认按照公开 harness 的 `0=可继续、1=错误` 协议读取 `solution` 输出。

## 12. Python 调试入口

`solution.py` 保留为 Python 差分和调试入口。直接运行方式如下：

```bash
python3 solution.py < token_ids.txt
```

它支持与 C++ 入口一致的输出翻转参数：

```bash
python3 solution.py --competition-output < token_ids.txt
```

Python 入口还提供 `fast`、`checkpoint` 和 `legacy` 三种差分模式：

```bash
python3 solution.py --semantic-mode fast < token_ids.txt
python3 solution.py --semantic-mode checkpoint < token_ids.txt
python3 solution.py --semantic-mode legacy < token_ids.txt
```

正式评测应先执行 `./build.sh`，随后使用构建生成的纯 C++ `solution`。

## 13. 调试

需要查看原生语义检查器的拒绝原因时，可设置：

```bash
CANGJIE_DEBUG_SEMANTIC=1 ./solution < token_ids.txt
```

调试信息写入标准错误流，标准输出仍只包含逐 token 的 `0` 或 `1`。

## 14. 常见问题

### `solution` 启动后进入 Python 或提示 Python 依赖错误

仓库中的初始 `solution` 是 Python 包装脚本。请先运行 `./build.sh`，再使用 `file solution` 确认其已经成为原生可执行文件。

### 提示 `cannot open token table`

确认 `generated/cl100k_base.bin` 已生成，并从项目根目录运行 `solution`。`solution`、`generated/` 和 `grammar/` 需要保持仓库中的相对目录结构。

### 提示 `cannot open grammar`

确认 `grammar/cangjie.gbnf` 存在，并从项目根目录启动程序。

### XGrammar 或 TVM FFI 共享库无法加载

重新执行 `./build.sh`。构建脚本会定位 XGrammar 与 TVM FFI 的共享库并写入运行时搜索路径。Linux 环境还应确认 XGrammar 和 TVM FFI 来自当前 Python 环境。

### 应该使用哪一种输出协议

- 当前公开 harness 和项目测试：直接运行 `./solution`，使用 `0=可继续、1=错误`；
- 官方若采用赛题文字约定：运行 `./solution --competition-output`，使用 `1=可继续、0=错误`。

协议切换无需重新编译，也不会改变首错位置。

### 平台耗时与本地耗时存在差异

平台耗时包含容器启动、资源限制和调度开销。性能对比应使用同一环境、同一批样例和相同统计口径。

## 15. 第三方依赖与来源

- [XGrammar v0.2.1](https://github.com/mlc-ai/xgrammar)：提供通用 GBNF 编译和字符级语法匹配能力，采用 Apache License 2.0；
- [Apache TVM FFI](https://tvm.apache.org/ffi/index.html)：提供 XGrammar 原生共享库依赖；
- [tiktoken](https://github.com/openai/tiktoken)：用于构建期生成 `cl100k_base` token 查表数据，采用 MIT License；
- [cangjie-fragment-checker](https://gitcode.com/bhzhan/cangjie-fragment-checker)：竞赛配套公开样例、交互测试工具和 typechecker 来源。

第三方依赖、许可证、分发方式和本队原创边界统一记录在 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md) 中。最终提交框架不包含 XGrammar、TVM FFI、tiktoken 或 Lark 的源码副本；前三者按构建或运行需要从外部环境安装，Lark 仅用于开发测试。

最终提交框架包含 `third_party/cangjie_typechecker/`。该目录基于竞赛配套公开仓库 [cangjie-fragment-checker](https://gitcode.com/bhzhan/cangjie-fragment-checker) 中的 typechecker，由本队作少量开发期适配，仅用于完整程序解析、差分测试、随机程序合法性标注和实验复现，不参与 `solution` 的编译、链接或运行。该目录及其本地修改均不作为本队原创成果，也不计入本队原创代码量；具体来源、修改文件和边界见目录内 README 与 `THIRD_PARTY_NOTICES.md`。生产运行路径由本队编写的 C++ 检查器、面向赛题子集适配的仓颉 GBNF、构建与数据生成工具，以及外部安装的 XGrammar/TVM FFI 依赖构成。
