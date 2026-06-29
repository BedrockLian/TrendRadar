---
name: self-healing
slug: self-healing
version: 3.10.0
description: 自动体检 TrendRadar 各组件：DB/配置/API/Gateway/记忆。修复常见故障。
author: Hermes Agent
metadata:
  hermes:
    tags: [trendradar, health, self-healing, devops]
    cron: 0 15 * * *
---

## 运行
Cron 每日 15:00 跑 `trendradar_health_check.py` (no_agent=true)。有异常推送 WeCom，健康静默。

## 检查项（14项 + 4 个子检查）

详见 `../../references/ARCHITECTURE.md`。

核心检查：DB (WAL + Storage 统一接入) → 脚本 (21个) → 配置 → Cron → Gateway → API → 数据时效 → 盲点审计 → 拦截器 → 全链路 → 记忆 → 进程。

## 6 个 cron job ID

| ID | 名称 | 类型 |
|----|------|------|
| `90a2866775df` | 日报推送 | LLM |
| `cab79825520e` | 推送看门狗（含空投补发） | no_agent |
| `68db70cd8556` | 每日维护 | no_agent |
| `c987a2883174` | 自动体检 | no_agent |
| `c20e2c82deda` | 周报推送 | LLM |
| `0b14c67429ba` | 月度报告 | LLM |

> Job ID 可能因重建变更。`check_cron()` 使用名称子串匹配（`CRON_JOB_NAMES`），不依赖硬编码 ID。

## 健康检查脚本陷阱

详见 `references/health-check-pitfalls.md`。

### 嵌套包结构下 `TR.parent` / `TRENDRADAR_HOME.parent` 不能用作 sys.path（2026-06-02）

仓库采用嵌套包结构：包 `trendradar/` 在内层 `~/.hermes/trendradar/trendradar/`，外层 `~/.hermes/trendradar/` 没有 `__init__.py`。所以 `sys.path`/`PYTHONPATH` 必须用 `TR`自身（= `TRENDRADAR_HOME`），**不是** `TR.parent`（= `~/.hermes/`，其下 `trendradar/`目录不是包）。详见 pitfalls.md #20。

> **⚠️ 这是设计意图，不要尝试合并（2026-06-10教训）**：双层结构是 commit `5c21d19`显式决策（外层真目录 = cron Workdir + GitHub Web UI；内层 = Python 包路径），由 `scripts_sync.sh`保持双向同步。看到"外层+内层两份 `config/`/`scripts/`"觉得是 bug 就想合并 → 会破坏 cron workdir 或 Python import链。**重构前必读 git log** —— `git log --oneline --grep=fix`找最近的修复 commit 通常有设计意图说明。任何不可逆操作（`mv .git`、`rm -rf`）前**必** bundle备份：`git bundle create $HOME/repo-<date>.bundle --all`。

### cron 副本 `~/.hermes/scripts/*.py` 与 git HEAD 长期脱钩（2026-05-30 现在 → 2026-06-09 已修）

`~/.hermes/scripts/` 是 Hermes scheduler 跑 no_agent cron 的 `scripts_dir`（`scheduler.py:854 / :984` 强制约束），与 git 仓库 `~/.hermes/trendradar/hermes-scripts/` 是两份独立副本。2026-06-09 实战发现：`scripts_sync.sh` 只同步 `config/` + `scripts/`（仓库内 `TR/config/` 与 `TR/trendradar/config/` 之间的双向），**完全不动** `HERMES_HOME/scripts/`（即 `~/.hermes/scripts/`）。这是一个盲点。

**2026-06-09 之前**：5/30 之后所有 `health_check.py` 修复（包括脚本里的 `PYTHON_GIL=0` 注入修复、`push_slot_detect NO_SLOT` 修复）都改在 `hermes-scripts/` 但 `cp` 到 `~/.hermes/scripts/` 这一步**被人脑遗忘了**——所以 cron 跑出来的脚本一直是 5/30 旧版。

**正确维护流程**（2026-06-09 修正）：
1. 改 `TR/hermes-scripts/*.py`
2. **必须**立即 `cp $TR/hermes-scripts/*.py $HERMES_HOME/scripts/`
3. `md5sum` 比对两份（应该一致）
4. **建议**把 `cp + md5sum -c` 写进 `scripts_sync.sh`，避免再忘

诊断：`hermes cron run <id>` 触发一个 no_agent job → 看 `~/.hermes/cron/output/<job_id>/<timestamp>.md` 里 stdout 是不是新行为。如果还是老行为，99% 是 `~/.hermes/scripts/` 没同步。详见 pitfalls.md #21。

### Python 文件被注入行号前缀（2026-06-09 新坑）

症状：`.py` 文件每行变成 `1|from trendradar.scripts.common import CST` 这种 `数字|内容` 格式，Python 直接 `SyntaxError: invalid syntax` 在 line 1。`head -5 file.py` 看起来正常（误判为 head 工具加了行号），但 `od -c file.py` 或 import 一下就崩。

**确认方法**：用 `od -c <file> | head -10` 看前几行字节——如果有 `1   |   f   r   o   m` 这种 `数字|空格|内容` 的字节序列，就是文件本体被污染了，**不是工具加了行号**。

**触发场景**：文件从某些 sed/awk/patch 工具的输出流写入（比如 `nl -ba` 编号后直接覆盖）。2026-06-09 在 `gen_cron_prompt.py` 和 `blog_watcher_bridge.py` 上发现，是过去某次 migration 的遗留。

