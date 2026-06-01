# 简报分片投递陷阱（2026-06-01 修复）

## 现象

用户收到半篇简报，尾部板块（如游戏/经济板块）被截断。WeCom 日志无错误，pipeline 返回 `status=ok`。

## 根因

Cron prompt 指引 Agent"输出 `briefing` 字段作为 final response（auto-delivery）"。Agent 将整篇 8KB 简报作为一条消息输出 → WeCom 静默截断（4096 字节硬限制），用户只收到前半篇。

Pipeline 的 `fragment_push.py` 实际已正确产出分片（push_log 中 `fragment_count: 6`），但 Agent 从未遍历 `fragments` 数组。

## 排查

1. 确认存档完整：`archive/YYYY-MM-DD/{slot}.md` 是纯 markdown，读它确认内容完整
2. 检查 push_log：`data/push_log.json` 中最近一条的 `fragment_count` 和 `total_items`
3. 检查 cron prompt 步骤 3：是否写的是"输出 `briefing` 字段"而非"遍历 `fragments` 数组"
4. 检查 cron job `enabled_toolsets` 是否包含 `messaging`

## 修复

两个层面的修复：

### gen_cron_prompt.py（生成器）
```python
# 改前：
'- `status: "ok"` → output `briefing` field as final response (auto-delivery)'

# 改后：
'- `status: "ok"` → parse `fragments` array. For each fragment, use
   send_message(target="wecom", message=fragment) to deliver individually.'
```

### Cron job（运行时）
- `enabled_toolsets` 必须包含 `"messaging"` 以便 Agent 调用 `send_message`
- Prompt 步骤 3 重写为遍历 fragments 投递

## 预防

新设 cron job 时：`enabled_toolsets` 必须包含 `messaging`，prompt 必须指引 fragments 遍历而非 briefing 输出。
