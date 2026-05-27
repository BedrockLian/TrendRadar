# 投递失败模式识别

> 优化器在分析推送质量时可能发现投递失败。这些模式帮助区分"内容质量问题"和"投递链路问题"。

## 已知静默失败模式

| 模式 | 现象 | 证据 | 修复 |
|------|------|------|------|
| Gateway WebSocket 断连 | pipeline ok 但用户没收到 | gateway 日志 `WebSocket error` + `Reconnected` | 22:00 watchdog 自动补发 |
| WeCom errcode 846609 | cron 投递错误 | cron job `last_delivery_error` 含 `aibot websocket not subscribed` | 22:00 watchdog 自动补发 |
| DeepSeek API 流中断 | 简报半篇丢失 | `RemoteProtocolError: peer closed connection` | pipeline 自动重试，失败则下一轮恢复 |
| cron job 从未运行 | 某时段静默跳过 | cron list 中 `last_run_at` 为 null | 检查 cron scheduler 状态 |

## 检测流程

1. 检查 push_log.json 最新 evening entry 的 status
2. 检查 cron job 的 `last_delivery_error`
3. 检查 `~/.hermes/trendradar/data/delivery_markers/` 是否有对应 run_id 的 marker
4. 若无 marker 且 pipeline status=ok → delivery_watchdog 将自动补发（22:00）
5. 手动补发：`render_markdown.py --push-id evening` → `hermes send --to wecom:bl --file <briefing>`

## 与优化器的关系

优化器报告中的 `推送偏差` 指标可能因投递失败而被误判为"内容供给不足"。
区分方法：若 push_log 中某时段 status=ok 但用户反馈没收到，这是投递问题而非质量/配比问题。
