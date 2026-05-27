<!-- version: 3.0.0 | consolidated: 2026-05-27 | 41 → 9 docs -->

# TrendRadar 参考文档索引

从 41 份参考文档合并为 9 份（+ 存档）。每份合并文档整合了多份原始文档。历史文件见 `_archive/`。

## 活跃文档

| 文件 | 内容 | 合并来源 |
|------|------|----------|
| `ARCHITECTURE.md` | 系统架构、分类、关键词、渲染、迁移、健康检查、API 模式 | classification-architecture.md, import-architecture.md, script-rendering.md, render-markdown.md, orchestrator-notes.md, keyword-architecture.md, migration-mechanism.md, health-check-design.md, api-backoff-circuit-breaker.md |
| `PIPELINE.md` | 管线数据流、性能瓶颈、渲染格式规范、深度分析格式 | pipeline.md, performance-pitfalls.md, render-format.md, deep-analysis-format.md |
| `SETUP.md` | 代理配置、RSSHub 搭建、缓存清理、cron 运维、迁移回滚、cron prompt、自动投递、源管理 | proxy-config.md, rsshub-proxy-setup.md, cache-cleanup.md, cron-operations.md, migration-rollback.md, cron-prompt-canonical.md, cron-sendmessage-fallback.md, sources-management.md, sources-format.md |
| `TRAPS.md` | 所有已知陷阱（48 个陷阱） | traps.md, pipeline-pitfalls.md, translation-pipeline-sync.md, render-markdown-failures.md, health-check-pitfalls.md, smoke-test-maintenance.md, ai-translate-cjk-detection.md, migration-idempotency-bug.md, api-diagnosis.md, fix-recipes.md, fragment-byte-splitting.md, pitfalls-utf8-bytes.md |
| `REPO-SYNC.md` | Git 仓库同步流程 | （保持原样） |
| `REFERENCES-CONSISTENCY-GUIDE.md` | 参考文档维护与冲突解决 | （保持原样） |
| `SKILL-AUDIT.md` | 技能审计检查清单（7 个维度） | （保持原样） |
| `DELIVERY-WATERMARK.md` | 投递标记机制文档 | （新增） |
| `cron-prompt-generated.md` | 从 pipeline_orchestrator --list-steps 自动生成的 cron prompt | （新增，自动生成） |

## 存档

移入 `_archive/` 的文件：
- `traps-archive.md` — 历史已修复陷阱（保留供参考）
- `weekly-format.md` — 周报模板（被 weekly-report 技能引用）
- `monthly-template.md` — 月报模板（被 monthly-report 技能引用）

## 原始文件 → 新位置映射

| 原始文件 | 新位置 |
|----------|--------|
| `INDEX.md` | → 本文件（替换） |
| `ai-translate-cjk-detection.md` | → TRAPS.md §39 |
| `api-backoff-circuit-breaker.md` | → ARCHITECTURE.md §10 |
| `api-diagnosis.md` | → TRAPS.md §44 |
| `cache-cleanup.md` | → SETUP.md §3 |
| `classification-architecture.md` | → ARCHITECTURE.md §3 |
| `cron-operations.md` | → SETUP.md §4 |
| `cron-prompt-canonical.md` | → SETUP.md §6 |
| `cron-sendmessage-fallback.md` | → SETUP.md §7 |
| `deep-analysis-format.md` | → PIPELINE.md §深度分析 |
| `fix-recipes.md` | → TRAPS.md §45 |
| `fragment-byte-splitting.md` | → TRAPS.md §48 |
| `health-check-design.md` | → ARCHITECTURE.md §9 |
| `health-check-pitfalls.md` | → TRAPS.md §41 |
| `import-architecture.md` | → ARCHITECTURE.md §2 |
| `keyword-architecture.md` | → ARCHITECTURE.md §4 |
| `migration-idempotency-bug.md` | → TRAPS.md §43 |
| `migration-mechanism.md` | → ARCHITECTURE.md §8 |
| `migration-rollback.md` | → SETUP.md §5 |
| `monthly-template.md` | → _archive/monthly-template.md |
| `orchestrator-notes.md` | → ARCHITECTURE.md §7 |
| `performance-pitfalls.md` | → PIPELINE.md §性能 |
| `pipeline-pitfalls.md` | → TRAPS.md §31-36 |
| `pipeline.md` | → PIPELINE.md（基础） |
| `pitfalls-utf8-bytes.md` | → TRAPS.md §47 |
| `proxy-config.md` | → SETUP.md §1 |
| `references-consistency-guide.md` | → （保持原样） |
| `render-format.md` | → PIPELINE.md §渲染格式 |
| `render-markdown-failures.md` | → TRAPS.md §40 |
| `render-markdown.md` | → ARCHITECTURE.md §6 |
| `repo-sync.md` | → （保持原样） |
| `rsshub-proxy-setup.md` | → SETUP.md §2 |
| `script-rendering.md` | → ARCHITECTURE.md §5 |
| `skill-audit.md` | → （保持原样） |
| `smoke-test-maintenance.md` | → TRAPS.md §42 |
| `sources-format.md` | → SETUP.md §8 |
| `sources-management.md` | → SETUP.md §8 |
| `traps-archive.md` | → _archive/traps-archive.md |
| `traps.md` | → TRAPS.md（基础） |
| `translation-pipeline-sync.md` | → TRAPS.md §37-39 |
| `weekly-format.md` | → _archive/weekly-format.md |

合计：41 份原始文档 → 9 份活跃 + 3 份存档 + 1 份自动生成 = 全部已归位。
