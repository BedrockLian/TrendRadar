# TrendRadar Health-Diagnosis Playbook — 2026-06-09 全量复盘

适用：用户说"TrendRadar 不工作"/"推送断了"/"今天没收到日报"——任何"链路全面异常"的场景。

按这个顺序检查，能在 ~10 分钟内定位 ~90% 的问题。

## Step 1 — Gateway 和 cron 调度层（30 秒）

```bash
hermes gateway status          # 应该 ✓ running
hermes cron status             # 应该 ✓ Gateway is running — cron jobs will fire
hermes cron list               # 看 active jobs 数量和名称
```

**预期正常**：`✓ Gateway is running (PID: ...)`, `6 active job(s)`。

**异常信号 → 排查方向**：
- `✗ Gateway is not running` → 用 `hermes gateway run --accept-hooks` 前台起（前台进程跟当前会话同生命周期，会话退出就停。要长期自启需要 `hermes gateway install` + UAC 授权）
- `Gateway is running` 但 cron jobs 全部 silent / 没产物 → 看 Step 2
- `No scheduled jobs` 但 skill 期望6 个 → 看 Step 3

## Step 2 — cron output 目录（30 秒）

```bash
ls -lt ~/.hermes/cron/output/<job_id>/ | head -5
# 看最近 5 次 stdout / status
cat ~/.hermes/cron/output/<job_id>/<最新>.md
```

**预期正常**：LLM job 有 `## Prompt` + `## Response` 段；no_agent job 有 `Status: silent (empty output)` 或具体 stdout。

**异常信号**：
- LLM job 只有 `[SILENT]` final response → pipeline 在 agent 跑之前就 silent 了（多半 `push_slot_detect` 返回 NO_SLOT 或 fetch 失败）
- LLM job final response 是 briefing 内容而不是状态行 → agent 误把简报当 final response 输出，触发 WeCom 4KB 截断
- no_agent job 完全没产物 → scheduler 没跑到（看 Step 3）或脚本 import 失败

## Step 3 — Scheduler 路径与脚本副本（1 分钟）

```bash
# 验证 scheduler 期望的 scripts_dir 是否存在且有脚本
ls -la $HERMES_HOME/scripts/
# 验证 HERMES_HOME 解析正确（Windows 上是 %LOCALAPPDATA%\hermes）
echo $HERMES_HOME    # 或从 hermes --version 的 Project 行确认
md5sum $HERMES_HOME/scripts/delivery_watchdog.py $TR/hermes-scripts/delivery_watchdog.py
```

**关键事实**：
- `HERMES_HOME` 在 Windows = `C:\Users\<user>\AppData\Local\hermes`，**不是** `~/.hermes`（那不存在）
- scheduler 强制 `scripts_dir = $HERMES_HOME/scripts`（`scheduler.py:984`），且做 `path.relative_to()` 安全检查
- 仓库真相源是 `$TR/hermes-scripts/`，**必须手动 cp** 到 `$HERMES_HOME/scripts/`
- `scripts_sync.sh` 只同步仓库**内部** `TR/config/` 与 `TR/trendradar/config/` —— 不碰 `$HERMES_HOME/scripts/`

**修复**：
```bash
mkdir -p $HERMES_HOME/scripts
cp -v $TR/hermes-scripts/*.py $HERMES_HOME/scripts/
md5sum $TR/hermes-scripts/*.py $HERMES_HOME/scripts/*.py   # 验证一致
```

## Step 4 — Pipeline 端到端（5 分钟）

```bash
# 强制跑一次完整 pipeline（绕过 slot_detect 时间窗检查）
export TRENDRADAR_HOME=$TR
export PYTHONPATH=$TR
$PYTHON $TR/trendradar/scripts/pipeline_orchestrator.py --push-id evening 2>&1 | tail -30
```

**观察关键 log**：
- `push_prepare ... 首次fetch — 触发 fetch` → fetch 在跑
- `fetch/blog 失败: No module named 'feedparser'` → 依赖缺失，装：`uv pip install --python $HERMES_HOME/hermes-agent/venv/Scripts/python.exe feedparser zstandard`
- `fetch 完成 0 条` → RSS 源全失败（代理/网络问题），看 `references/proxy-config.md`
- `精选: 头条0 ... 共0条` → fetch 成功但没有新条目（可能 DB fingerprint 把所有新条目都判重了）
- `Empty briefing detected` → `status: silent`，LLM cron 看到会输出 `[SILENT]`
- `JSON status: "ok"` + `fragments: [...]` → pipeline 正常完成，archive 写到 `$TR/archive/YYYY-MM-DD/evening.md`

**修好 pipeline 之后**：手动重跑 LLM job 让它读 archive 触发 deep analysis —— `hermes cron run <日报_job_id>`。**注意**：手动跑 pipeline 不会自动触发 LLM 重跑；如果 LLM 之前已经 SILENT，archive 有了它也不会重读。

## Step 5 — LLM job 配置（1 分钟）

```bash
# 看 jobs.json 里 LLM job 的 enabled_toolsets
python -c "
import json
data = json.load(open(r'$HERMES_HOME/cron/jobs.json'))
for j in data['jobs']:
    if not j.get('no_agent') and not j.get('script'):
        print(j['id'][:8], j['name'], 'toolsets:', j.get('enabled_toolsets'))
"
```

