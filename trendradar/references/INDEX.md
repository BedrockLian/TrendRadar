<!-- version: 2.8.0 | last-reviewed: 2026-05-26 -->

# References 索引

> 按功能分类。Agent 按需加载，不必全量读取。
> 标注 `[Skill]` 的文件仅在对应 Skill references/ 中，根目录无副本。

## 🔴 事故档案（出问题时先查这里）

| 文件 | 何时读 | 位置 |
|------|--------|------|
| `traps.md` | 任何不明故障 → 先查这里（22 个有效陷阱） | 根 |
| `traps-archive.md` | 历史已修复陷阱（8 个，防回退时查） | 根 |
| `pipeline-pitfalls.md` | 管线产出 0 条 / 翻译丢失 / Session is closed | 根 |
| `translation-pipeline-sync.md` | 翻译存在但渲染时丢失 | 根 |
| `render-markdown-failures.md` | 渲染脚本报错 / 格式异常 | 根 |
| `health-check-pitfalls.md` | 体检脚本误报 / 子进程失败 | [Skill] self-healing |
| `smoke-test-maintenance.md` | pytest 失败 / ImportError | [Skill] self-healing |
| `ai-translate-cjk-detection.md` | 翻译检测历史演进（已废弃架构） | 根 |
| `migration-idempotency-bug.md` | DB 表丢失但迁移跳过 | [Skill] self-healing |
| `api-diagnosis.md` | DeepSeek 断流 / WeCom WS 抖动 | [Skill] self-healing |
| `fix-recipes.md` | 已验证的质量修复脚本 | 根 |
| `performance-pitfalls.md` | TCP 连接池耗尽 | 根 |
| `fragment-byte-splitting.md` | WeCom 静默截断 / 分片超限 | [Skill] news-secretary |
| `pitfalls-utf8-bytes.md` | UTF-8 字节计数陷阱 | [Skill] system-config |

## 🟡 技术规格（改格式/加源时读）

| 文件 | 何时读 | 位置 |
|------|--------|------|
| `render-format.md` | 修改简报格式前 | 根 |
| `deep-analysis-format.md` | 修改深度分析格式前 | 根 |
| `keyword-architecture.md` | 扩充/修改关键词前 | 根 |
| `sources-format.md` | 添加/修改 RSS 源前 | 根 |
| `sources-management.md` | RSS 源发现与添加流程 | 根 |
| `weekly-format.md` | 写周报前 | 根 |
| `monthly-template.md` | 写月报前 | 根 |
| `performance-optimizer` SKILL.md | 调整评分/推送参数（含参数表） | Skill |

## 🔵 架构文档（理解系统时读）

| 文件 | 何时读 | 位置 |
|------|--------|------|
| `pipeline.md` | 理解管线全貌 | 根 |
| `classification-architecture.md` | 理解分类管线 | 根 |
| `script-rendering.md` | 理解渲染架构决策 | 根 |
| `import-architecture.md` | 理解导入规范 | 根 |
| `render-markdown.md` | 理解渲染脚本内部结构 | 根 |
| `orchestrator-notes.md` | 理解编排器注意事项 | 根 |

## 🟢 运维手册（部署/维护时读）

| 文件 | 何时读 | 位置 |
|------|--------|------|
| `cron-operations.md` | Cron 管理 / Gateway 重启 | 根 |
| `cron-prompt-canonical.md` | 更新日报 cron prompt | 根 |
| `cron-sendmessage-fallback.md` | 理解 cron 投递机制 | 根 |
| `repo-sync.md` | 同步到 Git 仓库（三处同步流程） | 根 |
| `health-check-design.md` | 理解体检设计（14 项 + 4 子检查） | [Skill] self-healing |
| `migration-mechanism.md` | 理解迁移引擎 | [Skill] self-healing |
| `migration-rollback.md` | 回滚迁移 | [Skill] self-healing |
| `cache-cleanup.md` | 缓存清理规程 | [Skill] self-healing |
| `proxy-config.md` | WSL 代理配置 | [Skill] system-config |
| `rsshub-proxy-setup.md` | RSSHub 代理设置 | [Skill] system-config |

## 🟣 可复用模式

| 文件 | 何时读 | 位置 |
|------|--------|------|
| `api-backoff-circuit-breaker.md` | 集成新的 LLM API 时 | [Skill] news-secretary |
| `skill-audit.md` | 修改 Skill 后审计（7 维度检查表） | [Skill] system-config |

## 🟤 文档治理

| 文件 | 何时读 | 位置 |
|------|--------|------|
| `references-consistency-guide.md` | 维护 references/ 本身时。冲突修复 + CI 防护 + 日常铁律 | 根 |
