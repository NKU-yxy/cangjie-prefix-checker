队伍名字：圆周运动

队伍号码：T2026100552010674

学校：南开大学

## 当前实现

默认 `solution` 在 `build.sh` 后为纯 C++ 运行时，不启动 Python
worker。实现、测试、性能与回滚信息见
[`PURE_CPP_REPORT_20260805.md`](PURE_CPP_REPORT_20260805.md)。历史 Python/C++ 混合版交接信息仍保留在
[`TEAMMATE_HANDOFF.md`](TEAMMATE_HANDOFF.md)。

提交前建议至少运行：

```bash
./build.sh
python3 benchmark/differential_check.py --solution ./solution
python3 benchmark/hidden_semantic_fuzz.py --seed 20260805 --cases-per-family 12
```

隐藏样例式随机生成器会用官方完整程序类型检查器标注结果，并检查多行声明、嵌套 lambda、重载歧义、泛型继承、作用域隔离与合法程序零误报。
