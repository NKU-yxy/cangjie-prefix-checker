# XGrammar 本地测试与计时评测指南

这篇文档记录如何在本机 Docker Desktop 中复现赛程官网的构建、测试、公开样例评测，以及如何看到每个样例的运行用时。

## 1. 当前目录说明

本地项目目录：

```bash
/Users/doufuru/Documents/编译大赛/XGrammar
```

官方公开测试仓库目录：

```bash
/Users/doufuru/Documents/编译大赛/cangjie-fragment-checker
```

官方 Docker 镜像：

```bash
docker.educg.net/compiler_system_challenge/cjchecker:20260522
```

提交包：

```bash
/Users/doufuru/Documents/编译大赛/XGrammar_submit.zip
```

本地结果目录：

```bash
/Users/doufuru/Documents/编译大赛/XGrammar/local_results
```

## 2. 每次测试前的准备

先打开 Docker Desktop，确认左下角没有报错，右下角显示 Docker 已运行。

然后打开终端，进入项目目录：

```bash
cd "/Users/doufuru/Documents/编译大赛/XGrammar"
```

检查 Docker 是否可用：

```bash
docker info --format '{{.OSType}} {{.Architecture}} {{.ServerVersion}}'
```

正常输出类似：

```text
linux aarch64 29.5.3
```

如果提示 `permission denied while trying to connect to the docker API`，通常是 Docker Desktop 还没有完全启动，等几秒再试。

## 3. 拉取官方 Docker 镜像

第一次使用需要拉取镜像：

```bash
docker pull docker.educg.net/compiler_system_challenge/cjchecker:20260522
```

以后镜像已经存在时，可以不用重复拉取。

## 4. 在官方环境里构建项目

下面这条命令会把当前项目目录挂载到容器的 `/workspace`，然后执行 `build.sh`。

```bash
docker run --rm --entrypoint bash \
  -v "$PWD":/workspace \
  -w /workspace \
  docker.educg.net/compiler_system_challenge/cjchecker:20260522 \
  -lc 'set -euo pipefail; chmod +x build.sh; ./build.sh; ls -l solution'
```

看到类似下面的输出，就说明构建成功：

```text
-rwxr-xr-x 1 root root 117 ... solution
```

`solution` 是平台最终会运行的可执行入口。

## 5. 跑项目自带单元测试

这条命令会在同一个官方容器环境里先构建，再运行项目自带测试：

```bash
docker run --rm --entrypoint bash \
  -v "$PWD":/workspace \
  -w /workspace \
  docker.educg.net/compiler_system_challenge/cjchecker:20260522 \
  -lc 'set -euo pipefail; ./build.sh; python3 -m unittest discover -s tests -v'
```

当前结果：

```text
Ran 12 tests
OK
```

## 6. 跑项目内置 CLI 测试

项目的 `main.py --test` 里有更多语法/语义样例：

```bash
docker run --rm --entrypoint bash \
  -v "$PWD":/workspace \
  -w /workspace \
  docker.educg.net/compiler_system_challenge/cjchecker:20260522 \
  -lc 'set -euo pipefail; ./build.sh; python3 main.py --test'
```

当前结果：

```text
Total: 57 passed, 0 failed out of 57 tests
```

## 7. 跑官方公开 50 个 wrong 样例

官方公开仓库已经拉在：

```bash
/Users/doufuru/Documents/编译大赛/cangjie-fragment-checker
```

如果这个目录不存在，可以重新拉取：

```bash
cd "/Users/doufuru/Documents/编译大赛"
git clone https://gitcode.com/bhzhan/cangjie-fragment-checker.git
cd "/Users/doufuru/Documents/编译大赛/XGrammar"
```

运行 50 个公开 wrong 样例：

```bash
docker run --rm --entrypoint bash \
  -v "$PWD":/workspace \
  -v "/Users/doufuru/Documents/编译大赛/cangjie-fragment-checker":/official \
  -w /workspace \
  docker.educg.net/compiler_system_challenge/cjchecker:20260522 \
  -lc 'set -euo pipefail; ./build.sh >/tmp/xgrammar_build.log 2>&1; python3 /workspace/local_results/run_official_wrong_samples.py'
```

当前结果：

```text
PUBLIC WRONG SAMPLES: 50/50 PASSED
```

## 8. 跑带每个样例用时的评测

这是你后续做优化时最常用的命令。它会输出类似官网的：

```text
err_undefined: 1.163s
err_assign_let: 1.874s
...
```

运行命令：

```bash
docker run --rm --entrypoint bash \
  -v "$PWD":/workspace \
  -v "/Users/doufuru/Documents/编译大赛/cangjie-fragment-checker":/official \
  -w /workspace \
  docker.educg.net/compiler_system_challenge/cjchecker:20260522 \
  -lc 'set -euo pipefail; ./build.sh >/tmp/xgrammar_build.log 2>&1; python3 -u /workspace/local_results/run_official_wrong_samples_timed.py 2>&1 | tee /workspace/local_results/official_wrong_samples_timed_$(date +%Y%m%d_%H%M%S).log'
```

