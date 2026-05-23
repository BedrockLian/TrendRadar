# trendradar-health-check — 设计

## 运行

Cron `c987a2883174`，每日 15:00 no_agent=true 静默。
脚本: `~/.hermes/scripts/trendradar_health_check.py`

## 静默设计

- 正常 → stdout 空 → 不推送
- 异常 → stdout = Markdown → 推送 WeCom

## 检查项

| # | 函数 | 检查 | 自动修复 |
|---|------|------|---------|
| 1 | check_db | fingerprints 表 | ✅ CREATE TABLE |
| 2 | check_db | heat_tracker 表 | ✅ CREATE TABLE |
| 3 | check_db | DB 非 0 字节 | ✅ 删除空壳 |
| 4 | check_scripts | 8 核心脚本 | ❌ |
| 5 | check_refs | news-format/pipeline/pitfalls | ❌ |
| 6 | check_config | timeline/translate/ai_interests/sources(data_sources key v2.0) | ❌ |
| 7 | check_cron | 3 job 注册 | ❌ |
| 8 | check_gateway | IPC socket + hermes 进程 | ❌ |

## 4. 自动修复

- `auto_repair_missing_table()` — 调用 `trendradar.migrations.runner.migrate()` 重建指纹/热度表，替代手写 CREATE TABLE
- `auto_repair_empty_db()` — 处理 0 字节 DB 文件
- 迁移引擎记录版本到 `_migrations` 表，幂等安全
| 9 | check_data_freshness | curated < 15h | ❌ |
| 10 | check_api | deepseek 可达 | ❌ |
| 11 | check_stale | 无滞留 cron session | ❌ |
| 12 | check_pipeline | slot_detect+RSS+导入+步骤完整性 | ❌ |

## 历史

- v1.0: 20项，含内存预警
- v1.1: 移除内存检查(台式机阈值不合)、12h指纹(与21→09间隔冲突)、curated时效 6h→15h、新增全链路检查
