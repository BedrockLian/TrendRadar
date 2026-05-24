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

## 记忆压缩
Agent 值守，无独立 cron。使用率≥75% 时按 `references/memory-compression.md` 协议逐条 replace。
压缩后须报告量化指标（修改前→后字符数，减少量/百分比）。

## 缓存清理（8步顺序）
`references/cache-cleanup.md` — TrendRadar旧缓存 → `__pycache__` → pip cache → apt → thumbnails → 旧日志gzip → 会话文件 → SQLite VACUUM。

## 常见故障

**诊断优先**: 任何异常先查 news-secretary `references/traps.md`（34条陷阱全集）。本表仅收录 healing 专属修复。

| 故障 | 修复 |
|------|------|
| 指纹表丢失 | `migrations/runner.migrate()` |
| 空壳DB | 自动删除 0 字节 fingerprints.db |
| 记忆膨胀(>90%) | Agent `memory` tool 逐条 replace |
| 导入测试误报 | `python3 -c "import xxx"` 产生的 argparse Traceback 无害 |
| python3.14t 依赖缝隙 | `pip install feedparser zstandard` |
| references/ 目录缺失 | `mkdir -p ~/.hermes/trendradar/references && cp -r ~/.hermes/skills/trendradar/news-secretary/references/* $_` |
| 裸导入残留 | `grep -rn "^from settings import" ~/.hermes/trendradar/scripts/*.py` — 详见 news-secretary `references/import-architecture.md` |
| cron 技能名不匹配 | `hermes cron list` → 逐项核对 skill 名 vs 磁盘目录 |
| cron prompt 引用已删除脚本/技能 | prompt 独立于 skill 内容，需单独 `cronjob action=update` |

## 参考文档

| 文件 | 内容 |
|------|------|
| `references/health-check-design.md` | 体检脚本设计 |
| `references/health-check-pitfalls.md` | 健康检查脚本维护陷阱（路径/导入/列表同步） |
| `references/memory-compression.md` | 记忆压缩协议 |
| `references/cache-cleanup.md` | 缓存清理规程 |
| `references/migration-mechanism.md` | 数据库迁移引擎 |
| news-secretary `references/traps.md` | 陷阱全集（交叉引用） |
| news-secretary `references/import-architecture.md` | 导入架构修复 |
