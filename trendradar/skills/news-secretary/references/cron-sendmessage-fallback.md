# Cron 投递机制：auto-delivery 协议

## 现状

**`send_message` 在 cron context 不可用。** cron agent 没有 `send_message` 工具。投递走系统机制：agent 的最终 final response 被调度器捕获后自动通过 Gateway 推送到 WeCom（`deliver: wecom`）。

## cron prompt 要求

1. 先用 `render_markdown.py` 渲染简报，捕获 stdout 到 `BRIEFING` 变量
2. 尝试 `fragment_push.py` 分片并用 `send_message` 逐片投递
3. **send_message 不可用时**：直接输出 `BRIEFING`（脚本渲染的完整 Markdown）作为 final response
4. 不得用 LLM 重新生成简报内容（会丢失翻译、格式跑偏）
5. 返回 `[SILENT]` 的条件：无新条目，且简报已通过 send_message 投递完成

## 历史陷阱

2026-05-24: 旧 prompt 第7步说「遍历 fragments 用 send_message 投递」，第8步又说「返回 [SILENT]」。agent 用不了 send_message，又因 [SILENT] 不输出内容，最后自作主张用 LLM 重新生成了内容（丢失全部翻译）。

**修复**：prompt 改为 send_message 不可用时直接输出 BRIEFING，不返回 [SILENT]。
