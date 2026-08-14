# 第三方依赖与来源声明

本文档记录项目使用的外部依赖，并区分第三方能力、本队适配与本队独立实现。最终提交框架包含下文明确列出的 XGrammar C++ core、DLPack/PicoJSON 单头依赖以及竞赛配套参考 Typechecker；其余外部依赖通过构建环境安装或仅在开发阶段调用。

## XGrammar

- 项目：XGrammar
- 版本：v0.2.1
- 上游 commit：`5b4e9ce9e72524037ae24ecd831b9b6604d2eb48`
- 来源：<https://github.com/mlc-ai/xgrammar>
- 许可证：Apache License 2.0
- 用途：提供 GBNF 编译和语法匹配能力。
- 分发方式：`vendor/xgrammar-v0.2.1/` 包含生产构建所需的 20 个 `.cc`、31 个内部头、8 个公开头，以及 PicoJSON/DLPack 两个单头依赖。XGrammar 的完整 `LICENSE`、`NOTICE` 和逐文件 SHA-256 清单位于同一目录。
- 本地修改：`cpp/earley_parser.h`、`cpp/earley_parser.cc`、`cpp/grammar_matcher.cc` 三个 vendored 文件有醒目的本队修改声明。修改把 Earley completion 关系中的 `rule_start_pos` 精确表示为不相交区间，并为已完成历史行建立通用范围汇总；其余状态字段全部保留。该机制不按 grammar 文本、identifier 名称或长度、源码、token 化、机器或测试配置启用。
- 命名空间隔离：生产构建将 vendored core 编译到 `xgrammar_g4`；显式 debug shadow 构建才同时加载未修改的 v0.2.1 wheel，并在原 `xgrammar` 命名空间中运行 accepted-G1 旧 matcher。

### XGrammar 内含的单头依赖

- DLPack：锁定 submodule commit `bbd2f4d32427e548797929af08cfe2a9cbb3cf12`，Apache License 2.0；许可证位于 `vendor/xgrammar-v0.2.1/3rdparty/dlpack/LICENSE`。
- PicoJSON：Copyright 2009–2010 Cybozu Labs, Inc.、Copyright 2011–2014 Kazuho Oku，采用其源码头所载的两条款 BSD 风格许可；完整声明同时保留在 `picojson.h` 和相邻 `LICENSE.txt`。

## Apache TVM FFI

- 版本约束：`apache-tvm-ffi>=0.1.9`
- 来源：<https://tvm.apache.org/ffi/>
- 许可证：Apache License 2.0
- 用途：仅供显式 old/new debug shadow 构建所加载的未修改 XGrammar wheel 使用；vendored 生产 core 不依赖 TVM FFI。
- 分发方式：最终提交框架不包含 TVM FFI 源码。
- 本地修改：无。

## tiktoken

- 版本约束：`tiktoken>=0.7.0`
- 来源：<https://github.com/openai/tiktoken>
- 许可证：MIT License
- 用途：构建阶段调用其公开 API，生成本地 `cl100k_base` token 查表数据。
- 分发方式：最终提交框架不包含 tiktoken 源码。
- 本地修改：无。

## Lark

- 版本约束：`lark>=1.1.0`
- 来源：<https://github.com/lark-parser/lark>
- 许可证：MIT License
- 用途：仅在开发阶段作为离线测试所需的通用解析依赖。
- 分发方式：最终提交框架不包含 Lark 源码；随框架提供的参考 typechecker 在开发/测试时需要外部安装 Lark。
- 本地修改：无。

## 其他 Python 开发依赖

- Pydantic（`pydantic>=2.0`）：<https://github.com/pydantic/pydantic>，MIT License。
- NumPy（`numpy>=1.24`）：<https://github.com/numpy/numpy>，BSD-3-Clause License。
- typing_extensions（`typing-extensions>=4.9.0`）：<https://github.com/python/typing_extensions>，PSF License Version 2。
- 用途：用于当前纯 C++ 生产运行时之外的开发、测试或 Python 兼容支持。
- 分发方式：最终提交框架不包含上述项目的源码副本。
- 本地修改：无。

## 竞赛配套参考 Typechecker

- 项目：`cangjie-fragment-checker`
- 来源：<https://gitcode.com/bhzhan/cangjie-fragment-checker>
- 所用版本：竞赛仓库 `2026-06-07` 公开快照；现有材料未记录可进一步核验的 commit SHA，因此以来源链接、快照日期和本节修改清单共同标识。
- 许可证状态：所使用的公开快照未包含独立的 LICENSE/NOTICE 文件；本文不据此推测其通用开源许可证。
- 使用依据与用途：该项目属于竞赛配套公开参考实现。本队基于其中的 typechecker 作少量适配，用于完整程序解析、随机程序合法性标注、差分测试和实验复现。
- 运行时关系：不参与 `solution` 的编译、链接或运行。
- 提交形式：最终代码框架包含 `third_party/cangjie_typechecker/` 开发/测试副本，以便复现本文实验；它不是生产运行依赖。
- 功能性修改：相对公开版本对 `builtin_context.py`、`checker.py`、`context.json`、`type_inference.py` 和 `type_services.py` 5 个文件作了功能性适配；扣除统一的来源注释后，原开发记录约为新增 98 行、删除 76 行。这些修改用于扩充迭代类型、字符串操作、默认构造器和接口实现等离线验证覆盖。
- 合规性修改：所有支持注释的 vendored Python/Lark 源文件均增加了不影响逻辑的统一来源头；不支持注释的 `context.json` 由本文件和目录 README 统一归因。因此，按文件系统直接统计的修改文件数和新增行数会高于上述功能性修改统计。
- 原创归属：该目录的上游代码、功能性适配及来源注释均不作为本队原创成果，不计入本队原创代码量。

## 本队独立实现范围

本队独立完成 C++ 竞赛入口与语义检查器、面向赛题子集及仓颉 1.0 规范校准的 GBNF 适配、构建脚本、context/token 查表生成工具和验证工具。上述原创范围明确排除 `third_party/cangjie_typechecker/` 的上游代码及本地适配，也明确排除 `vendor/xgrammar-v0.2.1/` 的上游源码；XGrammar 三个已披露文件中的本地修改仅计为本队适配，不把其上下文实现计作原创。
