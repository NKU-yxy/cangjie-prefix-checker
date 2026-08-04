# 纯 C++ 语义引擎实施报告（2026-08-05）

## 回滚点

- 混合 AC 提交：`db113a4`
- 标签：`hybrid-ac-20260805-0022`
- 稳定包：`/Users/doufuru/Documents/编译大赛/XGrammar_submit_final.zip`
- 稳定包 SHA-256：`95c205f66fac0fb86d224d0007a625d5b2e866473bde58bf302708907e9c2f69`

纯 C++ 实验位于 `feature/pure-cpp-semantic-engine`，不会覆盖上述回滚点。

## 已实现

- `solution` 运行时不再 `fork/exec` Python worker，也不调用 Lark。
- 新增 C++ 增量 lexer、类型/作用域/调用/lambda/泛型/类与接口检查。
- 语义模型和当前函数上下文按结构提交点缓存，避免每个 BPE token 重建全部声明。
- `build.sh` 将 `context.json` 预编译为带版本头的 `generated/context.bin`；运行时只读二进制表。
- 支持 context 中的全局变量、重载、默认参数、构造器、泛型类、实例/静态成员和接口关系。
- 保留 `--pure-cpp-semantic` 为兼容无操作参数；默认入口已是纯 C++。

## 正确性验收

- 公开错误样例精确首错：`50/50`
- 官方语义语料：`45/45`
- 项目语料：`57/57`
- `unittest`：`31/31`
- 语义分片差分：`54/54 × 4`（逐字节、固定种子随机分片、cl100k、整段）
- context 变体：`7/7`
- ASan/UBSan：通过上述 `54 × 4` 分片语料
- 官方 aarch64/GCC 11 Docker：C++ 语义引擎分片测试 `54/54 × 4`，context `7/7`
- 运行时进程检查：`solution` 子进程数为 `0`

官方 Docker 的完整 XGrammar 构建尝试两次，均因镜像内 PyPI 代理在下载 `apache-tvm-ffi` 时返回 SSL EOF 而中止；这是外部依赖源问题，不是 C++ 编译错误。

## 冷进程性能

本机 50 例每例新建进程，连续三轮：

| 指标 | 混合 AC 基线 | 纯 C++ 三轮中位 | 变化 |
|---|---:|---:|---:|
| p50 | 69.60 ms | 45.98 ms | -33.9% |
| p95 | 88.01 ms | 59.84 ms | -32.0% |
| 首 token p50 | 未统一记录 | 约 12.2 ms | — |

正式构建后的复测为 `p50=45.96ms`、`p95=61.83ms`、`50/50`。

## 复现命令

```bash
./build.sh
python3 -m unittest discover -s tests -v
python3 benchmark/differential_check.py \
  --official-root ../cangjie-fragment-checker --solution ./solution
python3 benchmark/native_fragment_differential.py
python3 benchmark/native_context_differential.py
python3 benchmark/production_benchmark.py \
  --official-root ../cangjie-fragment-checker --solution ./solution
```

## 已知实现边界

运行时已经是纯 C++，但语义层仍会在结构提交点重新扫描相关声明段，并在当前表达式未完成时重算该表达式；它已不再每 token 重建整个模型，但尚不是严格的“每个词法 token 永久只处理一次”。对超长隐藏样例，后续还可将当前表达式换成持久化 Pratt/LR 栈，把结构提交点扫描也消除。
