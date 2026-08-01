---
name: self-healing
slug: self-healing
version: 4.0.0
description: 检查 TrendRadar 本地运行时、任务结果和性能预算。
metadata:
  tags: [trendradar, health, maintenance, watchdog]
---

## 任务

- 体检：每日 15:00，运行 `ops/codex/health_check.py`。
- 维护：每日 03:00，运行 `ops/codex/maintenance.py`。
- 看门狗：09:10、12:10、21:10，运行 `ops/codex/output_watchdog.py --slot <slot>`。

每个入口 stdout 只返回一个 JSON 对象。异常交给 Codex 任务报告，不自动编造或重复生成日报。

## 诊断顺序

1. 先看 `status`、`failed_checks` 或 `reason`。
2. 再看 `TRENDRADAR_HOME`、`data/run_log.jsonl` 和 `outputs/`。
3. 若 `stats.budget.within_budget=false`，优先减少网络等待和重复磁盘读写。
4. 修复后用本机 Python 3.14.5 运行 `pytest` 和 `--check-version`。

## 参考

`../../../docs/INDEX.md`、`OPERATIONS.md`、`TRAPS.md`。
