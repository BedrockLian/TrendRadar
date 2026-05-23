---
name: trendradar-self-healing
slug: trendradar-self-healing
version: 2.3.0
description: 自动体检TrendRadar各组件。检测DB/配置/API/Gateway/全链路/记忆膨胀，修复常见故障。
author: Hermes Agent
metadata:
  hermes:
    tags: [trendradar, health, self-healing, devops]
    cron: 0 15 * * *
    data_dir: ~/.hermes/trendradar
    scripts_dir: ~/.hermes/scripts
---

## 运行
Cron 每日 15:00 跑 `trendradar_health_check.py` (no_agent=true)，有异常推送，健康静默。

## 检查项
DB(fingerprints/heat_tracker)、脚本导入、配置存在、Cron注册、Gateway IPC、API连通、全链路(push_slot_detect/RSS/脚本)、记忆(>90%告警)、进程滞留。
自动修复：数据库迁移(`migrations/runner.migrate()`)、删除空壳DB。

## 记忆压缩（Agent值守）
无独立cron — Agent值守。使用率≥75%时按 `references/memory-compression.md` 协议逐条replace替换。
**压缩后必须报告量化指标**：修改前字符数 → 修改后字符数 → 减少量和减少百分比。确保无核心信息丢失。

## 缓存清理（按序执行）
1. TrendRadar旧缓存(>1天) → 2. `__pycache__`(排除venv) → 3. pip cache purge → 4. apt-get clean → 5. thumbnails → 6. 旧日志gzip → 7. 会话文件 → 8. SQLite VACUUM
详情见 `references/cache-cleanup.md`。

## 常见故障

| 故障 | 修复 |
|------|------|
| 指纹表丢失 | `migrations/runner.migrate()` 统一重建 |
| 空壳DB | 自动删除0字节 fingerprints.db |
| delegate_task 误触发 | step10仅evening调，禁止LLM自行判断 |
| 记忆膨胀(>90%) | Agent `memory` tool 逐条replace |
| API超时 | 框架3次重试+KV缓存 |
| config 包名冲突 | v5.3.0已修复：重命名为 settings.py |
| zstd C扩展缺失 | settings.py三级fallback：compression.zstd→zstandard→普通JSON |
| python3.14t依赖缝隙 | `pip install feedparser zstandard`；需 `export PYTHONPATH=... PYTHON_GIL=0` |
| mail_queue 积累 | 忽略或定期清理 >7天 .eml |
| 导入测试误报 | `python3 -c "import xxx"` 产生的argparse/sys.argv Traceback 无害，不是真实导入失败 |

## 参考文档
| 文件 | 内容 |
|------|------|
| `references/health-check-design.md` | 体检脚本设计 |
| `references/memory-compression.md` | 记忆压缩协议 |
| `references/cache-cleanup.md` | 缓存清理规程（8步顺序） |
| `references/migration-mechanism.md` | 数据库迁移引擎 |
