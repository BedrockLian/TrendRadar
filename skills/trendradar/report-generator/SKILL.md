---
name: report-generator
slug: report-generator
version: 2.0.0
description: 为 Codex 计划任务准备周报和月报的可追溯数据证据。
metadata:
  tags: [report, research, weekly, monthly]
---

## 触发

- 周报：周一 09:30。
- 月报：每月 1 日 09:00。
- 手动：用户要求总结最近一周或一月趋势。

## 执行

```text
python -m trendradar.reporting.report_task --period weekly
python -m trendradar.reporting.report_task --period monthly
```

脚本只返回最近 curated 数据文件和结构化统计入口。Codex 根据证据生成 Markdown，标注来源和时间范围；没有数据时返回 `silent`。

## 参考

`../../../docs/INDEX.md`、`PIPELINE.md`、`OPERATIONS.md`。