**修复**（Python 一行）：
```python
import re
pat = re.compile(r'^\d+\|', re.MULTILINE)
with open(p, 'r', encoding='utf-8') as f: txt = f.read()
with open(p, 'w', encoding='utf-8') as f: f.write(pat.sub('', txt))
```
修复前先备份 `*.py.broken`。

### gateway `stop` 在 Windows 上会顺手停掉 Scheduled Task 服务（2026-06-09 新坑）

症状：`hermes gateway stop` 之后 `hermes gateway list` 显示 `✗ default (current) — not running`，但 `Scheduled Task registered: Hermes_Gateway` 还在——Windows Task Scheduler 的 service entry 被停了，下次开机可能不会自动重启（取决于 stop 行为是 drain 还是 kill）。

**预防**：debug 时**避免**用 `hermes gateway stop`，改用 `hermes cron list/status` 读状态、用 `hermes cron run <id>` 触发 job。如果必须 stop+run，记着 stop 后**重新 `hermes gateway install`** 让 Scheduled Task 重新激活。

### health_check.py 中 PYTHON_GIL=0 注入陷阱

`trendradar_health_check.py` 在多个 `subprocess.run()` 前有 `env.setdefault('PYTHON_GIL', '0')`。Python 3.14t 不支持 GIL 禁用，该行会导致子进程 `config_read_gil: not supported by this build` 崩溃。

**修复**：删除所有 `env.setdefault('PYTHON_GIL', '0')` 行。若 cron 环境需要 PYTHON_GIL，它已通过 systemd override 注入——不需要脚本再设默认值。

**受影响子检查**：`check_sanity_interceptor()`、`check_pipeline()`（push_slot_detect + import check）、`check_blind_spot()`。

### push_slot_detect NO_SLOT 正常视为失败陷阱

`push_slot_detect.py` 在非推送时段输出 `NO_SLOT` 并 exit=1。health_check 的判断逻辑 `if r.returncode != 0` 会误报 `push_slot_detect 执行失败`。

**修复**：`if r.returncode != 0 and r.stdout.strip() != 'NO_SLOT'` — 仅在 stdout 不是 `NO_SLOT` 时才报失败。

### CRON_JOB_NAMES 漂移 — 实际 job 名称与检查列表不一致（2026-06-29）

**症状**：health_check 报"job X 未注册"，但 `hermes cron list` 显示同名字不同前缀的 job 已注册。

**真因**：`CRON_JOB_NAMES` 列表里的名称是静态硬编码的。cron job 重建后会变更名称前缀（如 `推送降级看门狗`→`TrendRadar 推送看门狗`、`月度趋势报告`→`TrendRadar 月度报告`），子串匹配失效则退化为 token 匹配，单 token 名也无法命中。

**诊断**：对比 `CRON_JOB_NAMES` 中每个 name 与 `hermes cron list` 的 Name: 行：
```python
# Python 一行验证
import subprocess, re
r = subprocess.run(['hermes', 'cron', 'list'], capture_output=True, text=True)
names = set(re.findall(r'Name:\s+(.+)', r.stdout))
CRON_JOB_NAMES = ['日报推送', '推送看门狗', '每日维护', '自动体检', '周报推送', '月度报告']
for name in CRON_JOB_NAMES:
    found = any(name in jn for jn in names)
    print(f"{'✅' if found else '❌'} {name}")
```

**修复**：更新 `CRON_JOB_NAMES` 列表以匹配实际名称。同时删除已不再存在的 job（如 `slot_direct_push`）。

**预防**：每次 cron job 重建后同步更新 health_check.py 中的列表。

### 看门狗时序竞态 — 推送看门狗与管线同时调度（2026-06-29）

**症状**：archive 存在但 delivery_marker 不存在，用户没收到简报。health_check 不报错（因为 scripts/cron 都正常）。

**真因**：`delivery_watchdog`（no_agent, `0 9,12,21`）和 LLM 日报推送（LLM, `0 9,12,21`）共享同一调度 `0 9,12,21 * * *`。当 gateway 同时触发两者时：
1. 看门狗立即跑（~12:03:28）→ 查 archive → 管线还没生成文件 → 空 → silent
2. 管线慢几步（~12:03:51）→ 生成 archive → 但看门狗已完成 → **档案从未投递**

**2026-06-29 实战验证**：12:00 slot，看门狗 12:03:28 跑（空输出），管线 12:03:51 才生成 `noon.md`。午报从未投递，手动 `fragment_push + hermes send` 补投。

**预防**：
- **改时序**：看门狗延后 10 分钟跑（`0 9,12,21 → 10 9,12,21`），给管线留足时间
- **加冗余**：看门狗内部重试逻辑——第一次空则不写 marker，1 分钟后重读
- **加诊断**：health_check 检查 "archive 存在但 marker 不存在" 的漂移

