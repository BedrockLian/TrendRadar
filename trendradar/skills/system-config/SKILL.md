---
name: system-config
slug: system-config
version: 1.5.0
description: TrendRadar 项目路径、PYTHONPATH、Python 解释器、环境变量等系统配置知识。
author: Hermes Agent
metadata:
  hermes:
    tags: [trendradar, config, setup, pythonpath]
---

## 项目结构

- **源码目录**: `~/.hermes/trendradar/`
- **Git 发布仓库**: `~/TrendRadar/`
- **Windows 文档备份**: `/mnt/c/Users/ASUS/Documents/TrendRadar-System/trendradar/`
- **从零搭建指南**: `~/TrendRadar/SETUP.md`

## Hermes 相关路径

| 组件 | 路径 |
|------|------|
| 主配置 | `~/.hermes/config.yaml` |
| 技能目录 | `~/.hermes/skills/trendradar/` |
| 中心脚本 | `~/.hermes/scripts/` |
| 系统记忆 | `~/.hermes/memories/MEMORY.md`, `USER.md` |
| 会话数据库 | `~/.hermes/state.db` |
| cron 配置 | `~/.hermes/cron/jobs.json` |
| 运行日志 | `~/.hermes/logs/agent.log` / `errors.log` |

## 核心脚本位置

| 脚本 | 位置 |
|------|------|
| push_prepare.py | `~/.hermes/trendradar/scripts/` |
| batch_fetch.py | `~/.hermes/trendradar/scripts/` |
| fetch_feeds.py | `~/.hermes/trendradar/scripts/` |
| render_markdown.py | `~/.hermes/trendradar/scripts/` |
| render_deep_analysis.py | `~/.hermes/trendradar/scripts/` |
| health_check.py | `~/.hermes/scripts/trendradar_health_check.py` |
| maintenance.py | `~/.hermes/scripts/trendradar_maintenance.py` |
| delivery_watchdog.py | `~/.hermes/scripts/delivery_watchdog.py` |

## Cron 任务清单

| 名称 | Job ID | 调度 | 模式 | 技能/脚本 |
|------|--------|------|------|-----------|
| 日报推送 | `90a2866775df` | `0 9,12,21 * * *` | LLM | news-secretary, multi-search-engine |
| 周报推送 | `c20e2c82deda` | `30 9 * * 1` | LLM Pro | multi-search-engine, deep-research-cli, weekly-report |
| 月报推送 | `0b14c67429ba` | `0 9 1 * *` | LLM Pro | multi-search-engine, deep-research-cli, monthly-report |
| 性能优化器 | `718b663e8c04` | `15 21 * * *` | LLM | performance-optimizer, multi-search-engine, news-secretary |
| 自动体检 | `c987a2883174` | `0 15 * * *` | no_agent | `trendradar_health_check.py` |
| 每日维护 | `68db70cd8556` | `0 3 * * *` | no_agent | `trendradar_maintenance.py` |
| 降级看门狗 | `cab79825520e` | `0 10,14,22 * * *` | no_agent | `delivery_watchdog.py` |

## PYTHONPATH 陷阱（常见故障）

`trendradar` 项目根目录自身有 `__init__.py`，即它是 Python 包。需要将**其父目录**加入 Python 路径，而非项目根目录本身。

```python
# ❌ 错误用法
sys.path.insert(0, str(TR))          # /home/asus/.hermes/trendradar/ — 无法 import trendradar.*
env['PYTHONPATH'] = str(TR)

# ✅ 正确用法：TR.parent
sys.path.insert(0, str(TR.parent))   # /home/asus/.hermes/
env['PYTHONPATH'] = str(TR.parent)   # 使 from trendradar.scripts.common import * 正常工作
```

**cron prompt 中必须设置:**
```bash
export PYTHONPATH=/home/asus/.hermes
```

