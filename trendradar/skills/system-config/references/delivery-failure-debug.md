# 投递失败调试手册

> 发现于 2026-05-26 晚间 cron (push_id=evening, status=ok, 6 fragments, 但用户未收到)

## 核心认知

**Pipeline status=ok + fragment_count>0 ≠ 用户收到了简报。** Pipeline 只负责生成内容，不负责交付成功。交付由 Hermes Gateway 的 auto-delivery 机制处理，这个环节是黑盒。

**`hermes send --to wecom:bl` 是 CLI 下最可靠的补推方式。** 在 CLI 会话中直接输出内容只会显示在终端，不会推送到 WeCom。必须用 `hermes send` 显式投递。

## 调试步骤

### 1. 确认 pipeline 确实跑了

```bash
cat ~/.hermes/trendradar/data/push_log.json | python3 -c "import json,sys; j=json.load(sys.stdin); [print(f'{p[\"push_id\"]} @ {p[\"timestamp\"]}: status={p[\"status\"]}, frags={p[\"fragment_count\"]}, items={p[\"total_items\"]}') for p in j]"
```

### 2. 检查 Gateway 状态

```bash
PYTHON_GIL=1 hermes gateway status 2>&1
```

### 3. 检查交付看门狗日志

```bash
cat ~/.hermes/trendradar/data/push_log.json | grep -i "delivery\\|error\\|fail"
```

### 4. 检查 WebSocket 断连记录

```bash
grep "WebSocket\\|Reconnected\\|Gateway" ~/.hermes/logs/agent.log | tail -20
```

### 5. 检查 cron job 的 last_delivery_error

```bash
PYTHON_GIL=1 hermes cron list --json | python3 -c "import json,sys; [print(f'{j[\"name\"]}: {j.get(\"last_delivery_error\",\"none\")}') for j in json.load(sys.stdin)]"
```

### 6. 检查广播目标是否可用

```bash
PYTHON_GIL=1 hermes send --list
```

## 已知静默失败模式

| 模式 | manifest | 修复 |
|------|----------|------|
| Gateway WebSocket 断连 | `[Wecom] WebSocket error` + 紧跟 `Reconnected` | 自动重连成功，丢失概率低。手动补推 |
| Gateway 崩溃 | 推送日志显示 ok 但无 Reconnected | 重启 `hermes gateway restart` → 补推 |
| API 流中断 | DeepSeek `RemoteProtocolError: openresty` | 自动重试兜住大部分。stub response 需补推 |
| sub-agent 沙箱 | 子 Agent 所有 terminal 返回空 | 改用 inline 传参（见 deep-analysis-subagent-sandbox.md） |
| **WeCom WebSocket 未订阅** | `errcode 846609: aibot websocket not subscribed` | Gateway 运行但 WeCom 连接未注册。`hermes gateway restart` → 用 `hermes send --to wecom:bl` 补推 |

## 补推流程

当用户反馈没收到时，**不要只输出到 CLI 终端**，必须通过消息平台投递：

### CLI 会话下（当前场景）

```bash
cd ~/.hermes/trendradar
export PYTHON=/usr/local/bin/python3.14t PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0

# 1. 重新渲染简报
$PYTHON scripts/render_markdown.py --push-id {slot} > /tmp/briefing_{slot}.md

# 2. sanity check
$PYTHON scripts/sanity_check.py --push-id {slot}

# 3. 投递到 WeCom（重要！CLI 输出不会自动投递）
PYTHON_GIL=1 hermes send --to wecom:bl --file /tmp/briefing_{slot}.md
```

### 深度分析补推（晚间）

```bash
PYTHON_GIL=1 hermes send --to wecom:bl --file ~/.hermes/trendradar/reports/risk_analysis_*_evening.md
```

### 发现可用目标

```bash
PYTHON_GIL=1 hermes send --list
# 输出示例:
#   Wecom: wecom:bl (dm)
#   Feishu: feishu:oc_xxx (dm)
```

## 自动防护

`delivery_watchdog.py` 现在已内置 auto-delivery 空投检测：

1. **调度**：每日 10:00 / 14:00 / 22:00 运行（cron job `cab79825520e`）
2. **检测**：对比 `push_log.json` 最新 evening 条目与 `data/delivery_markers/` 目录
3. **补发**：未标记即自动重新渲染 → sanity_check → `hermes send --to wecom:bl` 补投
4. **循环防护**：补发后创建 `delivered_{run_id}.marker`，同一 run_id 只补一次
5. **时效**：仅补发 6 小时内的推送
