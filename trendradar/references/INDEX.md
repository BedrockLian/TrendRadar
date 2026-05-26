<!-- version: 2.8.0 | last-reviewed: 2026-05-26 -->

# References 索引

> 按功能分类。Agent 按需加载，不必全量读取。

## 🔴 事故档案（出问题时先查这里）

| 文件 | 何时读 | 大小 |
|------|--------|------|
| `traps.md` | 任何不明故障 → 先查这里 | 9KB |
| `traps-archive.md` | 历史已修复陷阱（防回退时查） | ~3KB |
| `pipeline-pitfalls.md` | 管线产出 0 条 / 翻译丢失 / Session is closed | 5KB |
| `translation-pipeline-sync.md` | 翻译存在但渲染时丢失 | 5KB |
| `render-markdown-failures.md` | 渲染脚本报错 / 格式异常 | 2KB |
| `health-check-pitfalls.md` | 体检脚本误报 / 子进程失败 | 6KB |
| `smoke-test-maintenance.md` | pytest 失败 / ImportError | 5KB |
| `ai-translate-cjk-detection.md` | 日语/英语未被翻译 | 3KB |
| `migration-idempotency-bug.md` | DB 表丢失但迁移跳过 | 1KB |
| `api-diagnosis.md` | DeepSeek 断流 / WeCom WS 抖动 | 4KB |
| `fix-recipes.md` | 已验证的质量修复脚本 | 2KB |
| `performance-pitfalls.md` | TCP 连接池耗尽 | 1KB |
| `fragment-byte-splitting.md` | WeCom 静默截断 / 分片超限 | 2KB |

## 🟡 技术规格（改格式/加源时读）

| 文件 | 何时读 | 大小 |
|------|--------|------|
| `render-format.md` | 修改简报格式前 | 2KB |
| `deep-analysis-format.md` | 修改深度分析格式前 | 3KB |
| `keyword-architecture.md` | 扩充/修改关键词前 | 3KB |
| `sources-format.md` | 添加/修改 RSS 源前 | 1KB |
| `weekly-format.md` | 写周报前 | 1KB |
| `monthly-template.md` | 写月报前 | 1KB |
| `performance-optimizer` SKILL.md | 调整评分/推送参数前 | 见 Skill |

## 🔵 架构文档（理解系统时读）

| 文件 | 何时读 | 大小 |
|------|--------|------|
| `pipeline.md` | 理解管线全貌 | 4KB |
| `classification-architecture.md` | 理解分类管线 | 2KB |
| `script-rendering.md` | 理解渲染架构决策 | 2KB |
| `import-architecture.md` | 理解导入规范 | 2KB |
| `render-markdown.md` | 理解渲染脚本内部结构 | 3KB |
| `orchestrator-notes.md` | 理解编排器注意事项 | 1KB |

## 🟢 运维手册（部署/维护时读）

| 文件 | 何时读 | 大小 |
|------|--------|------|
| `cron-operations.md` | Cron 管理 / Gateway 重启 | 3KB |
| `cron-prompt-canonical.md` | 更新日报 cron prompt | 2KB |
| `cron-sendmessage-fallback.md` | 理解 cron 投递机制 | 1KB |
| `repo-sync.md` | 同步到 Git 仓库 | 3KB |
| `health-check-design.md` | 理解体检设计 | 3KB |
| `migration-mechanism.md` | 理解迁移引擎 | 1KB |
| `migration-rollback.md` | 回滚迁移 | 2KB |
| `cache-cleanup.md` | 缓存清理规程 | 2KB |

## 🟣 可复用模式

| 文件 | 何时读 | 大小 |
|------|--------|------|
| `api-backoff-circuit-breaker.md` | 集成新的 LLM API 时 | 2KB |
| `skill-audit.md` | 修改 Skill 后审计 | 2KB |