**手动补投协议**（archive 已有）：
```bash
PY="$HERMES_HOME/hermes-agent/venv/Scripts/python.exe"
PYTHONPATH="$TRENDRADAR_HOME" "$PY" -c "
import json, subprocess
from pathlib import Path
from trendradar.scripts.fragment_push import split_fragments

archive = Path('$TRENDRADAR_HOME/archive/$(date +%Y-%m-%d)/noon.md')
content = archive.read_text(encoding='utf-8')
fragments = split_fragments(content)
for i, frag in enumerate(fragments):
    r = subprocess.run(['hermes','send','--to','wecom:bl'],
        input=frag, capture_output=True, text=True, timeout=30)
    print(f'frag {i+1}: exit={r.returncode}')

# Write marker
from datetime import datetime
import hashlib
marker_data = json.dumps({'status':'ok','fragments':len(fragments),'ts':datetime.now().isoformat()})
h = hashlib.md5(marker_data.encode()).hexdigest()[:8]
Path('$TRENDRADAR_HOME/data/delivery_markers/delivered_$(date +%Y%m%d)_noon_'+h+'.marker').write_text(marker_data)
"
```

## Gateway 不在跑的诊断（2026-06-10 实战，TrendRadar 4-Agent 审计发现）

**症状**：`hermes cron list` 末尾有 `⚠ Gateway is not running — jobs won't fire automatically`，但用户看不到任何 cron 触发失败的明显信号——任务注册了但**默默漏跑**。21:00 的日报推送/推送看门狗/晚间简报全都依赖 gateway 在跑才会触发。

**第一步（必跑）**：用 **两个命令** 自检，单一命令不可信：

```bash
hermes gateway status
# → 两种真实状态：
#   "✓ Scheduled Task registered: Hermes_Gateway" + "✗ No gateway process detected" = 任务在但没在跑
#   "✓ Gateway process running (PID: 19060)" = 正常

hermes cron list
# → 末尾 "⚠ Gateway is not running" 是 Hermes CLI 自检，跟 gateway status 一致
# → 但 LAST RUN 字段缺失时 = jobs.json 没记录（注意：cron list 默认不显示 last_run，需 hermes cron info <id>）
```

**第二跑**：看 Windows Task Scheduler 真实记录（cron list 的 "Next run" 来自内存状态，可能误导）：

```powershell
Get-ScheduledTask -TaskName 'Hermes_Gateway' | Get-ScheduledTaskInfo |
  Select-Object LastRunTime, LastTaskResult, NextRunTime, NumberOfMissedRuns
```

**`LastTaskResult` 关键码表**（直接诊断死因）：

| 十六进制 | 十进制 | 含义 | 处理 |
|---------|--------|------|------|
| `0x00000000` | 0 | 干净退出 | 正常 |
| `0xC000013A` | 3221225786 | **STATUS_CONTROL_C_EXIT** | 被 Ctrl+C / 系统 abort 杀（**最常见：用户关 Hermes Desktop 窗口**） |
| `0x800710E0` | -2147023648 | 操作员/系统取消 | 同上 |
| `0x00000102` | 258 | STILL_ACTIVE（孤儿进程残留） | gateway 没真死，看 `Get-Process Hermes` |

**`NextRunTime` 为空 = trigger 配错**：

```powershell
Get-ScheduledTask -TaskName 'Hermes_Gateway' | Select-Object Triggers
# 如果 StartBoundary 是固定过去时间（如 '2026-06-09T22:21:00'）+ Repetition 是 MSFT_TaskRepetitionPattern 但没设 Interval
# → 这是"过去时间点的单次触发 + 尝试重复但失败"组合，Task Scheduler 不再排下次
# → 修复：把 StartBoundary 改成当前时间 + Interval=PT1M（持续运行）
```

**第三跑（关键）**：看 forensic 日志——**`gateway-exit-diag.log` 是死因金矿**：

```bash
ls -lt "$LOCALAPPDATA/hermes/logs/" | head
# 三个关键文件（按重要性）：
#   gateway.log              — 业务日志（连接 wss / cron ticker / 消息收发）
#   gateway-exit-diag.log    — 启动快照 + 崩溃前状态（**死因第一现场**）
#   tui_gateway_crash.log    — TUI/GUI 内 thread 异常 dump
```

**`gateway-exit-diag.log` 关键模式**（每行一条 `tag: gateway.start` 快照）：
```json
{"ts": "2026-06-09T22:21:00", "tag": "gateway.start", "pid": 19060, "python": "3.11.15", "platform": "win32", "argv": ["...hermes", "gateway", "run", "--accept-hooks"]}
{"ts": "2026-06-09T23:09:06", "tag": "gateway.stop", "reason": "UNKNOWN as a planned gateway stop"}
```

如果 `gateway.stop` 出现 → 看它的 `reason` 字段。最近一次实战发现 `reason: "UNKNOWN as a planned gateway stop — exiting cleanly"` → 通常是 Windows Update / 用户登出 / 资源耗尽触发的优雅退出。

**第四跑（最深的根因）**：`_readerthread` UnicodeDecodeError 频发 = **gateway 不稳的真正元凶**：

`tui_gateway_crash.log` 多次出现：
```
thread exception · 2026-06-09 22:23:53 · thread=Thread-653 (_readerthread)
UnicodeDecodeError: 'gbk' codec can't decode byte 0x80 in position 15: illegal multibyte sequence
```

**根因**：hermes-agent 的 `subprocess.Popen` 调 no_agent cron 子进程时**用 Windows 系统 codepage（GBK 中文环境）decode child stdout**。子进程（如 `delivery_watchdog.py`、`trendradar_health_check.py`）输出含中文/UTF-8 字节时 → thread 抛异常死掉 → gateway 关键服务停摆。

**修复**（2 行即可，按推荐顺序）：

1. **环境变量层**（最低风险，`Hermes_Gateway.cmd` 顶部加一行）：

