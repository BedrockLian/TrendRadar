# Cron context 下投递机制：auto-delivery 协议

> `send_message` 在 cron context 中**不可用**。所有投递通过 final response auto-delivery 完成。

## 原理

cron job 执行完毕后，系统将 Agent 的 final response 自动投递到配置的 deliver 目标（WeCom）。
Agent 不需要（也不能）在 cron 中使用 `send_message` 工具。

## 正确做法

1. pipeline 产出渲染好的简报（`render_markdown.py` stdout）
2. Agent 将简报原文作为 final response 返回
3. 系统自动投递到 WeCom

```bash
# 编排器模式
RESULT=$($PYTHON scripts/pipeline_orchestrator.py 2>&1)
# 解析 JSON → status=ok 时将 briefing 字段作为 final response
```

## 错误做法

- ❌ 在 cron 中尝试 `send_message(target="wecom")` — 工具不可用
- ❌ 返回 `[SILENT]` 作为 final response — 什么都不投递
- ❌ Agent 用自己话重写简报内容 — 格式跑偏、翻译丢失
- ❌ 只返回 fragments JSON 数组不输出实际内容

## 历史

此前 pipeline 设计为逐片 send_message 投递，但 cron 环境无此工具。
v5.7.0+ 改为 auto-delivery：Agent 输出完整简报，系统负责投递。
