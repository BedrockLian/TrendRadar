---
name: news-secretary
slug: news-secretary
version: 6.5.0
description: 聚合多RSS源+博客，推送Markdown简报至企业微信。编排器一键管线 + 晚间Pro深度分析。
author: Hermes Agent
metadata:
  hermes:
    tags: [news, trend, RSS, wecom]
    delivery: wecom
    push_schedule: { merged: "0 9,12,21 * * *" }
    companion_skills: [self-healing, weekly-report, monthly-report, performance-optimizer, system-config]
---

## 触发
cron `0 9,12,21 * * *` (morning 30条 / noon 30条 / evening 20条, 日上限80)。晚间追加 3×Pro 深度分析。

## 管线

```
pipeline_orchestrator.py（v2.8.0 — 一键7阶段）
  ① push_slot_detect → ② push_prepare(fetch+curate) → ③ 并行(ai_translate ∥ batch_fetch)
  → ④ render_markdown → ⑤ fragment_push（UTF-8 字节计数分片） → ⑥ record_fingerprints（Storage 统一接入）
  → 输出 JSON: {status, fragments, briefing, stats, needs_deep_analysis}
```

LLM 运行编排器，解析 `fragments` 数组投递。编排器不可用时走 cron prompt 中的 fallback 手动管线。

### 自动特性（v6.5.0）

- **SILENT 闭环**：无新条目时自动删除 curated/fetch 中间文件，`fragments=[]` 显式空数组，防止 Agent 画蛇添足。
- **UTF-8 字节分片**：`fragment_push.py` 严格 3800 字节/片 (WeCom 4096 硬限制)，段落→句子→硬切三级递降，防静默截断。
- **并行翻译+抓取**：阶段③ `ThreadPoolExecutor` 真并行 `ai_translate ∥ batch_fetch`。
- **SSOT 自描述**：`--list-steps` 输出管道步骤 JSON，Agent 启动前动态读取而非依赖 Skill 中手动维护的步骤。
- **启动自检**：`--check-version` 校验所有依赖脚本存在，缺件触发 `EXIT_CONFIG_ERROR`。
- **Storage 统一接入**：`record_fingerprints.py` / `heat_tracker.py` 通过 `Storage.db()` 统一 WAL 连接，消除 raw `sqlite3.connect()`。
- **迁移回滚**：`migrations/runner.py` 支持 `down(target_version)`，每条 `.sql` 迁移文件须带 `-- down: <SQL>` 回滚注释。

简报由 `render_markdown.py` 纯脚本生成，Agent 不修改内容。

**cron prompt 同步警告**：修改此 skill 后必须单独更新 cron prompt（`cronjob action=update job_id=90a2866775df prompt=...`）。prompt 独立于 skill 内容，不会自动同步。

## 翻译管线（关键！）

外语文章翻译由 `ai_translate.py` 处理，规则：

1. **按来源定语言（来自 sources.json）** — `get_source_lang()` 读取 `data/sources.json` 每个源的 `language` + `platform` + `name` 字段。单真相源：加新源设好 `language` 即可，不再维护独立的映射文件。
2. **文件同步** — ai_translate 和 render_markdown 必须读同一文件（先日期版，fallback 非日期版）。已修：2026-05-24。
3. **render 优先 title_cn** — `render_markdown.py` `_format_item` 取 `title_cn`/`summary_cn`，不回落到原始 title/summary。
4. **cron prompt 直接输出 BRIEFING** — `send_message` 在 cron context 不可用。prompt 第7步直接输出脚本渲染结果，不经过 LLM 重写。
5. **items_to_translate tuple** — `needs_title`/`needs_summary` 由 `bool(source_lang)` 驱动（非 None 就翻译），第8个元素 `source_lang` (`'English'`/`'Japanese'`/`None`) 必须存在。来源语言由 `data/sources.json` 每个源的 `language` 字段决定（`_scan()` 提取 `en`/`ja` 源的 `platform`+`name` 做子串匹配）。`translate.yaml` 已淘汰（2026-05-25）。旧 CJK 启发式函数（`_is_cjk`/`cjk_ratio`/`needs_translation`/`detect_source_lang`）已于 2026-05-25 全部移除。

## 晚间深度分析

仅 evening。`delegate_task` 并行 3 个 Pro 子 Agent（趋势/跨域/风险），各基于当日 curated JSON（不联网）。
输出经 `render_deep_analysis.py --topic "主题"` 管道格式化后作为 final response 逐篇投递（系统自动推送 WeCom）。
完整协议见 `references/deep-analysis-format.md`。

**重要：每条分析作为独立 final response 分别输出，不得与简报正文拼接在一起。** 简报走 step 3, 分析走 step 4, 互不干扰。

## 输出规范（脚本固化 + `sanity_check.py` 拦截）

简报和深度分析由纯脚本生成，Agent 只做透传。`sanity_check.py` 在发布前自动扫描禁语/死链/敏感词/HTML残留。

1. **透传简报** — 输出 JSON `briefing` 字段内容本身。`sanity_check.py` 自动拦截 "As an AI language model" / "Here is your report" 等禁语。
2. **链接格式** — `[【媒体名】](url)`，不加"查看原文"前缀。
3. **深度分析独立投递** — 晚间 3 条深度分析各自作为单独 final response 输出。
4. **空行铁律** — 板块标题后 `\n\n\n`，条目间 `\n\n\n`，全文无 `---`/`***` 横线。
5. **格式契约** — 完整规则在 `render_markdown.py` 模块 docstring 中，修改格式必须先更新契约。

## 运行时
```bash
export PYTHON=/usr/local/bin/python3.14t PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0
```

## 关键参考

| 文件 | 何时读 |
|------|--------|
| `references/cron-sendmessage-fallback.md` | cron context 下投递机制：auto-delivery 协议 |
| `references/translation-pipeline-sync.md` | 翻译管线：title_cn偏好 + 来源检测 + 文件优先级 |
| `references/sources-management.md` | RSS 源发现与添加（BBC/NYT/NPR/NHK 模式） |
| `references/traps.md` | 已知陷阱全集（30 条） |
| `references/pipeline.md` | 管线 v2.8.0 全量文档（性能/故障恢复/自动特性） |
| `references/pitfalls-utf8-bytes.md` | UTF-8 字节计数陷阱：`_find_last` 修复 |
| `references/cron-operations.md` | Cron 运维：审计清单 + 技能名校验 |
| `references/render-format.md` | 简报输出格式（空行铁律/链接/emoji） |
| `references/deep-analysis-format.md` | 深度分析协议 + 知识图谱（--context 实体提取） |
| `references/pipeline-pitfalls.md` | 管线运维陷阱全集 |
| `references/cron-prompt-canonical.md` | 日报 cron prompt 标准文本 |
| `scripts/render_markdown.py` | **格式契约** — docstring 顶部 7 条铁律 |
| `scripts/sanity_check.py` | **发布前拦截器** — 禁语/死链/敏感词/HTML残留扫描 |
| `references/cron-prompt-canonical.md` | 日报 cron prompt 标准文本，skill 修改后同步 prompt 时直接用 |
| `scripts/render_markdown.py` | **格式契约** — docstring 顶部 7 条铁律，修改格式必须先改它 |
| `references/fragment-push-byte-splitting.md` | 字节级分片技术：UTF-8 计数 + 三级递降 + `_find_last` 字节-vs-字符陷阱 |

## 兴趣偏好
`config/ai_interests.yaml` — 正面+2分，排除=0分过滤。CLI: `python3 scripts/interest_cli.py {list,add,remove,exclude}`。