```cmd
@echo off
rem Hermes Agent Gateway - Messaging Platform Integration
cd /d C:\Users\ASUS\AppData\Local\hermes
set "HERMES_HOME=C:\Users\ASUS\AppData\Local\hermes"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"                    ← 加上这一行
set "HERMES_GATEWAY_DETACHED=1"
set "VIRTUAL_ENV=C:\Users\ASUS\AppData\Local\hermes\hermes-agent\venv"
C:\Users\ASUS\AppData\Local\hermes\hermes-agent\venv\Scripts\pythonw.exe -m hermes_cli.main gateway run
exit /b 0
```

2. **subprocess 层**（治本，但需改 hermes-agent 内部代码 `hermes-agent/cron/jobs.py`）：

```python
# 所有 subprocess.Popen / subprocess.run 处加：
subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
# → 'replace' 让 GBK 解不开的字节替换为 U+FFFD，thread 不再死
```

**5 分钟急救（如果 cron 漏了现在就要补）**：

```bash
# 1. 拉起 gateway
hermes gateway start
# → "✓ Gateway started via Scheduled Task 'Hermes_Gateway' (PID: 19060)"

# 2. 立即验证
hermes gateway status  # 应该是 "✓ Gateway process running"

# 3. 手动触发错过的 cron
hermes cron run 27d771f009ae  # 推送看门狗
hermes cron run ef14933d8082  # 日报推送
```

**预防清单**：
- 加 `PYTHONUTF8=1` 到 `Hermes_Gateway.cmd`（5 行改动，立即生效）
- 把 gateway status 自检写进 `health_check.py` 的 14 项之一（目前缺）
- `LastTaskResult 0xC000013A` 出现时**自动** `hermes gateway start` 兜底（self-healing cron 自身）

**完整诊断命令链（一键复制）**：
```bash
# PowerShell 版（含 GBK 解码，MSYS bash 友好）
powershell -NoProfile -Command "Get-Process -Name Hermes | Select Id, ProcessName | ConvertTo-Csv -NoTypeInformation" | iconv -f GBK -t UTF-8
powershell -NoProfile -Command "(Get-ScheduledTask -TaskName 'Hermes_Gateway' | Get-ScheduledTaskInfo | Select LastRunTime, LastTaskResult, NextRunTime | ConvertTo-Csv -NoTypeInformation)" | iconv -f GBK -t UTF-8
hermes gateway status
tail -20 "$LOCALAPPDATA/hermes/logs/gateway.log"
tail -20 "$LOCALAPPDATA/hermes/logs/gateway-exit-diag.log"
tail -20 "$LOCALAPPDATA/hermes/logs/tui_gateway_crash.log"
```

## 投递失败自动补发

详见 `../../references/DELIVERY-WATERMARK.md`。

### `gen_cron_prompt.py` 自身的 PYTHONPATH bug（2026-06-09 Windows 实战）

**症状**：`python scripts/gen_cron_prompt.py` 报 `ModuleNotFoundError: No module named 'trendradar'`。**这个文件本身**把 `PYTHONPATH = str(HERMES_HOME)` 写进生成的 cron prompt 里（line 35），所以即使你手动设 env 把它跑起来，生成的 prompt 也会让 cron job 跑失败。

**根因**：硬编码 `PYTHONPATH = str(HERMES_HOME)`（= `TRENDRADAR_HOME.parent`），违反上文 #20 铁律（必须是 `TRENDRADAR_HOME` 本身）。

**修复**：第35行改为 `PYTHONPATH = str(TRENDRADAR_HOME)`，然后 `bash scripts_sync.sh` 同步外层。

**调用前置**（Windows + 默认 Windows 路径）：
```bash
TRENDRADAR_HOME="C:\\Users\\ASUS\\AppData\\Local\\hermes\\trendradar" \
PYTHONPATH="C:\\Users\\ASUS\\AppData\\Local\\hermes\\trendradar" \
  python "$TR/trendradar/scripts/gen_cron_prompt.py"
```

### cron job 重建顺序 — 先验 `HERMES_HOME/scripts/` 目录存在（2026-06-09 Windows 实战）

**症状**：`hermes cron create --script trendradar_health_check.py --no-agent` 在目录不存在时被 scheduler.py:984 的路径校验拒绝（`Blocked: script path resolves outside the scripts directory`）。

**根因**：scheduler 强制约束 `scripts_dir = _get_hermes_home() / "scripts"` 并 mkdir，但 mkdir **只在 no_agent cron 首次创建时执行**——如果从来没建过 no_agent job，目录就一直缺。

**协议**：先 `mkdir -p "$HERMES_HOME/scripts"` + `cp hermes-scripts/*.py` 同步副本 + md5 比对 → 再 `hermes cron create --script=... --no-agent`。

### WeCom 凭证配置完整流程（2026-06-09 Windows 实战）

5 步：① 用 `python <<'PY' heredoc` 追加 `.env`（避免 shell history）② `config.yaml` 末尾追加 `platforms.wecom` 块 ③ `hermes gateway stop` + 前台 `gateway run --accept-hooks`（或 `gateway install` 需 UAC） ④ `tail logs/gateway.log` 确认 `✓ wecom connected` ⑤ 先 `--deliver local` 跑一次验证通，再切 `--deliver wecom`。

详见 `references/cron-job-creation-recipe.md`（端到端配方，含完整命令 + 验证步骤 + 故障回滚）。

