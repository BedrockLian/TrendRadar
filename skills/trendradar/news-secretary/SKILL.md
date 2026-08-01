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

- `ok`：检查 `stats.budget.within_budget`，然后把 `briefing` 字段的完整 Markdown 原文直接作为当前聊天消息输出。
- 如果 `stats.llm_stats.status` 为 `needs_codex`，读取 `translation_queue`，由 Codex 直接翻译标题和摘要，保存为 URL 对齐的 JSON 响应后执行：
  `python -m trendradar.cli.codex_direct_translate --push-id <slot> --response <response.json>`，然后重新渲染并展示最终 Markdown。
- Codex 直出必须保留原文事实和来源链接；不得把原文复制到 `title_cn`/`summary_cn`，也不得生成 `[未翻译]`、`[翻译失败]` 等占位文本。
- `silent`：记录本轮没有新内容，不补造摘要。
- `busy`：保留正在运行的任务，避免并发重跑。
- `error`：展示 `errors` 和 `artifacts` 路径，进入 self-healing 流程。

## 生产聊天直出契约

- 最终回复必须是 `briefing` 中的 Markdown 本体，让聊天框直接渲染标题、加粗、列表和来源链接。
- 不要把完整 Markdown 放进代码围栏；不要只返回 `.md` 文件路径、artifact 路径、本地预览页面或浏览器链接。
- 本地文件和预览页面只用于调试、审计和排障，不能替代生产聊天正文。
- `needs_codex` 流程完成翻译并重新渲染后，再输出最终 `briefing`；不要把中间 JSON、翻译队列或占位文本发给用户。

晚间 `needs_deep_analysis=true` 时，Codex 可按主题拆分研究任务；分析结果使用 `render_deep_analysis.py` 的标准 Markdown 规范。

## 参考

统一读取：`../../../docs/INDEX.md`、`PIPELINE.md`、`OPERATIONS.md`、`TRAPS.md`。
