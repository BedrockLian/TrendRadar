---
name: news-secretary
slug: news-secretary
version: 7.0.0
description: 运行 TrendRadar 日报管线并把结构化结果交给 Codex 任务呈现。
metadata:
  tags: [news, trend, rss, briefing]
---

## 触发

- 日报：每日 09:00、12:00、21:00。
- 手动：用户要求生成、重跑或诊断某个时段的日报。

## 执行

在仓库根目录运行：

```text
python -m trendradar.pipeline.pipeline_orchestrator --output json
```

需要复跑指定时段时加 `--push-id morning|noon|evening`；联调时可加 `--skip-fetch`。

## 结果处理

只读取 stdout 中的单个 JSON 对象：

- `ok`：展示 `briefing`，并检查 `stats.budget.within_budget`。
- `silent`：记录本轮没有新内容，不补造摘要。
- `busy`：保留正在运行的任务，避免并发重跑。
- `error`：展示 `errors` 和 `artifacts` 路径，进入 self-healing 流程。

晚间 `needs_deep_analysis=true` 时，Codex 可按主题拆分研究任务；分析结果使用 `render_deep_analysis.py` 的标准 Markdown 规范。

## 参考

统一读取：`../../../docs/INDEX.md`、`PIPELINE.md`、`OPERATIONS.md`、`TRAPS.md`。
