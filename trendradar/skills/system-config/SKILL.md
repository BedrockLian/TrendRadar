---
name: system-config
slug: system-config
version: 2.2.0
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

三处路径需同步：Hermes 运行时 (`~/.hermes/`)、Hermes 中心脚本 (`~/.hermes/scripts/`)、Git 发布仓 (`~/TrendRadar/`)。

详细步骤 + 验证 + 常见遗漏表见 `references/repo-sync.md`。

### 关键注意事项

- **三处一致**：技能目录名、SKILL.md `name:` 字段、cron 的 `skills:` 列表必须一致
- **`references/` 子目录**：某些 skill（如 `self-healing`）有自己的 `references/`——它们是 skill-local 参考文件，不与 central `trendradar/references/` 合并。同步后记得 `git add`，否则 `git status` 显示 `??`
- **依赖文件**：`pyproject.toml` 修改后必须同步 `requirements.txt`（手动维护）。用 `diff <(grep...) <(grep...)` 检查一致性
- **脚本两处存在**：`trendradar_*.py` 同时存在于 `~/.hermes/scripts/`（cron 加载）和 `~/TrendRadar/hermes-scripts/`（仓库发布）。改脚本后两处都要更新

## 维护注意

任何对 skill SKILL.md 或 reference 文件的修改，必须在**两个位置同步**执行：

| 位置 | 路径 | 用途 |
|------|------|------|
| Hermes 运行时 | `~/.hermes/skills/trendradar/<skill>/` | cron 实际加载的版本 |
| Git 发布仓 | `~/TrendRadar/trendradar/skills/<skill>/` | 版本控制 & 分发 |

即：`patch` / `write_file` 后，若文件同时存在于两处，两处都要改。只改一处会导致下一次 `repo-sync.md` 的 `cp -r` 覆盖另一边的改动。

集中 references 位于 `~/.hermes/trendradar/references/`，发布仓对应 `~/TrendRadar/trendradar/references/`。SKILL.md 中引用路径统一为 `references/xxx.md`，不再使用 `news-secretary references/xxx.md` 格式。

## TrendRadar 技能

| 名称 | 用途 |
|------|------|
| `news-secretary` | 日报推送管线（编排器 + 晚间深度分析） |
| `self-healing` | 自动体检 + 自修复（DB/配置/API/Gateway/记忆） |
| `performance-optimizer` | 推送质量评分 + 推送偏好收敛调优 |
| `weekly-report` | 每周深度趋势周报 |
| `monthly-report` | 月度聚合趋势报告 |
