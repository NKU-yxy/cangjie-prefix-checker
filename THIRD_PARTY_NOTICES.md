# 第三方依赖与来源声明

最终提交包中的 C++ 入口、增量语义检查器、仓颉 GBNF 适配、构建脚本和
查表生成工具均由本队独立实现。以下第三方项目按其许可证随包分发或在
生成阶段使用。

## XGrammar C++ Core

- 项目：XGrammar
- 版本：`0.2.1`，上游 tag `v0.2.1`
- 上游 commit：`5b4e9ce9e72524037ae24ecd831b9b6604d2eb48`
- 来源：<https://github.com/mlc-ai/xgrammar>
- 许可证：Apache License 2.0
- 用途：提供 GBNF 编译和增量语法匹配能力。
- 随包内容：`third_party/xgrammar_core/` 中仅包含构建所需的公开 C++ core、
  头文件、许可证及 NOTICE；不包含 Python/TVM FFI 绑定、测试和无关工具。
- 本地修改：上游文件内容未作功能性修改，仅按提交目录布局选择性分发。

XGrammar 使用的 DLPack 头文件按 Apache License 2.0 分发，其许可证位于
`third_party/xgrammar_core/third_party/dlpack/LICENSE`。PicoJSON 头文件
保留了其 BSD-2-Clause 版权与许可证全文。

## tiktoken

- 版本：`0.13.0`（构建表生成阶段）
- 来源：<https://github.com/openai/tiktoken>
- 许可证：MIT License
- 用途：通过判题镜像预装的公开 API 与离线缓存生成
  `generated/cl100k_base.bin`。
- 分发方式：提交包不包含 tiktoken 源码或二进制；运行阶段也不导入
  tiktoken。生成表 SHA-256 为
  `308b0361bc24138a3ba3b3659cc09083f2d8fcd5dcd080a407b499e97cc2fd34`。

## 竞赛官方上下文

`generated/context.bin` 由决赛官方 `context_final.json`（提交包中按构建约定
命名为 `context.json`）通过本队生成工具生成，SHA-256 为
`2cf015b7f60f4d6fbb89a805e4d11daeaae0e70061f6a5813c94dcf0586ec113`。
竞赛配套参考 Typechecker 仅用于开发期差分测试，不参与最终程序的编译、
链接或运行，也不包含在提交包中。
