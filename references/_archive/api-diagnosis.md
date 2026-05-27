# API 连接问题诊断

> DeepSeek 服务端断流 + WeCom WebSocket 抖动。这两个是**持续存在的环境现象**，非本地故障。
> 排查推送丢失或 API 错误时，先对照本表排除这两类已知噪音。

## 1. DeepSeek openresty 流中断

**现象**: `RemoteProtocolError: peer closed connection without sending complete message body (incomplete chunked read)`

**日志签名**:
```
error_type=RemoteProtocolError
http_status=200
upstream=[server=openresty]
```

**根因**: DeepSeek 的反向代理（openresty/nginx）在 chunked transfer 中主动断连。
数据已发 120-290KB，但未完成就关闭了 TCP 连接。HTTP 状态码为 200（迷惑性）。

**发生模式**:
- 非持续，突发式出现（一天 0-4 次）
- 与请求长度无关 — 短响应（424 bytes）和长响应（289KB）都中招
- 自动重试通常恢复（attempt 2/3），但三次全挂也可能

**对 cron 日报的影响**: 
- 最坏情况：12:02 的 `cron_90a2866775df` 因流中断 → 只返回 `stub response`（0 chars）→ 当日午报丢失
- Hermes 的 `chat_completion_helpers` 检测到 `partial stream delivered before error` 后会返回 stub 防止重复消息

**诊断步骤**:
1. `grep "RemoteProtocolError\|incomplete chunked" ~/.hermes/logs/errors.log` — 查看历史记录
2. `grep "stream_diag\|incomplete chunked" ~/.hermes/logs/agent.log` — 查看 stream drop 详情
3. 如果时点与 cron 运行时间重叠（如 12:02 / 15:14 / 15:41 / 16:26），则有因果关联
4. 检查该 cron 运行的输出是否为空或 stub

**无法本地修复** — 这是 DeepSeek 服务端基础设施问题。如发生频率高，考虑：
- 切换 provider（如 openrouter 中转）
- 为关键 cron 加 result 验证 + 补推机制

## 2. WeCom WebSocket 频繁断连

**现象**: `[Wecom] WebSocket error: WeCom websocket closed` → `[Wecom] Reconnected`

**日志签名**:
```
WARNING gateway.platforms.wecom: [Wecom] WebSocket error: WeCom websocket closed
INFO  gateway.platforms.wecom: [Wecom] Reconnected
```

**根因**: 企业微信 WebSocket 在中国企业网络环境下周期性断连。非异常。

**发生模式**:
- 间隔: 12-20 分钟一次
- 恢复: 2 秒内自动重连成功
- 偶有爆发: 16:31 出现 3 次连续断连（间隔 12s / 14s）
- 24 小时内通常 10-15 次

**影响评估**:
- ✅ 自动重连始终成功，Gateway 不崩溃
- ⚠️ 重连窗口（~2s）内的推送可能丢失
- ✅ cron 的 auto-delivery 有重试机制，通常能恢复
- ❌ 如果断连窗口恰好撞上推送，用户可能收不到但 cron 日志显示"已发送"

**诊断步骤**:
1. `grep "WebSocket error\|Reconnected" ~/.hermes/logs/agent.log` — 统计频率
2. `hermes gateway status` — 确认 gateway 正常运行（active running）
3. 如果用户反馈没收到推送但 cron 日志 ok → 比推送时刻与 WS 断连时间是否重叠

**缓解措施**:
- 这是 WeCom 平台特性，无法消除
- 确保所有推送走 cron final response auto-delivery（有重试），不要手动 send_message
- 对于极端重要的推送，加推送确认看门狗

## 3. 排查流程图

```
用户说"没收到推送"
│
├─ cron 日志有"send_message isn't available"？
│   → cron prompt 没用 auto-delivery，改回 final response
│
├─ cron 日志显示"5/5 sent"？
│   → 比对推送时刻与 WeCom WS 断连时刻
│   │
│   ├─ 时间重叠 → WS 窗口丢失（trap 2）
│   └─ 不重叠 → Gateway 可能在推送后崩溃（查 trap 13）
│
├─ cron 日志是 stub response（0 chars）？
│   → DeepSeek openresty 断流截断（trap 1）
│   → 补推：直接 render → fragment → final response
│
└─ cron 日志为空或未触发？
    → cron 调度问题 / Gateway 挂了
