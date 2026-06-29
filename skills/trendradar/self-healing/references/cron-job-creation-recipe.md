# Cron Job 端到端创建配方（TrendRadar, 2026-06-09 实战）

> 适用场景：从零部署 TrendRadar 6 个 cron job，或重建丢失的 jobs。
> 路径以 Windows + Hermes 默认 home（`%LOCALAPPDATA%\hermes`）为基准；Linux 把 `$LOCALAPPDATA/hermes` 替换为 `~/.hermes` 即可。

## 0. 验证 HERMES_HOME 真实值（**第一步必须做**）

```bash
# 方法 1：直接调 hermes 自己的函数（最准）
python -c "from hermes_constants import get_hermes_home; print(get_hermes_home())"
# 期望：Windows → C:\Users\<user>\AppData\Local\hermes
#       Linux   → /home/<user>/.hermes

# 方法 2：CLI
hermes config show | grep -E "Config:|Install:"
# 期望两个路径都在 HERMES_HOME 下
```

**如果 HERMES_HOME 是 `~/.hermes/`**（Linux）→ 后续命令照抄。
**如果 HERMES_HOME 是 `%LOCALAPPDATA%\hermes\`**（Windows）→ 所有 `~/.hermes/` 替换为 `$LOCALAPPDATA/hermes/`（bash）或 `C:\Users\<user>\AppData\Local\hermes\`（PowerShell / cmd）。

## 1. 解 TrendRadar 关键变量

```bash
# 用真实 HERMES_HOME 解析 TRENDRADAR_HOME
HERMES_HOME=$(python -c "from hermes_constants import get_hermes_home; print(get_hermes_home())")
TR="$HERMES_HOME/trendradar"
TR_PKG="$TR/trendradar"  # Python 包所在
echo "HERMES_HOME=$HERMES_HOME"
echo "TRENDRADAR_HOME=$TR"
echo "TR_pkg=$TR_PKG"
```

## 2. 修前置坑（必做）

### 2.1 修 `gen_cron_prompt.py` 自身 PYTHONPATH bug（见 SKILL #24）

```python
# $TR_PKG/scripts/gen_cron_prompt.py line 35
# 错：
PYTHONPATH = str(HERMES_HOME)
# 对：
PYTHONPATH = str(TRENDRADAR_HOME)
```

### 2.2 剥 git blob 行号污染（如有，见 SKILL #23）

```bash
for f in "$TR_PKG/scripts/"*.py; do
  if head -c 30 "$f" | od -c | head -1 | grep -q "1   |"; then
    echo "CORRUPT: $f"
    cp "$f" "$f.broken"
    sed -E 's/^[0-9]+\|//' "$f.broken" > "$f"
  fi
