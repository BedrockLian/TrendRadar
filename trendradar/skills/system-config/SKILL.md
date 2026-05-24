---
name: system-config
slug: system-config
version: 2.0.0
description: TrendRadar 项目路径、PYTHONPATH、Python 解释器、环境变量速查。
author: Hermes Agent
metadata:
  hermes:
    tags: [trendradar, config, setup, pythonpath]
---

## 项目结构

- **源码/运行时**: `~/.hermes/trendradar/`（Python 包，有 `__init__.py`）
- **Git 发布仓库**: `~/TrendRadar/`
- **从零搭建指南**: `~/TrendRadar/SETUP.md`

## Hermes 关键路径

| 组件 | 路径 |
|------|------|
| 主配置 | `~/.hermes/config.yaml` |
| Cron 配置 | `~/.hermes/cron/jobs.json` |
| 技能目录 | `~/.hermes/skills/trendradar/` |
| 运行日志 | `~/.hermes/logs/agent.log` / `errors.log` |

## Cron 任务

运行 `hermes cron list` 查看当前所有任务。
日报/周报/月报/性能优化器为 LLM 驱动（加载对应 skill），体检/维护/看门狗为 no_agent 脚本模式。

## PYTHONPATH（关键陷阱）

`trendradar/` 目录自身有 `__init__.py`，是 Python 包。**必须将父目录加入 PYTHONPATH**：

```python
# ✅ 正确
sys.path.insert(0, str(TR.parent))   # /home/asus/.hermes/
env['PYTHONPATH'] = str(TR.parent)   # 使 from trendradar.scripts.xxx import * 正常

# ❌ 错误
sys.path.insert(0, str(TR))          # /home/asus/.hermes/trendradar/ — import 失败
```

cron prompt 和 subprocess 调用必须 `export PYTHONPATH=/home/asus/.hermes`。

## Python 解释器

- `python3.14t`（free-threaded，多并发抓取性能更优）
- 需 `export PYTHON_GIL=0`
- 依赖: `pip install feedparser zstandard`

## 同步到 Git 仓库

详见 `references/repo-sync.md`。核心：同步 scripts/config/migrations 到 `~/TrendRadar/`，skills 不纳入 repo。
需手动确保三个地方一致：技能目录名、frontmatter `name:` 字段、cron 的 `skills:` 列表。

## TrendRadar 技能

| 名称 | 用途 |
|------|------|
| `news-secretary` | 日报推送管线（编排器 + 晚间深度分析） |
| `self-healing` | 自动体检 + 自修复（DB/配置/API/Gateway/记忆） |
| `performance-optimizer` | 推送质量评分 + 推送偏好收敛调优 |
| `weekly-report` | 每周深度趋势周报 |
| `monthly-report` | 月度聚合趋势报告 |