**2026-05-23 修复教训：健康检查脚本也有此陷阱**
`trendradar_health_check.py` 两处需要 PYTHONPATH：
1. `check_pipeline()` 的 import 检查 — `env['PYTHONPATH'] = str(TR.parent)`（需先 `os.environ.copy()` 保留原有环境）
2. `auto_repair_missing_table()` 的数据库迁移 — `sys.path.insert(0, str(TR.parent))`

## Python 解释器

- 使用 `python3.14t`（免费线程无 GIL 版本，多并发抓取性能更优）
- 需要 `export PYTHON_GIL=0`
- 依赖缝隙修复: `pip install feedparser zstandard`（PyPI wheel 在某些平台不完整）
- 如使用普通 Python 3.12+，需调整 cron prompt 中的解释器路径

## 同步仓库

修改 TrendRadar 系统文件后，同步到 Git 仓库的标准化流程：

```bash
# 同步核心代码（scripts/ + config/ + migrations/）
cp -r ~/.hermes/trendradar/scripts/ ~/TrendRadar/trendradar/
cp -r ~/.hermes/trendradar/config/ ~/TrendRadar/trendradar/
cp -r ~/.hermes/trendradar/migrations/ ~/TrendRadar/trendradar/

# 同步中心脚本
cp ~/.hermes/scripts/trendradar_health_check.py ~/TrendRadar/hermes-scripts/
cp ~/.hermes/scripts/trendradar_maintenance.py ~/TrendRadar/hermes-scripts/
cp ~/.hermes/scripts/delivery_watchdog.py ~/TrendRadar/hermes-scripts/

# 注意：skills 目录不在 repo 中
# ~/.hermes/skills/trendradar/ 是 Hermes 运行时技能目录
# 仓库中的 README.md 仅记录技能名称和用途，不存储 SKILL.md 内容

# 更新文档
# 手动编辑 ~/TrendRadar/README.md 和 ~/TrendRadar/SETUP.md 中的技能名引用

# 提交推送
cd ~/TrendRadar
git add -A
git commit -m "<描述>"
git push
```

⚠️ 始终同步到独立发布仓库 `~/TrendRadar/`，而非直接操作实时系统 `~/.hermes/trendradar/`。
⚠️ 技能文件（SKILL.md）保存在 `~/.hermes/skills/trendradar/` 下，不纳入 Git 仓库。但 `README.md` 和 `SETUP.md` 中的技能名称引用需手动更新——确保三个地方一致：技能目录名、frontmatter `name:` 字段、cron 的 `skills:` 列表。任何一处不匹配都会导致 cron 报 `Skill not found`。

## TrendRadar 内置技能

| 名称 | 用途 |
|------|------|
| `news-secretary` | 日报推送管线（RSS → 分类 → 渲染 → 分片 → 晚间 Pro 分析） |
| `self-healing` | 自动体检 + 自修复（DB/配置/API/Gateway/记忆） |
| `performance-optimizer` | 推送质量评分 + 推送偏好收敛调优 |
| `system-config` | ⬅ 本技能：系统配置速查 |
| `weekly-report` | 每周一深度趋势周报：五大板块 + 信息茧房突围 |
| `monthly-report` | 每月1日聚合月报：四周数据 + 深度搜索验证 |

## 已安装的外部技能

| 名称 | 来源 | 用途 |
|------|------|------|
| `anthropic-skill-creator` | [Anthropic 官方](https://github.com/anthropics/claude-plugins-official) | 技能评估框架（with/without 对比 + 评分 Agent + 盲比） |
| `skill-builder` | clawhub 社区 | 技能编写规范指南 |
| `godmode` | [G0DM0D3](https://github.com/elder-plinius/G0DM0D3) / [L1B3RT4S](https://github.com/elder-plinius/L1B3RT4S) | API 级越狱框架：Parseltongue 输入混淆 + GODMODE 系统指令 + Prefill + ULTRAPLINIAN 多模型竞速 |

## 技能评估基线

`references/evaluation-baseline.md` 记录了 2026-05-23 对三个 TrendRadar 技能的定量评估结果：with-skill 93% vs without-skill 67%（Δ+26%）。后续改进后可重新跑 18 组 subagent 对比检验效果。