### Hermes 的真实 HERMES_HOME 在 Windows 上不是 `~/.hermes/`（2026-06-09 实战）

**症状**：skill 文档写 `~/.hermes/trendradar/...`，但 `ls ~/.hermes/` 报 `No such file or directory`。

**根因**：Windows 上 Hermes 把 home 解析为 `%LOCALAPPDATA%\hermes`（即 `C:\Users\ASUS\AppData\Local\hermes\`），不是 bash home（`C:\Users\ASUS\`）。skill 文档里的 `~/.hermes/` 是 Linux 简写，跨平台时必须翻译。

**验证**（任何诊断第一步）：
```bash
python -c "from hermes_constants import get_hermes_home; print(get_hermes_home())"
# → C:\Users\ASUS\AppData\Local\hermes
hermes config show | grep Config
# → Config: C:\Users\ASUS\AppData\Local\hermes\config.yaml
```

## 常见故障

详见 `../../references/TRAPS.md`。

### Cron 任务 "Request timed out" — 直连互联网中断

**症状**：多台 LLM cron job 同时报 `RuntimeError: Request timed out`，但 no_agent 脚本类 cron 正常。WeCom 在线。

**诊断**：
```bash
# 1. 验证直连是否正常
curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 8 https://www.google.com
# → 000 / exit 28 / "Network is unreachable" = 直连断

# 2. 验证代理是否正常
curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 8 -x http://127.0.0.1:7890 https://www.google.com
# → 200 = 代理正常

# 3. 检查 DeepSeek API 可达性（直连路由可能例外）
curl -s -o /dev/null -w "HTTP %{http_code}\n" --max-time 8 https://api.deepseek.com/v1/models
# → 401 = 正常（无 token 的预期响应）
```

**修复**：补充 `~/.config/systemd/user/hermes-gateway.service.d/override.conf` 中的代理 env vars，然后重启 gateway。详见 `../system-config/references/proxy-config.md` 的 **Gateway 级别代理** 章节。

**原理**：TrendRadar pipeline 脚本内部已有 `PROXY_URL` 配置（RSS 采集走代理），不受影响。但 Hermes web 工具（`web_search`/`web_extract`）由 cron job 的 LLM agent 调用，需要系统级 `HTTP_PROXY` 环境变量才能走代理。直连断时，web 工具超时 → agent 超时 → cron 报 "Request timed out"。

### ai_translate 401 假阳性 — 真因是 `_resolve_api_key_env` 不查 .env（2026-06-02 实战 + 22:11 真因锁定）

**症状**：`pipeline_orchestrator.py` 跑通，但 ai_translate 步骤 `Translate batch failed: Auth failed: 401 Authentication Fails (governor)`，或 LLM cron 21:00 evening 整体 `Request timed out`（实际子任务 401）。

**真因（commit `d257e3e`）**：`trendradar/scripts/llm_providers.py:485-509` 的 `_resolve_api_key_env(provider_name)` **只查 `os.environ.get(env_name)`，完全不读 .env 文件**。cron LLM agent 跑 ai_translate 时 env 里没 `DEEPSEEK_API_KEY` → 链全部 miss → `api_key=None` → 401。

注意：`settings.get_api_key()`（`trendradar/config/api.py:28`）**有** `TRENDRADAR_HOME/.env` + `~/.hermes/.env` 双重 fallback 链。**但** `llm_providers._resolve_api_key_env` 是另一条独立路径，不走它。这是双实现分裂 bug：ai_translate 调 `get_api_key()` 自己拿 key（成功），但**实际传 key 给 provider** 时走 `create_provider('openai_chat')` → `_resolve_api_key_env(name)` → 只查 env → 拿到 None。

**诊断 3 步**（5 分钟定位）：
```bash
# Step 1: 验 env 里 key
python3 -c "import os; k=os.environ.get('DEEPSEEK_API_KEY',''); print(f'prefix={k[:8]!r} len={len(k)}')"
# 期望 prefix='sk-xxx' len=35；len=0 → cron env 没注入（最常见）

