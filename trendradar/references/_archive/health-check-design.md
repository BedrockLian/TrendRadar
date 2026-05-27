# trendradar-health-check — 设计

## 运行

Cron `c987a2883174`，每日 15:00 no_agent=true 静默。
脚本: `~/.hermes/scripts/trendradar_health_check.py`

## 静默设计

- 正常 → stdout 空 → 不推送
- 异常 → stdout = Markdown → 推送 WeCom

## 检查项（14项）

| # | 函数 | 检查 | 自动修复 |
|---|------|------|---------|
| 1 | check_db | fingerprints 表 | ✅ migrate() |
| 2 | check_db | heat_tracker 表 | ✅ migrate() |
| 3 | check_db | 数据库非 0 字节 | ✅ 删除空壳 |
| 4 | check_scripts | 18 个核心脚本存在 | ❌ |
| 5 | check_config | YAML+JSON+keywords.py 完整性 | ❌ |
| 6 | check_settings_constants | DOMAINS/DOMAIN_LABELS/BRIEFING_RATIO 等 | ❌ |
| 7 | check_cron | 7 个 job ID 全部注册 | ❌ |
| 8 | check_gateway | IPC socket + hermes wecom 进程 | ❌ |
| 9 | check_data_freshness | curated < 15h | ❌ |
| 10 | check_api | deepseek + 外网出口可达 | ❌ |
| 11 | check_stale_processes | 所有 cron job ID 的滞留进程 | ❌ |
| 12 | check_memory_size | MEMORY/USER 使用率 (>75% 预警) | ❌ |
| 13 | check_push_log_backpressure | push_log.json 体积 (100KB/1MB) | ❌ |
| 14 | check_pipeline | slot_detect+RSS 连通+导入+步骤完整性 | ❌ |
| 15 | _check_system_resources | 磁盘使用率 (≥90% 告警) | ❌ |

## 7 个 Cron Job ID

| ID | 名称 | 类型 |
|----|------|------|
| `c987a2883174` | 自动体检 | no_agent |
| `90a2866775df` | 日报推送 | LLM |
| `68db70cd8556` | 每日维护 | no_agent |
| `cab79825520e` | 推送看门狗 | no_agent |
| `718b663e8c04` | 性能优化器 | LLM |
| `c20e2c82deda` | 周报推送 | LLM |
| `0b14c67429ba` | 月度报告 | LLM |

## 自动修复

- `auto_repair_missing_table()` — 调用 `repair_missing_tables()` + `migrate()` 重建指纹/热度表
- `auto_repair_empty_db()` — 删除 0 字节 DB 文件
- 迁移引擎幂等安全，记录版本到 `_migrations` 表

## Python 解释器注意事项

所有子进程调用（push_slot_detect、导入检查）必须使用管线的 python3.14t，而非系统 python3：

```python
pipeline_python = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')
if not os.access(pipeline_python, os.X_OK):
    pipeline_python = sys.executable  # fallback
penv = os.environ.copy()
penv['PYTHONPATH'] = str(TR.parent)     # /home/asus/.hermes
penv.setdefault('PYTHON_GIL', '0')
subprocess.run([pipeline_python, ...], env=penv)
```

系统 python3 缺少 `feedparser`、`zstandard` 等仅装在 python3.14t 上的依赖，导致导入检查误报。

## 历史

- v1.0: 20项，含内存预警
- v1.1: 移除内存检查(台式机阈值不合)、12h指纹、curated时效 6h→15h、新增全链路检查
- v2.0: 15项，新增 settings 常量/ push_log 体积/磁盘资源/7 cron IDs
