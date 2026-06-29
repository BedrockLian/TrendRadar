# Delivery Canary Protocol（WeCom chat_id canary 工作流）

**触发**：任何带 `--deliver wecom` 的 cron job 投递前、或 `deliver=wecom` 但没收到消息时。
**耗时**：< 5 分钟（如果你能在企业微信里找到 bot）。
**首次记录**：2026-06-09 实测。

## 核心原理

WeCom AI bot 通过 WebSocket 接收 inbound `aibot_msg_callback` 时，gateway 把 `user_id`（你的 userid）记入内存。**没有 inbound 之前 `WECOM_HOME_CHANNEL` 取不到值**——cron 投递会静默失败。

**前置条件**：
- WeCom bot 凭证已配（WECOM_BOT_ID + WECOM_SECRET）
- gateway 在前台/后台运行（连接了 WeCom）
- 用户能在企业微信里找到 bot

## Canary 7 步（可重复模板）

### Step 1：清空 gateway log 便于看新消息
```bash
> "$HERMES_HOME/logs/gateway.log"  # HERMES_HOME=$LOCALAPPDATA/hermes on Windows
# 或: : > "$HERMES_HOME/logs/gateway.log"（bash 兼容写法）
```
**为什么**：之前可能有几十 MB 旧 log，`grep` 找你的 inbound 容易被淹没。

### Step 2：重启 gateway（拿干净内存状态）
```bash
hermes gateway stop
sleep 2
# 起新 gateway（background）
hermes gateway run --accept-hooks &
sleep 6
# 验证连接
hermes gateway status  # → "Gateway is running"
tail -5 "$HERMES_HOME/logs/gateway.log"  # → 含 "✓ wecom connected"
```

### Step 3：在企业微信给 bot 发任意消息
- 打开企业微信 → 找到 bot（名字应在 Hermes config 里设过，如 "TrendRadar User"）
- 发 `hi` 或 `ping`
- bot 通常会回一段对话（被路由到 main agent，这是正常的——你的"hi"被 main agent 收到了，agent 的回复发回给你）

### Step 4：从 log 拿 chat_id
```bash
tail -50 "$HERMES_HOME/logs/gateway.log" | grep "inbound message"
# 典型输出:
#   2026-06-09 22:14:30 INFO gateway.run: inbound message: platform=wecom user=bl chat=bl msg='你好'
```
**记下 `user=` 后的值**——这就是你的 chat_id（WeCom AI bot 内部用 alias 替代真实 userid）。

### Step 5：测试投递（verify chat_id 可达）
```bash
hermes send -t wecom "Hermes 投递链路测试 — 应该看到这条"
# 期望输出: Sent to wecom home channel (chat_id: bl)
```
**用户侧验证**：在企业微信看到 "Hermes 投递链路测试 — 应该看到这条"。

**没看到？** 检查：
- `tail gateway.log | grep -i error` → wecom 平台报错？
- bot 是否被你屏蔽？
- `WECOM_HOME_CHANNEL` 写入 .env 前 `hermes send` 用了什么路径？（看 `gateway/config.py:1725-1733`）

### Step 6：写 chat_id 到 .env
```bash
echo "WECOM_HOME_CHANNEL=<chat_id>" >> "$HERMES_HOME/.env"
echo "WECOM_HOME_CHANNEL_NAME=<display_name>" >> "$HERMES_HOME/.env"  # 可选
# THREAD_ID 仅在话题模式用，普通 DM 不要设
```
**⚠️ .env 已存在**则**追加**（不要覆盖！里面还有 DEEPSEEK_API_KEY 等其他 key）：
```python
# 用 python 追加，避免覆盖
with open(env_path, 'a', encoding='utf-8') as f:
    f.write('\n# WeCom home channel (added <date>)\n')
    f.write(f'WECOM_HOME_CHANNEL=<chat_id>\n')
```

### Step 7：切 cron job 到 wecom 投递
```bash
# 低风险 job 先试（看门狗/体检）当 canary
hermes cron edit <watchdog_job_id> --deliver wecom
hermes cron list | grep <name>  # → Deliver: wecom
```

**次日观察**：到 cron 触发时间，看企业微信是否真收到消息。

## 故障排查矩阵

| 症状 | 根因 | 修复 |
|------|------|------|
| Step 3 发消息后 log 没 inbound | bot 没连 / bot 被你屏蔽 / 发到了别的 bot | `hermes gateway status` → `tail log` → 看是否还有 "✓ wecom connected" |
| Step 5 `hermes send -t wecom` 报错 | chat_id 没写 env | 确认 `echo $WECOM_HOME_CHANNEL` 有值 |
| 投到了企业微信但用户没收到 | bot 用了 group_policy=disabled 而你发的是 DM | 改 `group_policy: open` 或确保是单聊 |
| Step 5 成功但 Step 7 cron 投递失败 | cron 进程 env 没继承 .env（gateway 已启动） | `hermes gateway restart` 让 gateway 重读 .env |
| chat_id 在 log 里是 `bl` 这种短 alias | 正常——AI bot 内部 alias | 直接用作 WECOM_HOME_CHANNEL 值即可 |

## Cron job 投递目标矩阵（哪些切 wecom、哪些保持 local）

| Job 类型 | deliver=wecom？ | 理由 |
|----------|----------------|------|
| **LLM 日报**（news-secretary 跑）| ⚠️ **local** | prompt 里说 "DO NOT use send_message, slot_direct_push cron 接管"——避免双投 |
| **no_agent 推送看门狗**（delivery_watchdog.py）| ✅ **wecom** | 它就是真投递的执行者，LLM 日报写的 archive 文件由它读+推 |
| **no_agent 自动体检**（trendradar_health_check.py）| ✅ **wecom** | 异常时才推，正常空 stdout=silent |
| **LLM 周报 / 月报**（report-generator）| ✅ **wecom** | prompt 写了"按板块 split_fragments + send_message(target=wecom)"分片投递 |
| **no_agent 每日维护** | 💾 **local** | 默认静默，不应主动推 |

## 反向：从 wecom 切回 local

任何时候回退（验证 cron pipeline本身 正常）：
```bash
hermes cron edit <job_id> --deliver local
# 不要删 WECOM_HOME_CHANNEL——下次切回来还要用
```