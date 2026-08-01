# 日报管线

## 阶段

```text
时段识别 → 抓取与精选 → 事件追踪 → AI 翻译 → Markdown 渲染 → 指纹记录
```

`python -m trendradar.pipeline.pipeline_orchestrator --list-steps` 是阶段定义的机器可读入口。

## JSON 结果

成功结果包含：

```json
{
  "protocol_version": 1,
  "status": "ok",
  "push_id": "morning",
  "briefing": "...",
  "stats": {
    "total_elapsed": 12.3,
    "budget": {
      "budget_seconds": 180,
      "elapsed_seconds": 12.3,
      "within_budget": true
    }
  },
  "artifacts": {
    "briefing_path": "...",
    "curated_path": "..."
  }
}
```

`silent` 表示没有新内容，`busy` 表示已有同名任务运行，`error` 表示需要诊断。Codex 只展示 `briefing`，不重新生成或拼接脚本输出。

## 性能策略

- RSS 使用线程池并行，避免人为串行等待。
- 来源配置、关键词和兴趣配置只从统一目录读取。
- 翻译按批次处理，并复用 HTTP 客户端和缓存。
- 每轮通过锁避免重复抓取和重复写入。
- 全链路以单调时钟计时；超过 180 秒会在结果中明确标记并转为错误。

## 输出格式

Markdown 保留标题、条目、摘要、来源链接和统计尾注。渲染脚本的 docstring 是格式契约，修改时同步更新本文件。
