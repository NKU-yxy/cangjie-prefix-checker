# v14-AORTA Patch 0 — 基线冻结（2026-08-19）

## 冻结对象：v12-F1-L（官网 63/100）

- 分支：`v14-aorta`，自 `09abd7c`（v12-F1-L 官方 63/100 记录提交）创建
- 基线官方名单：`/tmp/v12L_official.txt`（63 例）
- 基线交付 zip：`cangjie-checker_v12_F1_L_20260818.zip`（897,751 B，
  sha256 `0a2e8590bf9d20e2c55b1f7edebc390beba6d8df8ecd4dd0e9d3149448f1f2a0`）
- 基线 solution：sha256 `fe20e47ad204e9220982de7377bd1ba0f895cf886b4b21539d686495d98b6ee4`
  （2017048 B）

## 本地复验（分支重建）

| 验证项 | 结果 |
|---|---|
| 重建 solution 字节 | `fe20e47a...` 与基线完全一致 ✓ |
| 官网 harness wrong（50 例） | 49/50（唯一失败 = err_arraylist_toarray_assign 309-vs-308，v10 起已知永久偏差） |
| 官网 harness wrong2（50 例） | 50/50 ✓ |
| 代表性用例 stdout（toarray_assign / callback_explicit） | 与基线二进制逐字节一致 ✓ |

## 本 patch 变更

- `cpp/solution.cpp`：新增 `CANGJIE_TRACE_FIRE` JSONL fire trace（默认关闭，
  行为与基线逐 token 一致；stderr 输出，不污染 stdout）：
  `{"event":"fire","token":N,"syntax_ok":bool,"message":"..."}`
- `tools/jsonl 验证`：trace 输出为合法 JSON（已用 json.loads 验证）
- 门禁/行为：零变化（trace 关闭路径与基线字节一致）

## 后续 patch 的 trace 扩展点

- Patch 2 起在 CheckStatus 增加 frontier 载荷（symbol_kind/tail/boundary），
  由 solution.cpp 的 trace 点统一输出。
