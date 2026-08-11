# 本地官方样例 Baseline

本目录保存最终提交 `b40791c7104be19196f5c045c17a297103ae1267` 在赛事官方
ARM64 Docker 镜像中的公开 50 例测试结果。

后续所有优化测试必须遵守项目根目录的
[`OPTIMIZATION_TESTING_CONTRACT.md`](../OPTIMIZATION_TESTING_CONTRACT.md)。未满足该条约
的结果不得替换正式 baseline 或标记为有效优化。

主要文件：

- `official_50_baseline_20260811_arm64.md`：便于阅读的逐例结果；
- `official_50_baseline_20260811_arm64.csv`：便于和后续优化版本做表格比较；
- `official_50_baseline_20260811_arm64.json`：完整元数据和 450 次实测原始值；
- `run_official_baseline.py`：可重复运行的计时与正确性校验脚本。

## 复现命令

必须在同一个一次性容器中先构建、再测试。`build.sh` 会在容器内安装并动态
链接 XGrammar；若换一个全新容器直接运行构建产物，共享库不会保留。

从项目根目录运行：

```bash
docker run --rm --entrypoint bash \
  -v "$PWD":/workspace \
  -v "/Users/doufuru/Documents/编译大赛/cangjie-fragment-checker":/official:ro \
  -w /workspace \
  docker.educg.net/compiler_system_challenge/cjchecker:20260522 \
  -lc 'set -euo pipefail; \
    export TIKTOKEN_CACHE_DIR=/official/tiktoken_cache; \
    export OFFICIAL_DOCKER_IMAGE=docker.educg.net/compiler_system_challenge/cjchecker:20260522; \
    ./build.sh >/tmp/build.log 2>&1; \
    python3 -u baseline_results/run_official_baseline.py \
      --official-root /official \
      --solution /workspace/solution \
      --warmups 1 \
      --repetitions 9 \
      --seed 20260811 \
      --output-prefix /workspace/baseline_results/official_50_baseline_next'
```

优化前后应使用同一台机器、同一镜像、同一官方样例提交和相同重复次数。主要比较
CSV 中的 `process_total_median_ms`；`detection_median_ms` 可辅助区分进程退出开销。
