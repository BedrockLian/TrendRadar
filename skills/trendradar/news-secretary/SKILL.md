---
name: news-secretary
slug: news-secretary
version: 6.26.0
description: 聚合多RSS源+博客，推送Markdown简报至企业微信。编排器一键管线 + 晚间flash深度分析。
author: Hermes Agent
metadata:
  hermes:
    tags: [news, trend, RSS, wecom]
    delivery: wecom
    push_schedule: { merged: "0 9,12,21 * * *" }
    companion_skills: [self-healing, report-generator, system-config]
---

## 触发

### 自动（cron）
cron `0 9,12,21 * * *` (早30/午30/晚20, 日上限80)。晚间追加 3×flash 深度分析（2026-06-02 从 Pro 改 flash）。

### 手动补推（Agent 触发）
用户说 "补推早报/午报/晚报"、"今天没收到日报"、"重新推一下" → 立即走 `references/manual-retro-push.md` 工作流。**不要等 cron 自动恢复**——cron 链路随时可断。

**⚠️ 关键诊断步骤（2026-06-06 踩坑修正）**：**先 `hermes cron list` 和 `hermes cron status`**，**不要先 `crontab -l`**。Hermes cron 走的是**内置 gateway 调度器**（systemd 跑），不是系统 cron。`crontab -l` 为空是**正常状态**——gateway 自己调度 7 个 job。看到空 crontab 就误判"cron 没装"是错的，会导致手动重复投递（详见 `references/retropush-double-deliver-2026-06-06.md`）。

触发顺序：① `hermes cron list` + `hermes cron status` 确认 gateway 状态 ② 检查 `last_status` + `delivery_markers/` 找失败原因 ③ 跑 `pipeline_orchestrator --push-id <slot>` ④ 用 `fragment_push + hermes send` 重投（见 `references/manual-retro-push.md` 协议，注意写 marker）——**`slot_direct_push.py` 已不再存在**，不要引用 ⑤ 验证 marker 已写为 `status=ok`。

## v6.26 关键行为（2026-06-09 实测确认）

### Deep Analysis 触发逻辑
- pipeline_orchestrator 在 `push_id=evening` 且 `final_status != "error"` 时返回 `needs_deep_analysis: true`。
- LLM agent **必须**主动 parse 这个字段：当 `true` 时启3 个 `delegate_task` sub-agent（flash + deepseek-v4-flash），每个跑一个主题的深度分析，pipe 过 `render_deep_analysis.py` 格式化，sub-agent 各自用 `hermes send --to wecom:bl --subject "🔍 深度 · <主题>"` 投递。
- **历史 bug**：v6.26 之前的 cron prompt（SSOT 在 `references/cron-prompt-generated.md`）只在 "Deep Analysis (evening only)" 一节简略提了3 步，但**Main Flow 段只说"`status: ok` → 输出3步状态行就结束"**——LLM 看到 `needs_deep_analysis: true` 也不知道要触发。结果：**历史所有 evening archive（2026-05-30 ~ 2026-06-08）都没有 deep analysis 章节**，bug 持续了约10 天。
- **2026-06-09 修复**：重写 SSOT prompt 的 Main Flow 段，明确写 "Check `needs_deep_analysis` field: If true → launch 3 delegate_task sub-agents"；同时强化 Deep Analysis 段为具体的 Step 1/2/3 协议。修复后 cron job `ef14933d8082` 的 prompt 已同步更新。**首次验证窗口是次日晚 21:00**。

### Scheduler 不自动注入环境变量
LLM agent 的 cron prompt **必须在开头显式 export**（SSOT 模板就这么写）：
```bash
TRENDRADAR_HOME=<绝对路径>
HERMES_HOME=<绝对路径>
PYTHON=<venv python.exe 绝对路径>
PYTHONPATH=$TRENDRADAR_HOME   # 注意：是自身，不是 .parent
```
否则 `pipeline_orchestrator.py` import 失败（`ModuleNotFoundError: trendradar`）或报 Windows path 错位。验证：`hermes cron run <job>` 看 cron output 里第一行 `PYTHONPATH env:` 是否正确；scheduler **不会**自动注入这些变量（验证于 2026-06-09）。

### 手动 pipeline 后 LLM cron 不会自动重跑
如果手动 `python pipeline_orchestrator.py --push-id evening` 生成 archive，但 LLM job `ef14933d8082` 在那之前已经跑过 `[SILENT]`，LLM **不会**自动重跑。即使 archive 已经有了，**晚报摘要依然缺失**——必须重跑 LLM cron（`hermes cron run ef14933d8082`），或者等到次日 21:00 cron 自然触发。
**预防**：debug 时先确认 pipeline status 再决定要不要重跑 LLM；避免"手动跑 pipeline 解决眼前，但 LLM 端不知道"的状态。

### marker 命名统一（v6.26 修复）
历史 bug：`_write_marker` 写的是 `{today}_{push_id}.marker`（无 `delivered_` 前缀），而 `is_delivered(run_id) / mark_delivered(run_id)` 期望的是 `delivered_{run_id}.marker`——结果是每次 auto_redeliver 都会判定"未投递"→ 重复投递。2026-06-09 修复在 `delivery_watchdog.py`，所有 marker 现在统一为 `delivered_{YYYYMMDD}_{push_id}.marker`。如果看到 `*.marker` 没有 `delivered_` 前缀，是历史遗留（可以清掉，不影响新流程）。

### ⚠️ 看门狗时序竞态 — 管线生成了档案但从未投递（2026-06-29）

**症状**：`archive/YYYY-MM-DD/noon.md` 存在，`delivery_markers/` 无对应 marker，用户没收到简报。health_check 不报错。

**真因**：`delivery_watchdog`（no_agent, `0 9,12,21`）和 LLM 日报推送（LLM, `0 9,12,21`）共享同一调度。gateway 同时触发两者时看门狗先跑完（~12:03:28），管线后生成 archive（~12:03:51）→ 看门狗看到空目录 → 静默 → 档案从未投递。

**验证**：
```bash
# 看 archive 和 marker 的时间
ls -l "$TRENDRADAR_HOME/archive/$(date +%Y-%m-%d)/"*.md
ls -l "$TRENDRADAR_HOME/data/delivery_markers/"delivered_$(date +%Y%m%d)*
# archive 存在但 marker 不存在 = 时序竞态命中
```

**修复**：将 `delivery_watchdog` 调度延后 10 分钟（`10 9,12,21 * * *`），或用 `fragment_push + hermes send` 手动补投（见 `references/manual-retro-push.md`）。

**预防**：改看门狗 schedule (+10min)，或让看门狗内部增加重试逻辑。

## 参考

| 文件 | 内容 |
|------|------|
| `references/manual-retro-push.md` | 手动补推工作流 |
| `references/retropush-double-deliver-2026-06-06.md` | 补推重复投递案例 |
| `references/fetch-pipeline-bugs-2026-06-03.md` | fetch pipeline bug 案例 |
| `references/fragment-delivery-pitfall.md` | 分片投递陷阱 |
| `references/deep-analysis-prompt-fix.md` | 2026-06-09 deep analysis 触发逻辑修复（含 SSOT diff + 部署清单） |
| `../../references/PIPELINE.md` | 管线流程 + 渲染格式规范（trendradar 级共享） |

## 投递链路参考

| 文件 | 用途 |
|------|------|
| `references/delivery-canary.md` | **WeCom chat_id canary 7 步协议** — 从清 log → 重启 gateway → inbound 抓 chat_id → 写 .env → 切 wecom 的可重复工作流。**任何 cron job 切 wecom 投递前必读**（2026-06-09 实测） |
