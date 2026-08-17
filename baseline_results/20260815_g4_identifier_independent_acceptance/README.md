# G4-029 长标识符稳健性独立验收归档

最终结论：冻结候选 `029531cecaea28b765455559805fe45c31011b54` 的 G4 定向验收为 **ACCEPTED / RELEASE-READY**。归档为 sealed，`blockers=[]`。官方 50 例的通用性能分类仍是 **NO PROVEN GAIN**，详细边界见 `FINAL_REPORT.md`。

## 发布文件

- `g4-029-identifier-independent-acceptance.tar.gz`：完整、确定性证据包，94,182,816 bytes。
- `g4-029-identifier-independent-acceptance.tar.gz.sha256`：压缩包外部 SHA-256 绑定。
- `inventory.json`：sealed 证据清单的便捷副本。
- `CONTENT_SHA256SUMS`：包内完整内容清单的便捷副本；权威校验对象是解压后的同名文件。
- `verify_archive.py`、`inventory.schema.json`：便携校验器及模式副本。
- `ARCHIVE_BUILD_REPORT.json`：双 stage、双 tar、双解压与篡改拒绝结果。

## 校验

在本目录先校验压缩包：

```sh
shasum -a 256 -c g4-029-identifier-independent-acceptance.tar.gz.sha256
```

然后解压并运行包内校验器：

```sh
mkdir /private/tmp/g4-029-verify
tar -xzf g4-029-identifier-independent-acceptance.tar.gz -C /private/tmp/g4-029-verify
python3 /private/tmp/g4-029-verify/g4-029-identifier-independent-acceptance/tools/verify_archive.py \
  /private/tmp/g4-029-verify/g4-029-identifier-independent-acceptance
```

成功结果应包含 `status: PASS`、`sealed: true` 和空 `blockers`。
