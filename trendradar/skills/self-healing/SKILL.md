---
name: self-healing
slug: self-healing
version: 3.1.0
description: 自动体检 TrendRadar 各组件：DB/配置/API/Gateway/记忆。修复常见故障。
author: Hermes Agent
metadata:
  hermes:
    tags: [trendradar, health, self-healing, devops]
    cron: 0 15 * * *
---

## 运行
Cron 每日 15:00 跑 `trendradar_health_check.py` (no_agent=true)。有异常推送 WeCom，健康静默。

## 检查项（15项）

| # | 函数 | 检查 | 自动修复 |
|---|------|------|---------|
| 1 | check_db | fingerprints 表 | ✅ migrate() |
| 2 | check_db | heat_tracker 表 | ✅ migrate() |
| 3 | check_db | 数据库非 0 字节 | ✅ 删除空壳 |
| 4 | check_scripts | 18 个核心脚本存在 | ❌ |
| 5 | check_config | timeline/translate/ai_interests/sources/keywords | ❌ |
| 6 | check_settings_constants | DOMAINS/DOMAIN_LABELS/BRIEFING_RATIO 等 | ❌ |
| 7 | check_cron | 7 个 job ID 全部注册 | ❌ |
| 8 | check_gateway | IPC socket + hermes wecom 进程 | ❌ |
| 9 | check_data_freshness | curated < 15h | ❌ |
| 10 | check_api | deepseek 可达 + 外网出口 | ❌ |
| 11 | check_stale_processes | 所有 cron job ID 的滞留进程 | ❌ |
| 12 | check_memory_size | MEMORY/USER 使用率 (>75% 预警, >90% 告警) | ❌ |
| 13 | check_push_log_backpressure | push_log.json 体积 (100KB/1MB 阈值) | ❌ |
| 14 | check_pipeline | slot_detect+RSS 连通+导入+步骤完整性 | ❌ |
| 15 | _check_system_resources | 磁盘使用率 (≥90% 告警) | ❌ |

## 7 个 cron job ID

| ID | 名称 | 类型 |
|----|------|------|
| `c987a2883174` | 自动体检 | no_agent (健康检查自身) |
| `90a2866775df` | 日报推送 | LLM |
| `68db70cd8556` | 每日维护 | no_agent |
| `cab79825520e` | 推送看门狗 | no_agent |
| `718b663e8c04` | 性能优化器 | LLM |
| `c20e2c82deda` | 周报推送 | LLM |
| `0b14c67429ba` | 月度报告 | LLM |

> Job ID 可能因重建变更。`check_cron()` 硬编码这些 ID —— 重装 cron 后必须同步更新脚本中的 `CRON_JOBS` 字典。

## 常见故障

**诊断优先**: 任何异常先查 `references/traps.md`（29条陷阱全集）。本表仅收录 healing 专属修复。

| 故障 | 修复 |
|------|------|
| 指纹表丢失 | `migrations/runner.migrate()` |
| 空壳DB | 自动删除 0 字节 fingerprints.db |
| 记忆膨胀(>90%) | Agent `memory` tool 逐条 replace |
| 导入测试误报 | 健康检查子进程用 `sys.executable`（系统 python3）而非管线 python3.14t → feedparser/其他依赖缺失。**修复**: 用 `$PYTHON` 环境变量，fallback `/usr/local/bin/python3.14t`，设 `PYTHONPATH` + `PYTHON_GIL=0` |
| python3.14t 依赖缝隙 | `pip install feedparser zstandard` |
| 裸导入残留 | `grep -rn "^from settings import" ~/.hermes/trendradar/scripts/*.py` — 详见 `references/import-architecture.md` |
| cron 技能名不匹配 | `hermes cron list` → 逐项核对 skill 名 vs 磁盘目录 |
| cron prompt 引用已删除脚本/技能 | prompt 独立于 skill 内容，需单独 `cronjob action=update` |
| `push_slot_detect` exit=1 | 两种可能：① `config/timeline.yaml` 缺失（`sys.exit(1)`，输出 `NO_SLOT`）；② 健康检查用系统 python3 调用（缺少 PYTHONPATH）。先确认用的是 python3.14t + 设了 PYTHONPATH |
| `fetch_feeds` 导入在健康检查中失败 | 健康检查用 `sys.executable` 调子进程但 `feedparser` 只装在 python3.14t 上。**修复**: 健康检查脚本顶部定义 `pipeline_python` 逻辑，所有子进程调用统一走该解释器 |
| cron 报告 stub response / 推送丢失但推送时刻无异常 | 查 `errors.log` 是否有 `RemoteProtocolError`（DeepSeek openresty 断流）。**修复**: 补推：直接 render → fragment → final response |
| 用户说没收到但 cron 日志显示发送成功 | 比对推送时刻与 WeCom WS 断连时刻（`agent.log` 中 `WebSocket error`）。详见 `references/api-diagnosis.md` |

## 参考文档

| 文件 | 内容 |
|------|------|
| `references/traps.md` | 陷阱全集 |
| `references/api-diagnosis.md` | DeepSeek 断流 & WeCom WS 抖动 — 排查推送丢失第一步 |
| `references/import-architecture.md` | 导入架构修复 |
| `references/health-check-design.md` | 体检设计：检查项表 + cron ID 表 |
| `references/health-check-pitfalls.md` | 维护陷阱：SKILL_DIR/导入方式/列表同步/日志/解释器 |
