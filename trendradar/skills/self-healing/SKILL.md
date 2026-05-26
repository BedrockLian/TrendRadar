---
name: self-healing
slug: self-healing
version: 3.4.0
description: 自动体检 TrendRadar 各组件：DB/配置/API/Gateway/记忆。修复常见故障。
author: Hermes Agent
metadata:
  hermes:
    tags: [trendradar, health, self-healing, devops]
    cron: 0 15 * * *
---

## 运行
Cron 每日 15:00 跑 `trendradar_health_check.py` (no_agent=true)。有异常推送 WeCom，健康静默。

## 检查项（14项 + 4 个子检查）

详见 `references/health-check-design.md`。

核心检查：DB (WAL + Storage 统一接入) → 脚本 (21个) → 配置 → Cron → Gateway → API → 数据时效 → 盲点审计 → 拦截器 → 全链路 → 记忆 → 进程。

## 7 个 cron job ID

| ID | 名称 | 类型 |
|----|------|------|
| `90a2866775df` | 日报推送 | LLM |
| `718b663e8c04` | 性能优化器 | LLM |
| `cab79825520e` | 推送看门狗 | no_agent |
| `68db70cd8556` | 每日维护 | no_agent |
| `c987a2883174` | 自动体检 | no_agent |
| `c20e2c82deda` | 周报推送 | LLM |
| `0b14c67429ba` | 月度报告 | LLM |

> Job ID 可能因重建变更。`check_cron()` 硬编码这些 ID。

## 常见故障

详见 `references/health-check-pitfalls.md` 和 `references/traps.md`。

## 烟雾测试

每日维护 (`68db70cd8556`) 内含 `pytest tests/` 运行（103 tests, 2026-05-26）。测试失败会推送到 WeCom。

手动运行:
```bash
cd ~/TrendRadar/trendradar && python -m pytest tests/ -v --tb=short
```

测试维护 + 失败模式速查：`references/smoke-test-maintenance.md`（含 6 种常见失败模式及修复方法）。

## 翻译管线专项诊断

翻译大面积缺失时的排查顺序：
1. `_load_source_languages()` 是否返回空 → 检查 `_SOURCES_PATH` 是否用 `get_data_dir()`
2. `get_source_lang()` 对已知外媒平台是否返回 None → 检查 `sources.json` 中对应源的 `language` 字段
3. `_load_and_scan` 文件选择是否正确 → 检查是否读到正确日期版文件（三层回退）
4. `ai_translate.py` 是否实际运行 → 手动跑一次验证:
```bash
cd ~/TrendRadar/trendradar && PYTHONPATH=/home/asus/TrendRadar /usr/local/bin/python3.14t scripts/ai_translate.py --push-id {slot}
```
5. **BATCH_SIZE 导致的假翻译** — 摘要正确但标题保持原文不变 (`title_cn == title`)。DeepSeek batch >5 时只翻摘要不翻标题。`BATCH_SIZE = 5`。先清理假 `title_cn` 再重跑。

## 参考文档

| 文件 | 内容 |
|------|------|
| `references/traps.md` | 陷阱全集 |
| `references/health-check-design.md` | 体检设计：检查项表 + cron ID 表 |
| `references/health-check-pitfalls.md` | 维护陷阱 |
| `references/api-diagnosis.md` | DeepSeek 断流 & WeCom WS 抖动 |
| `references/import-architecture.md` | 导入架构修复 |
| `references/migration-mechanism.md` | 迁移引擎架构 |
| `references/migration-rollback.md` | 迁移回滚约定 |
| `references/migration-idempotency-bug.md` | 迁移幂等性 Bug |
| `references/sources-management.md` | 信息源管理 |
| `references/smoke-test-maintenance.md` | 烟雾测试维护：常见失败模式 + 修复方法 |
| `references/cache-cleanup.md` | 缓存清理规程 |
