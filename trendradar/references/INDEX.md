<!-- version: 3.1.0 | consolidated: 2026-05-30 | 41 → 8 active docs -->

# TrendRadar 参考文档索引

从 41 份参考文档合并为 8 份（+ 存档）。每份合并文档整合了多份原始文档。历史文件见 `_archive/`。

## 活跃文档

| 文件 | 内容 | 合并来源 |
|------|------|----------|
| `ARCHITECTURE.md` | 系统架构、分类、关键词、渲染、迁移、健康检查、API 模式 | 9 份原始文档 |
| `PIPELINE.md` | 管线数据流、性能瓶颈、渲染格式规范、深度分析格式 | 4 份原始文档 |
| `SETUP.md` | 代理配置、缓存清理、cron 运维、迁移回滚、cron prompt、自动投递、源管理 | 9 份原始文档 |
| `TRAPS.md` | 所有已知陷阱（48 个陷阱） | 12 份原始文档 |
| `REPO-SYNC.md` | Git 仓库同步流程（三处路径） | 保持原样 |
| `REFERENCES-CONSISTENCY-GUIDE.md` | 参考文档跨 Skill 同步指南 | 精简版（删历史修复步骤） |
| `SKILL-AUDIT.md` | 技能审计检查清单（7 个维度） | 保持原样 |
| `DELIVERY-WATERMARK.md` | 投递水印机制：MarkerDir + delivery_watchdog + 手动标记 | 保持原样 |

## 存档

移入 `_archive/` 的文件：
- `traps-archive.md` — 历史已修复陷阱（保留供参考）

## 已删除（内容已合并或过时）

> 历史删除记录见 git log 2026-05-27 ~ 2026-05-30 提交。
