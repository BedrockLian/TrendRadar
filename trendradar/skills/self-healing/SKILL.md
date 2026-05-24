---
name: self-healing
slug: self-healing
version: 3.0.0
description: 自动体检 TrendRadar 各组件：DB/配置/API/Gateway/记忆。修复常见故障。
author: Hermes Agent
metadata:
  hermes:
    tags: [trendradar, health, self-healing, devops]
    cron: 0 15 * * *
---

## 运行
Cron 每日 15:00 跑 `trendradar_health_check.py` (no_agent=true)。有异常推送 WeCom，健康静默。

## 检查项
DB(fingerprints/heat_tracker)、脚本导入、配置、Cron注册、Gateway IPC、API连通、全链路(push_slot_detect/RSS)、记忆(>90%告警)、进程滞留。
自动修复：数据库迁移(`migrations/runner.migrate()`)、删除空壳DB。

## 常见故障

**诊断优先**: 任何异常先查 `references/traps.md`（34条陷阱全集）。本表仅收录 healing 专属修复。

| 故障 | 修复 |
|------|------|
| 指纹表丢失 | `migrations/runner.migrate()` |
| 空壳DB | 自动删除 0 字节 fingerprints.db |
| 记忆膨胀(>90%) | Agent `memory` tool 逐条 replace |
| 导入测试误报 | `python3 -c "import xxx"` 产生的 argparse Traceback 无害 |
| python3.14t 依赖缝隙 | `pip install feedparser zstandard` |
| 裸导入残留 | `grep -rn "^from settings import" ~/.hermes/trendradar/scripts/*.py` — 详见 `references/import-architecture.md` |
| cron 技能名不匹配 | `hermes cron list` → 逐项核对 skill 名 vs 磁盘目录 |
| cron prompt 引用已删除脚本/技能 | prompt 独立于 skill 内容，需单独 `cronjob action=update` |

## 参考文档

| 文件 | 内容 |
|------|------|
| `references/traps.md` | 陷阱全集 |
| `references/import-architecture.md` | 导入架构修复 |
