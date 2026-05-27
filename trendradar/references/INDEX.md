<!-- version: 3.0.0 | consolidated: 2026-05-27 | 41 → 9 docs -->

# TrendRadar References Index

Consolidated from 41 reference documents to 9 (+ archive). Each consolidated
document merges multiple originals. See `_archive/` for historical files.

## Active Documents

| File | Contents | Merged From |
|------|----------|-------------|
| `ARCHITECTURE.md` | System architecture, classification, keywords, rendering, migrations, health check, API patterns | classification-architecture.md, import-architecture.md, script-rendering.md, render-markdown.md, orchestrator-notes.md, keyword-architecture.md, migration-mechanism.md, health-check-design.md, api-backoff-circuit-breaker.md |
| `PIPELINE.md` | Pipeline data flow, performance bottlenecks, render format spec, deep analysis format | pipeline.md, performance-pitfalls.md, render-format.md, deep-analysis-format.md |
| `SETUP.md` | Proxy config, RSSHub setup, cache cleanup, cron ops, migration rollback, cron prompt, auto-delivery, source management | proxy-config.md, rsshub-proxy-setup.md, cache-cleanup.md, cron-operations.md, migration-rollback.md, cron-prompt-canonical.md, cron-sendmessage-fallback.md, sources-management.md, sources-format.md |
| `TRAPS.md` | All known pitfalls (48 traps) | traps.md, pipeline-pitfalls.md, translation-pipeline-sync.md, render-markdown-failures.md, health-check-pitfalls.md, smoke-test-maintenance.md, ai-translate-cjk-detection.md, migration-idempotency-bug.md, api-diagnosis.md, fix-recipes.md, fragment-byte-splitting.md, pitfalls-utf8-bytes.md |
| `REPO-SYNC.md` | Git repository sync procedures | (kept as-is) |
| `REFERENCES-CONSISTENCY-GUIDE.md` | References maintenance and conflict resolution | (kept as-is) |
| `SKILL-AUDIT.md` | Skill audit checklist (7 dimensions) | (kept as-is) |
| `DELIVERY-WATERMARK.md` | Delivery marker mechanism documentation | (new) |
| `cron-prompt-generated.md` | Auto-generated cron prompt from pipeline_orchestrator --list-steps | (new, auto-generated) |

## Archive

Files moved to `_archive/`:
- `traps-archive.md` — historically fixed traps (preserved for reference)
- `weekly-format.md` — weekly report template (referenced by weekly-report skill)
- `monthly-template.md` — monthly report template (referenced by monthly-report skill)

## Original → New Mapping

| Original File | New Home |
|---------------|----------|
| `INDEX.md` | → this file (replaced) |
| `ai-translate-cjk-detection.md` | → TRAPS.md §39 |
| `api-backoff-circuit-breaker.md` | → ARCHITECTURE.md §10 |
| `api-diagnosis.md` | → TRAPS.md §44 |
| `cache-cleanup.md` | → SETUP.md §3 |
| `classification-architecture.md` | → ARCHITECTURE.md §3 |
| `cron-operations.md` | → SETUP.md §4 |
| `cron-prompt-canonical.md` | → SETUP.md §6 |
| `cron-sendmessage-fallback.md` | → SETUP.md §7 |
| `deep-analysis-format.md` | → PIPELINE.md §Deep Analysis |
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
| `performance-pitfalls.md` | → PIPELINE.md §Performance |
| `pipeline-pitfalls.md` | → TRAPS.md §31-36 |
| `pipeline.md` | → PIPELINE.md (base) |
| `pitfalls-utf8-bytes.md` | → TRAPS.md §47 |
| `proxy-config.md` | → SETUP.md §1 |
| `references-consistency-guide.md` | → (kept as-is) |
| `render-format.md` | → PIPELINE.md §Render Format |
| `render-markdown-failures.md` | → TRAPS.md §40 |
| `render-markdown.md` | → ARCHITECTURE.md §6 |
| `repo-sync.md` | → (kept as-is) |
| `rsshub-proxy-setup.md` | → SETUP.md §2 |
| `script-rendering.md` | → ARCHITECTURE.md §5 |
| `skill-audit.md` | → (kept as-is) |
| `smoke-test-maintenance.md` | → TRAPS.md §42 |
| `sources-format.md` | → SETUP.md §8 |
| `sources-management.md` | → SETUP.md §8 |
| `traps-archive.md` | → _archive/traps-archive.md |
| `traps.md` | → TRAPS.md (base) |
| `translation-pipeline-sync.md` | → TRAPS.md §37-39 |
| `weekly-format.md` | → _archive/weekly-format.md |

Total: 41 original docs → 9 active + 3 archived + 1 auto-generated = all accounted for.