done
```

### 2.3 同步 scripts 内外两份

```bash
cd "$TR" && bash scripts_sync.sh    # inner → outer
```

## 3. 预创建 scheduler 的 `scripts_dir`

```bash
mkdir -p "$HERMES_HOME/scripts"
cp -v "$TR/hermes-scripts/"*.py "$HERMES_HOME/scripts/"
md5sum "$TR/hermes-scripts/"*.py "$HERMES_HOME/scripts/"*.py
# 期望每行 md5 出现 2 次（外层 = 内层）
```

## 4. 配置 WeCom（推送目标）

### 4.1 写凭证到 `.env`（追加不覆盖）

```python
import os
env_path = os.environ['LOCALAPPDATA'] + r'\hermes\.env'
bot = "<WECOM_BOT_ID>"
sec = "<WECOM_SECRET>"
if 'WECOM_BOT_ID=' not in open(env_path, encoding='utf-8').read():
    with open(env_path, 'a', encoding='utf-8') as f:
        f.write(f'\n# WeCom (added {__import__("datetime").date.today()})\n')
        f.write(f'WECOM_BOT_ID={bot}\nWECOM_SECRET=***   ```

### 4.2 `config.yaml` 末尾追加 wecom 平台块

```yaml
platforms:
  wecom:
    enabled: true
    extra:
      bot_id: "<WECOM_BOT_ID>"
      secret: "<WECOM_SECRET>"
      websocket_url: "wss://openws.work.weixin.qq.com"
      dm_policy: "open"
```

### 4.3 重启 gateway + 验证连接

```bash
hermes gateway stop 2>&1 | head -3
# 前台跑（会话内有效）：
hermes gateway run --accept-hooks &
sleep 8
hermes gateway status  # 期望: ✓ Gateway is running
tail -5 "$HERMES_HOME/logs/gateway.log" | grep -i "wecom.*connected"
# 期望: ✓ wecom connected

# 长期自启需 UAC（Windows）：hermes gateway install
# Linux: hermes gateway install（systemd user service）
```

## 5. 生成 cron prompt SSOT（v6.26 news-secretary 用）

```bash
TRENDRADAR_HOME="$TR" \
PYTHONPATH="$TR" \
  python "$TR_PKG/scripts/gen_cron_prompt.py" > "$TR/references/cron-prompt-generated.md"
wc -l "$TR/references/cron-prompt-generated.md"
# 期望：~96 行（含 7 个 pipeline stage 表）
```

## 6. 批量建 6 个 cron job

按 SKILL 列出的 6 个 job，分三批建（避免一次性失败连带）：

### 6.1 先建 3 个 no_agent（最简单，不需 LLM token）

```bash
# 每日维护
hermes cron create "0 3 * * *" "Daily maintenance" \
  --name "TrendRadar 每日维护" \
  --script trendradar_maintenance.py \
  --no-agent --deliver local

# 自动体检（15:00，与 SKILL 一致）
hermes cron create "0 15 * * *" "Daily health check" \
  --name "TrendRadar 自动体检" \
  --script trendradar_health_check.py \
  --no-agent --deliver local

# 推送看门狗（每 10 分钟，空投补发）
hermes cron create "*/10 * * * *" "Push delivery watchdog" \
  --name "TrendRadar 推送看门狗" \
  --script delivery_watchdog.py \
  --no-agent --deliver local
```

### 6.2 再建 1 个日报（先用 `local` 验证通）

```bash
PROMPT=$(cat "$TR/references/cron-prompt-generated.md")

hermes cron create "0 9,12,21 * * *" "$PROMPT" \
  --name "TrendRadar 日报推送" \
  --skill news-secretary \
  --deliver local
```

**手动跑一次**：
```bash
hermes cron list
# 找到日报 job 的 ID
hermes cron run <日报 job ID>
# 检查输出 + archive/YYYY-MM-DD/*.md 是否生成
```

### 6.3 最后切投递目标 + 建周报/月报

```bash
# 把日报切到 wecom
hermes cron edit <日报 job ID> --deliver wecom

# 周报（每周一 09:30）
WEEKLY_PROMPT=$(cat "$TR/references/cron-prompt-generated.md")  # 或手写
hermes cron create "30 9 * * 1" "$WEEKLY_PROMPT" \
  --name "TrendRadar 周报推送" \
  --skill report-generator \
  --deliver wecom

# 月报（每月1日 09:00）
hermes cron create "0 9 1 * *" "<月报 prompt>" \
  --name "TrendRadar 月度报告" \
  --skill report-generator \
  --deliver wecom
```

## 7. 端到端验证

```bash
# 7.1 6 个 job 都注册
hermes cron list | head -20
# 期望：6 行（含名称 + schedule + next run）

# 7.2 scripts_dir 副本与 git HEAD 一致
for f in "$HERMES_HOME/scripts/trendradar_"*.py; do
  bn=$(basename "$f")
  [ "$(md5sum < "$f")" != "$(md5sum < "$TR/hermes-scripts/$bn")" ] && echo "DRIFT: $bn"
done
# 期望：无输出

# 7.3 WeCom 在线
tail -1 "$HERMES_HOME/logs/gateway.log" | grep "wecom connected"
# 期望：上一行匹配

# 7.4 DB 完整
sqlite3 "$TR/data/fingerprints.db" "PRAGMA integrity_check; SELECT count(*) FROM fingerprints;"
# 期望：ok + 数字

# 7.5 一次端到端手动推送
hermes cron run <日报 job ID>
ls "$TR/archive/$(date +%Y-%m-%d)/"*.md 2>&1
# 期望：morning.md / noon.md / evening.md 至少一份
```

## 8. 故障回滚

| 现象 | 修复 |
|------|------|
| `--deliver wecom` 投递失败 | `hermes cron edit <id> --deliver local`，先看 log 找原因 |
| scheduler 报 `Blocked: script path` | 漏了第 3 步 → `mkdir -p $HERMES_HOME/scripts && cp ...` |
| `gen_cron_prompt` ModuleNotFoundError | 漏了 2.1（PYTHONPATH 修）或 `PYTHONPATH` 没设 |
| Gateway 不稳 → cron 不触发 | `hermes gateway stop && hermes gateway run` 重启 |
| 推送内容超 WeCom 4KB 限制 | 已被 SKILL `news-secretary` 自动分片处理（slot_direct_push） |

## 9. 维护铁律

- 改 `hermes-scripts/` 任何文件后**立即** `cp` 到 `HERMES_HOME/scripts/` + md5 比对（见 SKILL #21）
- 修 cron prompt SSOT 时只用 `gen_cron_prompt.py` 自动生成，**不要手写**两份漂移
- 改任何 `trendradar/` 仓库脚本后跑 `bash scripts_sync.sh` 同步内→外
- WeCom 凭证轮换时同步改 `.env` + `config.yaml` + 重启 gateway

---

**实战参考**：本配方基于 2026-06-09 首次从零搭建 TrendRadar cron 调度系统的实际执行序列，每步命令都验证过可跑通。Windows + Hermes 默认 home 是 `%LOCALAPPDATA%\hermes`，不是 `~/.hermes/`（见 SKILL #27）。