# Step 2: 真打 API（绕过所有内部逻辑，验证 key 本身有效）
python3 -c "
import urllib.request, json
key = open('/home/asus/.hermes/.env').read().split('DEEPSEEK_API_KEY='***')[0].strip().strip(chr(34))
req = urllib.request.Request('https://api.deepseek.com/v1/chat/completions',
  data=json.dumps({'model':'deepseek-v4-flash','messages':[{'role':'user','content':'hi'}],'max_tokens':5}).encode(),
  headers={'Authorization':f'Bearer {key}','Content-Type':'application/json'})
print('HTTP', urllib.request.urlopen(req, timeout=15).status)"
# 期望 200；key 本身有效，问题在内部传参

# Step 3: 验证 create_provider 拿不到 key
python3.14t -c "
import sys; sys.path.insert(0, '/home/asus/.hermes/trendradar')
from trendradar.scripts.llm_providers import create_provider
p = create_provider('openai_chat', model='deepseek-v4-flash')
print(f'api_key={p.api_key}')"  # None = bug 复现
```

**修复**（单点，3 行代码 + 1 个 import）：
```python
# trendradar/scripts/llm_providers.py _resolve_api_key_env() 末尾
for env_name in env_chains.get(canonical, []):
    val = os.environ.get(env_name)
    if val:
        return val
# 链全部 miss 后 fallback 到 settings.get_api_key()（支持 .env 文件）
try:
    from trendradar.scripts.settings import get_api_key as _gk
    fallback = _gk()
    if fallback:
        return fallback
except Exception:
    pass
return None
```

**预防清单**：
- 任何 `provider = create_provider(...)` 之后**必须** `assert provider.api_key, "API key not resolved"`（fail-fast）
- `settings.get_api_key()` 和 `llm_providers._resolve_api_key_env` 双实现要长期合并为单一来源（待实施）

**补充 — 之前误归因**：2026-06-02 早期 session 以为是 `.env` 占位符问题（`DEEPSEEK_API_KEY=*** 模板），那是**症状**不是**根因**。真因是 `_resolve_api_key_env` 完全不查 .env，无论 .env 是占位符还是真 key 都 401。详见 `../system-config/SKILL.md` "API Key 加载陷阱"章节。

### marker 时序错位 + archive 双投递路径（2026-06-02 21:00 evening 实战）

**症状**：用户说"晚报没投递成功"，但 `delivered_2026-06-02_evening.marker` 存在且 mtime 18:44，`status=ok fragments=6/6`。21:00 cron 看似失败，21:16 slot_direct_push 看似 SKIP 已投——但 15 个事件 6 个 `[翻译失败]`，深度分析完全没跑。

**真因 — 三个独立 cron 串行产生 marker/archive 时序错位**：

| 时间 | 事件 | 写文件 |
|------|------|--------|
| **18:44** | 某次 evening 简报投递 | `delivered_evening.marker` (status=ok 6/6) |
| **21:00** | LLM cron 重跑 evening pipeline | 新 `archive/2026-06-02/evening.md` (15 条, 6 个 [翻译失败]) |
| **21:05** | slot_direct_push 跑 | 检测到 marker → SKIP 跳过 |
| **21:15** | LLM cron 整体 `Request timed out` | — |
| **21:16** | slot_direct_push 跑 | 再次 SKIP 跳过 |

**完整 21:00 失败链路**（不是 ai_translate 失败）：

1. 21:00:24 cron 启动，DeepSeek API call 9 次成功（push_prepare + import 探索）
2. 21:09:25 之后 DeepSeek 持续 60s timeout（API 自身问题，与 ai_translate 无关）
3. 21:15:47 3 轮重试全失败 → `RuntimeError: Request timed out`
4. **archive 15 个 [翻译失败] 标记是更早某次 ai_translate 失败留下的**（21:00 pipeline 根本没进 ai_translate 步骤）

**archive 双投递路径**（这是关键设计缺陷）：

| 文件 | 投递路径 | 触发 | 状态 |
|------|---------|------|------|
| `archive/.../evening.md` | `slot_direct_push.py --slot evening` | no_agent cron `fb4e21d7af94` (5 9,12,21) | 自动 |
| `archive/.../evening.deep.md` | **必须手动** `hermes send --file <path>` | 无 | **手动** |

**slot_direct_push 不投递 deep analysis**——它只看 `archive/.../evening.md`。深度分析是 LLM cron prompt (`gen_cron_prompt.py:138-145`) 写明的步骤：
```
## Deep Analysis (evening only)
Only when push_id=evening and needs_deep_analysis=true:
1. Launch 3 Pro delegate_task sub-agents in parallel (trends/cross-domain/risks)
2. Pipe each result through render_deep_analysis.py
3. Output each formatted analysis as separate final response
```

**render_deep_analysis.py 不写 archive**——只输出 stdout。所以 LLM agent 拼装 `evening.deep.md` 是它自己的责任。

**补投 evening + deep 协议**（2026-06-02 实战固化）：

```bash
# 1) 修复翻译（先清 [翻译失败] 字段，再跑 ai_translate）
#    用 self-healing 提供的脚本：
python3.14t ~/.hermes/skills/trendradar/self-healing/scripts/clean_failed_translations.py --push-id evening
#    或手动：清掉 title_cn 前缀为 [翻译失败] 的字段、summary_cn 前缀为 [外媒] 的字段；
#    中文项 title_cn 空时从 title 补、summary 截 100 字。
#    关键：如果只清 [翻译失败] 文本，ai_translate 不会重跑（它把 [翻译失败] 视为"已有"），
#    必须 `del item['title_cn']` 整个删掉字段。

# 2) 重跑 ai_translate（需要 llm_providers.py 已 patch #d257e3e）
cd /home/asus/.hermes/trendradar
python3.14t -m trendradar.scripts.ai_translate --push-id evening

# 3) 重生成简报 archive
python3.14t -m trendradar.scripts.render_markdown --push-id evening

# 4) 跑 3 个 Pro deep analysis（用 delegate_task + deepseek-v4-pro 并行）
# 输出 3 个 markdown → render_deep_analysis.py → 拼装 evening.deep.md

# 5) 删旧 marker
rm -f /home/asus/.hermes/trendradar/data/delivery_markers/delivered_$(date +%Y-%m-%d)_evening.marker

# 6) 投递简报（用 fragment_push + hermes send，不依赖 slot_direct_push）
PYTHONPATH="$TRENDRADAR_HOME" python3.14t -c "
import json, subprocess
from pathlib import Path
from trendradar.scripts.fragment_push import split_fragments
content = Path('$TRENDRADAR_HOME/archive/$(date +%Y-%m-%d)/evening.md').read_text(encoding='utf-8')
for i, frag in enumerate(split_fragments(content)):
    subprocess.run(['hermes','send','--to','wecom:bl'], input=frag, capture_output=True, timeout=30)
    print(f'frag {i+1} delivered')
"

# 7) 投递深度分析（手动，hermes send 一片直达）
hermes send -t wecom:bl --file /home/asus/.hermes/trendradar/archive/$(date +%Y-%m-%d)/evening.deep.md

# 8) 验证
python3.14t /home/asus/.hermes/scripts/trendradar_health_check.py
```

**检测当前是否有时序错位**：
```bash
# marker 时间 vs archive 时间 倒挂
marker=/home/asus/.hermes/trendradar/data/delivery_markers/delivered_$(date +%Y-%m-%d)_evening.marker
arch=/home/asus/.hermes/trendradar/archive/$(date +%Y-%m-%d)/evening.md
[ -f "$marker" ] && [ -f "$arch" ] && \
  [ "$(stat -c %Y "$marker")" -lt "$(stat -c %Y "$arch")" ] && \
  echo "DRIFT: marker is older than archive — 补投"
```

### ai_translate 0 任务 — 改了错 data 目录

**症状**：手动改 `trendradar/data/curated_*.json` 后跑 `ai_translate.py`，报 `No items need processing for push-id 'evening'`，但明明清空了 `summary_cn`。

**根因**：仓库有两份 `data/` 目录（`~/.hermes/trendradar/data/` 外层 vs `~/.hermes/trendradar/trendradar/data/` 内层）。`ai_translate` 读外层，git 跟踪内层 —— 改错地方，0 任务。

**诊断**：
```bash
python3 -c "from trendradar.scripts.file_utils import get_data_dir; print(get_data_dir())"
# → /home/asus/.hermes/trendradar/data/   ← 改这里

# 校验改对地方
md5sum ~/.hermes/trendradar/data/curated_evening_20260601.json \
       ~/.hermes/trendradar/trendradar/data/curated_evening_20260601.json
# → md5 不一致时 = 改错
```

详见 `../system-config/SKILL.md` "双 data 目录陷阱"章节。

## 模板与脚本

- `templates/trendradar_health_check.py` — v3.1（2026-06-29），7 个核心 check，纯 stdlib。相比 v3.0 新增：`check_gateway()` Windows 支持（`hermes gateway status`）、`CRON_JOB_NAMES` 修正。
- `scripts/clean_failed_translations.py` — 补投前清理 curated JSON 的 [翻译失败]/[外媒] 标记 + 补全中文空 title_cn，让 ai_translate 能重跑。2026-06-02 22:11 evening 补投时使用，清 6 字段后 6/6 翻译成功

### health_check v3.0 设计决策（2026-06-02 重建）

**v2.x → v3.0 重大变化**：
- v2.x: `from trendradar.scripts.X import Y` 大量 import → cron env PYTHONPATH 错就崩
- v3.0: **零 trendradar.* import**，所有功能 stdlib 实现
  - DB 检查：`sqlite3.connect('~/.hermes/trendradar/data/fingerprints.db')`
  - 脚本检查：`Path.exists()`
  - Cron 检查：`subprocess.run(['hermes', 'cron', 'list'], capture_output=True, text=True)`
  - Gateway：`subprocess.run(['systemctl', '--user', 'is-active', 'hermes-gateway'])`
  - API：`urllib.request.urlopen('https://api.deepseek.com/v1/models', timeout=8)`
  - 记忆：直接读 `~/.hermes/memories/MEMORY.md` 文件 size

**设计原因**（2026-06-02 教训）：
- cron env 没 `PYTHONPATH=~/.hermes/trendradar` 注入时，v2.x 的 health_check 自身都跑不起来（import 失败）→ **自己修不了自己** 的悖论
- v3.0 砍掉所有外部包依赖，**确保 health_check 永远能跑**——健康检查器必须自己能跑

**维护铁律**：
- 新增 check **优先**用 stdlib 实现
- 不得添加 `from trendradar.* import` 行
- 若必须用 trendradar 内部函数（如 `check_specific_bug`），改为 `subprocess.run([sys.executable, '-m', 'trendradar.scripts.X'])` 调子进程（子进程失败不影响 health_check 自身）

## 烟雾测试

每日维护 (`68db70cd8556`) 内含 `pytest tests/` 运行。测试失败会推送到 WeCom。

手动运行:
```bash
cd ~/TrendRadar/trendradar && python -m pytest tests/ -v --tb=short
```

测试维护 + 失败模式速查：`../../references/MAINTENANCE.md`（含 **9 种** 常见失败模式及修复方法，包括 import 死锁零输出超时 #8）。

## 翻译管线专项诊断

详见 `../news-secretary/SKILL.md` 翻译管线章节及 `../../references/TRAPS.md`。

## 参考文档

| 文件 | 内容 |
|------|------|
| `../../references/TRAPS.md` | 陷阱全集 + 维护陷阱 |
| `../../references/ARCHITECTURE.md` | 体检设计：检查项表 + cron ID 表 |
| `../../references/PIPELINE.md` | DeepSeek 断流 & WeCom WS 抖动 |
| `../../references/MAINTENANCE.md` | 烟雾测试维护：常见失败模式 + 修复方法 + Skill 审计 |
| `../../references/SETUP.md` | 缓存清理规程 |
| `references/foreign-china-expansion.md` | foreign_china 域扩展：新增源/关键词/验证方法 |
| `references/health-check-pitfalls.md` | 体检陷阱全集（**#30 看门狗时序竞态**、**#29 CRON_JOB_NAMES 漂移**、#28 WeCom投递真实通路、#27 Windows HERMES_HOME ≠ ~/.hermes、#26 WeCom凭证配置、#25 cron重建顺序、#24 gen_cron_prompt.py自身 bug、#23 git blob 行号污染、#21 cron 副本脱钩、#20 PYTHONPATH 陷阱、#18 PYTHON_GIL=0 crash、#14 httpbin 走代理超时 等 30 条实战教训） |
| `references/2026-06-29-session.md` | 2026-06-29 实战：Windows check_gateway 修复、CRON_JOB_NAMES 漂移、看门狗时序竞态 |

## 2026-06-09 同 session 新增（修复 4 个 Windows bug）

### delivery_watchdog.py Windows 兼容性 4 个 bug + 1 个 Windows-only crash

`hermes-scripts/delivery_watchdog.py` 在 Windows 上跑会 crash（不是 silent 失败，是直接 traceback 让 cron 报 exit≠0）。**所有 no_agent cron 调度都依赖这脚本能跑**（推送看门狗 / 每日维护 / 自动体检 都会受影响）。

| Bug | 症状 | 修复 |
|-----|------|-----|
| `HERMES_HOME = os.path.expanduser("~/.hermes")` | 解析为 `C:\<user>\.hermes\`（不存在），所有路径校验过不了 | `_resolve_hermes_home()` helper：env > `hermes_constants.get_hermes_home()` API > Linux fallback |
| `TRENDRADAR_HOME` 默认 `Path.home() / '.hermes' / 'trendradar'` | 同上错位 | `_resolve_trendradar_home()` helper：`HERMES_HOME / 'trendradar'` |
| `PYTHON` 默认 `/usr/local/bin/python3.14t` | Windows 不存在 | 自动探测 venv `Scripts/python.exe` (Win) / `bin/python` (Linux) |
| `check_socket()` 只查 `/tmp/*.sock` | 报 "WeCom IPC socket 不可达" | 加 Windows TCP probe `127.0.0.1:{8765,8000,8888,7777}/health` |
| env 值含 `Path` 对象 | Windows CreateProcess `TypeError: environment can only contain strings` | 显式 `str()` 转换 |

### venv pip 坏掉时用 uv 装包

**症状**：`python -m pip install feedparser zstandard` 报 `No module named pip.__main__; 'pip' is a package and cannot be directly executed`（命名空间冲突）。

**修复**：
```bash
uv pip install --python "$HERMES_HOME/hermes-agent/venv/Scripts/python.exe" feedparser zstandard
```

### 看门狗 marker 命名 bug：`_write_marker` 不写 `delivered_` 前缀 → 重复推送

**修复**：
```python
# delivery_watchdog.py:_write_marker
run_id = f'{today.replace("-", "")}_{push_id}'  # YYYYMMDD_<slot>
marker_path = MARKER_DIR / f'delivered_{run_id}.marker'  # 与 is_delivered 一致
```

**铁律**：任何补投脚本写 marker 必须用 `delivered_<YYYYMMDD>_<slot>.marker` 命名。

### 看门狗与 LLM 管线竞态 — no_agent 跑在 archive 生成前（#29）

**症状**：`delivery_watchdog` 在 12:03 跑完，管线 12:03:51 才生成 archive → 简报从未投递。

**修复**：看门狗调度推迟 5 分钟：`hermes cron update 27d771f009ae --schedule "5 9,12,21 * * *"`。

详见 `references/health-check-pitfalls.md` #29。

### `HERMES_CRON_SESSION` 环境变量残留导致 `hermes send` 静默跳过（#30）

**症状**：`hermes cron run` 后，shell 环境留下 `HERMES_CRON_SESSION=1` → 此后 `hermes send` 全部静默跳过，无内容实际投递。

**修复**：`unset HERMES_CRON_SESSION HERMES_CRON_AUTO_DELIVER_PLATFORM HERMES_CRON_AUTO_DELIVER_CHAT_ID HERMES_QUIET`

详见 `references/health-check-pitfalls.md` #30。

### `hermes send -t wecom:bl --file<archive>` 是补发的真实通路（不是 IPC socket）

推送走 `hermes send` 调 Hermes CLI → gateway HTTP/WebSocket。**`/tmp/*.sock` 只是健康探针**。

**手动补推协议**（archive 已有但 marker 没写）：
```bash
PY="$HERMES_HOME/hermes-agent/venv/Scripts/python.exe"
PYTHONPATH="$TRENDRADAR_HOME" "$PY" -c "
from trendradar.scripts.fragment_push import split_fragments
import subprocess, json
from pathlib import Path
from datetime import datetime
import hashlib

content = Path(r'$TRENDRADAR_HOME/archive/$(date +%Y-%m-%d)/noon.md').read_text(encoding='utf-8')
for i, frag in enumerate(split_fragments(content)):
    r = subprocess.run(['hermes','send','--to','wecom:bl'], input=frag, capture_output=True, text=True, timeout=30)
    print(f'frag {i+1}: exit={r.returncode}')

# Write marker
marker_data = json.dumps({'status':'ok','fragments':len(fragments),'ts':datetime.now().isoformat()})
h = hashlib.md5(marker_data.encode()).hexdigest()[:8]
Path('$TRENDRADAR_HOME/data/delivery_markers/delivered_$(date +%Y%m%d)_noon_'+h+'.marker').write_text(marker_data)
"
```
