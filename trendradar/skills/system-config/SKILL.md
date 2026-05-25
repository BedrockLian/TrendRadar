---
name: system-config
slug: system-config
version: 2.9.0
description: TrendRadar 项目路径、Python 环境、Cron 任务、代理配置速查。
author: Hermes Agent
metadata:
  hermes:
    tags: [trendradar, config, setup]
---

## 触发

Agent 需要 TrendRadar 路径/Python 环境/Cron/代理/同步信息时自动加载。

## 项目结构

- **源码/运行时**: `~/.hermes/trendradar/`
- **Git 发布仓**: `~/TrendRadar/`
- **从零搭建**: `~/TrendRadar/SETUP.md`
- **一条龙部署**: `~/TrendRadar/one-key-setup.sh`

## Hermes 关键路径

| 组件 | 路径 |
|------|------|
| 主配置 | `~/.hermes/config.yaml` |
| Cron 配置 | `~/.hermes/cron/jobs.json` |
| 技能目录 | `~/.hermes/skills/trendradar/` |
| 运行日志 | `~/.hermes/logs/agent.log` / `errors.log` |

## Cron 任务

`hermes cron list` 查看所有任务。日报/周报/月报/优化器为 LLM 驱动，体检/维护/看门狗为 no_agent 脚本模式。

**Cron prompt 格式**: 只需透传脚本输出。`sanity_check.py` 在推送层自动拦截禁语，无需 prompt 层重复约束。

## Python 环境

- **解释器**: `python3.14t`（free-threaded）
- **必需**: `export PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0`
- **依赖**: `feedparser zstandard aiohttp pyyaml pyahocorasick`
- **GIL 锁**: `settings.py` 启动时自动检查，`PYTHON_GIL != 0` 输出 RuntimeWarning

## 同步到 Git 仓库

三处需同步：Hermes 运行时、Hermes 脚本、Git 发布仓。详见 `references/repo-sync.md`。

## 维护注意

修改 skill SKILL.md 或 reference 文件后，两处同步执行：`~/.hermes/skills/trendradar/` ↔ `~/TrendRadar/trendradar/skills/`。

## TrendRadar 技能

| 名称 | 用途 |
|------|------|
| news-secretary | 日报推送管线 |
| self-healing | 自动体检 + 自修复 |
| performance-optimizer | 推送质量评分 + 偏好收敛 |
| weekly-report | 每周深度趋势周报 |
| monthly-report | 月度聚合趋势报告 |

## 参考文件

| 文件 | 内容 |
|------|------|
| `references/repo-sync.md` | 三处同步 + 验证流程 |
| `references/rsshub-proxy-setup.md` | RSSHub Docker 代理配置（undici + --import） |
| `references/proxy-config.md` | 米霍姆代理分流架构 + 排查 |
| `references/pipeline.md` | 管线 v2.8.0 全量文档 |
| `references/traps.md` | 已知陷阱全集 |
| `references/pitfalls-utf8-bytes.md` | UTF-8 字节计数陷阱修复 |
