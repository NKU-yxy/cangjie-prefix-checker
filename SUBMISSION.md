# 决赛提交说明

本仓库按以下赛题环境整理：

| 项目 | 配置 |
| --- | --- |
| 镜像 ID | `cangjie_fragment_checker_final` |
| Docker 镜像 | `docker.educg.net/compiler_system_challenge/cjchecker:v1.2` |
| 操作系统 | Ubuntu 22.04 |
| 服务器架构 | ARM |

## 生成提交包

在仓库根目录执行：

```bash
python3 tools/package_submission.py
```

这会生成 `dist/cangjie-fragment-checker-submission.zip`。归档根目录只包含源码、构建所需资源和唯一的 `build.sh`；不会包含 `solution`、`generated/` 或本地开发脚本。评测端在解压目录执行：

```bash
./build.sh
```

成功后，归档根目录会生成可执行文件 `solution`。

打包工具会在创建归档前校验：

- `context.json` 的 SHA-256 是否为 `facb628ab01a52d7ef8f2fe36ca463ccd381e02e45282c82803b793730068303`，即与决赛 `context_final.json` 相同；
- `build.sh` 是否可执行，且归档内恰好有一个；
- 归档没有预编译的 `solution` 或旧的 `build_local.sh`；
- ZIP 文件能通过完整性检测。

## Docker 预检

启动 Docker 后，可在仓库根目录运行：

```bash
docker run --rm --platform linux/arm64 \
  -v "$PWD":/work -w /work \
  docker.educg.net/compiler_system_challenge/cjchecker:v1.2 \
  bash -lc './build.sh && file solution'
```

输出应显示 `solution` 为 Linux ARM 可执行文件。此构建过程不下载依赖：token 表、上下文表生成器和 XGrammar 源码均在提交包内。

## 结果范围

`context.json` 已按决赛 `context_final.json` 对齐。历史提交记录中的 `63/100` 是旧上下文模型下的实验结果；私有决赛数据集不可在本地获取，因此不能把该历史分数承诺为当前 ZIP 的可复现评测结果。应以 Docker 构建成功和公开数据集验证为当前可复现检查。
