---
name: trendradar-system-config
slug: trendradar-system-config
version: 1.0.1
description: TrendRadar 项目路径、PYTHONPATH、Python 解释器、环境变量等系统配置知识。
author: Hermes Agent
metadata:
  hermes:
    tags: [trendradar, config, setup, pythonpath]
---

## 项目结构

- 源码: `~/.hermes/trendradar/`
- 健康检查脚本: `~/.hermes/scripts/trendradar_health_check.py`
- 其他中心脚本: `~/.hermes/scripts/delivery_watchdog.py`, `~/.hermes/scripts/trendradar_maintenance.py`
- 发布仓库: `~/TrendRadar/`
- 备份: `~/.hermes/trendradar-backup/`

## PYTHONPATH 陷阱（常见故障）

`trendradar` 项目根目录 `/home/asus/.hermes/trendradar/` 自身有 `__init__.py`，即它是 `trendradar` Python 包。

```python
# ❌ 在脚本中使用 str(TR) 不行
sys.path.insert(0, str(TR))          # /home/asus/.hermes/trendradar/
env['PYTHONPATH'] = str(TR)          # 无法 import trendradar.*

# ✅ 必须用 TR.parent (父目录)
sys.path.insert(0, str(TR.parent))   # /home/asus/.hermes/
env['PYTHONPATH'] = str(TR.parent)   # 使 from trendradar.scripts.common import * 正常工作
```

**2026-05-23 修复教训：健康检查脚本也有此陷阱**
`trendradar_health_check.py` 中两处需要 PYTHONPATH：
1. `check_pipeline()` 的 import 检查 — 用 `env['PYTHONPATH'] = str(TR.parent)` 传入子进程
2. `auto_repair_missing_table()` 的 `from trendradar.migrations.runner import migrate` — 用 `sys.path.insert(0, str(TR.parent))`

**cron prompt 中:**
```bash
export PYTHONPATH=/home/asus/.hermes
```

## Python 解释器

- 使用 `python3.14t`（免费线程版本）
- 需要 `export PYTHON_GIL=0`
- 依赖缝隙修复: `pip install feedparser zstandard`

## 关键脚本路径

| 脚本 | 位置 |
|------|------|
| push_prepare.py | `~/.hermes/trendradar/scripts/` |
| batch_fetch.py | `~/.hermes/trendradar/scripts/` |
| fetch_feeds.py | `~/.hermes/trendradar/scripts/` |
| health_check.py | `~/.hermes/scripts/trendradar_health_check.py` |
| delivery_watchdog.py | `~/.hermes/scripts/delivery_watchdog.py` |
| maintenance.py | `~/.hermes/scripts/trendradar_maintenance.py` |
