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

详见 `references/ARCHITECTURE.md`。

核心检查：DB (WAL + Storage 统一接入) → 脚本 (21个) → 配置 → Cron → Gateway → API → 数据时效 → 盲点审计 → 拦截器 → 全链路 → 记忆 → 进程。

## 7 个 cron job ID

| ID | 名称 | 类型 |
|----|------|------|
| `90a2866775df` | 日报推送 | LLM |
| `718b663e8c04` | 性能优化器 | LLM |
| `cab79825520e` | 推送看门狗（含空投补发） | no_agent |
| `68db70cd8556` | 每日维护 | no_agent |
| `c987a2883174` | 自动体检 | no_agent |
| `c20e2c82deda` | 周报推送 | LLM |
| `0b14c67429ba` | 月度报告 | LLM |

> Job ID 可能因重建变更。`check_cron()` 硬编码这些 ID。

## 投递失败自动补发

`delivery_watchdog.py` 额外承担 auto-delivery 空投检测（2026-05-26 新增）：

1. **调度**：每日 10:00 / 14:00 / 22:00（cron `cab79825520e`），22:00 距晚间推送仅 1h
2. **检测**：对比 `push_log.json` 最新 evening 条目与 `data/delivery_markers/` 目录
3. **补发**：未标记即自动重新渲染 → sanity_check → `hermes send --to wecom:bl` 补投
4. **循环防护**：补发后写 `delivered_{run_id}.marker`，同一 run_id 只补一次
5. **时效**：仅补发 6 小时内的推送

诊断详见 `../../news-secretary/references/DELIVERY-WATERMARK.md  # was delivery-failure-debug → delivery`。

## 常见故障

详见 `references/TRAPS.md` 和 `references/TRAPS.md`。

## 烟雾测试

每日维护 (`68db70cd8556`) 内含 `pytest tests/` 运行。测试失败会推送到 WeCom。

手动运行:
```bash
cd ~/TrendRadar/trendradar && python -m pytest tests/ -v --tb=short
```

测试维护 + 失败模式速查：`references/SKILL-AUDIT.md  # was smoke-test-maintenance → skill audit`（含 **9 种** 常见失败模式及修复方法，包括 import 死锁零输出超时 #8）。

## 翻译管线专项诊断

翻译大面积缺失时的排查顺序：
1. `_load_source_languages()` 是否返回空 → 检查 `_SOURCES_PATH` 是否用 `get_data_dir()`
2. `get_source_lang()` 对已知外媒平台是否返回 None → 检查 `sources.json` 中对应源的 `language` 字段
3. **`data/sources.json` 是否存在？** — git clean/reset 会删除它 → `_load_source_languages()` 静默返回空 frozensets → `get_source_lang()` 全部 None → 0 条翻译。从备份恢复：`cp backups/trendradar/$(date +%Y%m%d)/sources.json data/`
3. `_load_and_scan` 文件选择是否正确 → 检查是否读到正确日期版文件（三层回退）
4. `ai_translate.py` 是否实际运行 → 手动跑一次验证:
```bash
cd ~/TrendRadar/trendradar && PYTHONPATH=/home/asus/TrendRadar /usr/local/bin/python3.14t scripts/ai_translate.py --push-id {slot}
```
5. **BATCH_SIZE 导致的假翻译** — 摘要正确但标题保持原文不变 (`title_cn == title`)。DeepSeek batch >5 时只翻摘要不翻标题。`BATCH_SIZE = 5`。先清理假 `title_cn` 再重跑。
7. **源被预分类错域** — 特定源的文章一直在 `fetch_all` 中被抓取（检查 raw cache）但从未出现在简报中，可能在 `_preclassify` 阶段被关键词误匹配到 tech/gaming 域 → LLM 精选时被其他专业源挤掉。检查 `_likely_domain` 是否正确，在 `_preclassify()` 的 `SOURCE_DOMAIN_OVERRIDE` 字典中加条目强制分配正确域。
8. **预分类 category fallback 缺失** — `foreign_china` 类别源（BBC 世界/中国、NPR 国际、路透社·国际）掉到 `other`。检查 `_preclassify` 的 fallback 是否覆盖了所有 sources.json 中的 category 值。
9. **短关键词子串误触** — `config/keywords.py` 中 2 字符关键词（FF/AI/AR）通过子串匹配误触任何英文单词中的字母组合。`_likely_domain` 大面积为 tech/gaming 而非预期域时检查此问题。
7. **源 RSS 源可用性** — 直接 `curl localhost:1200/{route}` 测试 RSSHub 响应。若 HTTP 200 有内容但 fetch_feeds 抓不到，可能是代理池耗尽或 aiohttp session 配置问题。单独测试 `_fetch_one()` 可确认。

## 参考文档

| 文件 | 内容 |
|------|------|
| `references/TRAPS.md` | 陷阱全集 |
| `references/ARCHITECTURE.md` | 体检设计：检查项表 + cron ID 表 |
| `references/TRAPS.md` | 维护陷阱（含 git clean 恢复 #9、嵌套包路径 #10、PYTHONPATH import 死锁 #11） |
| `references/PIPELINE.md  # was api-diagnosis → pipeline troubleshooting` | DeepSeek 断流 & WeCom WS 抖动 |
| `references/ARCHITECTURE.md  # was import-architecture → architecture` | 导入架构修复 |
| `references/ARCHITECTURE.md  # was migration-mechanism → architecture` | 迁移引擎架构 |
| `references/ARCHITECTURE.md  # was migration-rollback → architecture` | 迁移回滚约定 |
| `references/TRAPS.md  # was migration-idempotency-bug → traps` | 迁移幂等性 Bug |

| `references/SKILL-AUDIT.md  # was smoke-test-maintenance → skill audit` | 烟雾测试维护：常见失败模式 + 修复方法 |
| `references/SETUP.md  # was cache-cleanup → setup` | 缓存清理规程 |