**预期**：`enabled_toolsets = ['default', 'delegation']`（或至少含 `delegation`，如果 prompt 用 `delegate_task`）

**异常 → 修**：
```bash
# 直接改 jobs.json（hermes cron create/edit 都不暴露 --toolset）
python -c "
import json
p = r'$HERMES_HOME/cron/jobs.json'
d = json.load(open(p))
for j in d['jobs']:
    if not j.get('no_agent') and not j.get('script'):
        j['enabled_toolsets'] = ['default', 'delegation']
json.dump(d, open(p, 'w'), ensure_ascii=False, indent=2)
"
hermes gateway restart     # Windows: stop + run --accept-hooks
```

## Step 6 — 推送链路（1 分钟）

```bash
# 看 WeCom 是否还连
tail -5 ~/.hermes/logs/gateway.log | grep -i wecom
# 试发测试消息验证 chat_id 可达
hermes send -t wecom "测试消息 — 应该立即收到"
```

**预期**：`Sent to wecom home channel (chat_id: <你的_userid>)`，几秒后 WeCom 收到。

**如果发不出去**：
- `Channel directory built: 0 target(s)` 且没 inbound → 还没用户给 bot 发过消息；引导用户发任意"hi"触发 inbound 后再看 chat_id
- `WECOM_BOT_ID` / `WECOM_SECRET` 没设 → 检查 `$HERMES_HOME/.env` 和 `$HERMES_HOME/config.yaml` 的 `platforms.wecom` 块

## Step 7 — Archive 和 marker 一致性（30 秒）

```bash
# 今天 archive 应该有内容
ls -lt $TR/archive/$(date +%Y-%m-%d)/*.md
# delivery_markers 里今天应有对应 marker
ls -lt $TR/data/delivery_markers/ | grep "$(date +%Y%m%d)"
```

**异常**：
- archive 有但 marker 没有 → 看门狗没补发（可能 IPC socket check 失败但不影响实际投递，验证 `gateway.log` 看 wecom 发送记录）
- marker 有但 archive 没有 → 看门狗把失败投递误标成 success（2026-06-09 修过的 `_write_marker` bug）

## 完整健康检查命令（10 秒判断）

```bash
# 把这套检查做成一条命令粘到终端
TR=$LOCALAPPDATA/hermes/trendradar
HH=$LOCALAPPDATA/hermes

echo "=== Gateway ==="
hermes gateway status 2>&1 | head -3

echo ""
echo "=== Cron ==="
hermes cron status 2>&1 | grep -E "active jobs|next run"

echo ""
echo "=== WeCom ==="
tail -3 "$HH/logs/gateway.log" | grep -i wecom | head -1

echo ""
echo "=== Scheduler scripts_dir ==="
ls "$HH/scripts/" 2>&1 | wc -l

echo ""
echo "=== DB health ==="
python -c "
import sqlite3
for label, db in [('prod', r'$TR/data/fingerprints.db'), ('git', r'$TR/trendradar/data/fingerprints.db')]:
    try:
        c = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
        cur = c.cursor()
        cur.execute('PRAGMA integrity_check')
        cur.execute('PRAGMA journal_mode')
        cur.execute('SELECT count(*) FROM fingerprints')
        print(f'  {label}: {cur.fetchone()[0]} integrity=ok')
    except Exception as e:
        print(f'  {label}: ERR {e}')
"

echo ""
echo "=== Archive today ==="
ls "$TR/archive/$(date +%Y-%m-%d)/" 2>&1
```

## 已知坑速查（修复于 2026-06-09）

| 症状 | 根因 | 修复 |
|------|------|------|
| `ModuleNotFoundError: No module named 'trendradar'` | `PYTHONPATH=TRENDRADAR_HOME.parent` | 改成 `$TRENDRADAR_HOME` 自身 |
| `No module named 'feedparser'` | TrendRadar 依赖没装 | `uv pip install --python <venv> feedparser zstandard` |
| `TypeError: environment can only contain strings` | subprocess env 传了 Path 对象 | `env[k] = str(v) for k,v in os.environ.items()` |
| `SyntaxError: invalid syntax line 1` | Python 文件被注入 `数字\|` 行号前缀 | Python re.sub `^\d+\|` 修复 |
| LLM 跑 [SILENT] 不补发 | LLM cron 不自动重跑 | 手动 `hermes cron run <id>` |
| deep analysis 一直没生成 | cron prompt Main Flow 没读 `needs_deep_analysis` | 见 `news-secretary/references/deep-analysis-prompt-fix.md` |
| wecom 测试发送 0 chat | 没 inbound 过 | 用户先发"hi"消息触发 inbound |

## 不要做

- **不要 `crontab -l`**——Hermes cron 不走系统 cron，crontab 为空是正常的
- **不要 `hermes send --file` 裸调重投**——不写 delivery_marker，下次 cron 会再投一次
- **不要 `python3.14t --version` 假设**——Windows 安装的是 cpython 3.11，TrendRadar 的 free-threaded 3.14t 是 Linux 推荐
- **不要 `hermes cron create --deliver wecom` 直接切**——先验证 `WECOM_HOME_CHANNEL` chat_id 可达，否则投递 silent 失败