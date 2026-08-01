# Codex 计划与运维

## 时间表

时间、描述、入口、时区和预算唯一来源是 `src/trendradar/config/plan.json`。当前任务如下：

| 任务 | 时间 |
|---|---|
| 自动体检 | 每日 15:00 |
| 每日维护 | 每日 03:00 |
| 输出看门狗 | 09:10、12:10、21:10 |
| 日报 | 09:00、12:00、21:00 |
| 周报 | 周一 09:30 |
| 月报 | 每月 1 日 09:00 |

时区为 `Asia/Shanghai`。运行脚本只输出 JSON 和 Markdown；Codex 任务读取结果后，将报告 Markdown 本体直接输出到当前聊天框。产物路径和本地预览只用于审计与排障，不能替代正文。

## 入口

```text
python ops/codex/health_check.py
python ops/codex/maintenance.py
python ops/codex/output_watchdog.py --slot morning|noon|evening
python -m trendradar.reporting.report_task --period weekly|monthly
```

## 排障顺序

1. 查看 stdout JSON 的 `status`、`errors`、`failed_checks` 和 `timing`。
2. 查看 `.runtime/data/run_log.jsonl`、`.runtime/data/push_log.json` 和 `.runtime/outputs/`。
3. 检查 `.runtime/locks/` 是否有真实运行中的锁；过期锁会自动回收。
4. 先用 `--skip-fetch` 验证渲染和指纹阶段，再恢复完整抓取。
5. 用 Python 3.14.5 运行测试和 `--check-version`。

## 结果保留

日报 Markdown 写入 `outputs/YYYY-MM-DD/<slot>.md`，同时存档到 `archive/YYYY-MM-DD/<slot>.md`。看门狗只核验产物和耗时，不重复执行任务。