注意这里必须保留：

```bash
set -euo pipefail
```

它能保证 `build.sh` 如果失败，测试会立刻停止，而不是继续跑出误导性的失败结果。

也建议保留：

```bash
python3 -u
```

`-u` 表示无缓冲输出，这样每个样例跑完后会立刻显示，不用等全部结束。

当前正式计时结果文件：

```bash
local_results/official_wrong_samples_timed_20260614_085646.log
```

当前结果：

```text
PUBLIC WRONG SAMPLES: 50/50 PASSED
```

当前最慢 10 个样例：

```text
err_assign_let: 1.874s
err_arity: 1.818s
err_lambda_hof_explicit: 1.407s
err_lambda_infer_ambiguous_2: 1.278s
err_lambda_infer_wrong_return_2: 1.255s
err_continue_outside_loop: 1.202s
err_lambda_return_type_explicit: 1.174s
err_undefined: 1.163s
err_lambda_interface_callback_explicit: 1.163s
err_array_index_not_int64: 1.132s
```

## 9. 查看已有测试结果

查看汇总：

```bash
cat local_results/SUMMARY.md
```

查看完整 Docker 测试日志：

```bash
cat local_results/docker_eval_20260614_083420.log
```

查看官方公开样例通过情况：

```bash
cat local_results/official_wrong_samples_20260614_084021.log
```

查看逐样例计时结果：

```bash
cat local_results/official_wrong_samples_timed_20260614_085646.log
```

查看 benchmark JSON：

```bash
cat benchmark/benchmark_report.json
```

## 10. 单独测试某一个官方样例

如果你只想看一个慢样例，比如 `err_assign_let`：

```bash
docker run --rm --entrypoint bash \
  -v "$PWD":/workspace \
  -v "/Users/doufuru/Documents/编译大赛/cangjie-fragment-checker":/official \
  -w /workspace \
  docker.educg.net/compiler_system_challenge/cjchecker:20260522 \
  -lc 'set -euo pipefail; ./build.sh >/tmp/xgrammar_build.log 2>&1; cd /official; time python3 scripts/token_interaction_test.py wrong/err_assign_let.cj --cmd /workspace/solution'
```

如果输出：

```text
PASSED
```

说明该样例判断正确。`time` 会额外显示本地运行时间。

## 11. 跑真实生产 benchmark 与差分测试

旧的 `benchmark/benchmark.py` 是预热后的离线测试，不能代表提交耗时。真实
基准会为每个样例启动全新 `solution` 进程，并校验精确首次报错 token：

```bash
python3 benchmark/production_benchmark.py --solution ./solution --mode fast
```

再运行官方公开位置和官方 typechecker 额外程序的差分：

```text
python3 benchmark/differential_check.py --mode fast

当前本机结果：公开错误位置 `50/50`，官方额外语义程序 `45/45`；冷进程
`total_p50≈231ms`、`p95≈249ms`。具体数值会随机器和 ARM Docker 环境变化。
```

## 12. 重新生成提交 zip

提交平台要求 zip 根目录直接包含 `build.sh`，不能再套一层 `XGrammar/`。

在项目目录运行：

```bash
cd "/Users/doufuru/Documents/编译大赛/XGrammar"
zip -r ../XGrammar_submit.zip . \
  -x './.venv/*' \
  -x './__pycache__/*' \
  -x './*/__pycache__/*' \
  -x './*/*/__pycache__/*' \
  -x './.DS_Store'
```

检查 zip 根目录是否有 `build.sh`：

```bash
unzip -l ../XGrammar_submit.zip | sed -n '1,40p'
```

应该能看到：

```text
build.sh
solution.py
requirements.txt
src/
grammar/
third_party/
```

提交文件：

```bash
/Users/doufuru/Documents/编译大赛/XGrammar_submit.zip
```

## 13. 常见问题

### `chmod: cannot access 'build.sh': No such file or directory`

说明 zip 根目录没有 `build.sh`。通常是你压缩了外层文件夹，导致结构变成：

```text
XGrammar/build.sh
```

正确结构必须是：

```text
build.sh
solution.py
src/
```

### Docker 里找不到文件

优先检查挂载路径：

```bash
docker run --rm --entrypoint bash \
  -v "$PWD":/workspace \
  -w /workspace \
  docker.educg.net/compiler_system_challenge/cjchecker:20260522 \
  -lc 'pwd; ls -la'
```

能看到 `build.sh` 才说明挂载正确。

### 本机 Python 跑不起来

本机 macOS 默认 Python 可能是 3.9，而项目代码需要 Python 3.10+。不要优先在本机 Python 跑，优先用官方 Docker 镜像。

### 某次日志显示全失败

如果命令没有写：

```bash
set -euo pipefail
```

可能出现 `build.sh` 已失败但评测继续运行的情况，结果会失真。正式计时请使用第 8 节的命令。
