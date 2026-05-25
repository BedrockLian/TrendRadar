---
name: news-secretary
slug: news-secretary
version: 6.4.0
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
pipeline_orchestrator.py（一键6阶段）
  ① push_slot_detect → ② push_prepare(fetch+curate) → ③ 并行(ai_translate ∥ batch_fetch)
  → ④ render_markdown → ⑤ fragment_push → ⑥ record_fingerprints
  → 输出 JSON: {status, fragments, briefing, stats, needs_deep_analysis}
```

LLM 运行编排器，解析 `fragments` 数组投递。编排器不可用时走 cron prompt 中的 fallback 6步手动管线。
无新条目 → [SILENT]。简报由 `render_markdown.py` 纯脚本生成，Agent 不修改内容。

**cron prompt 同步警告**：修改此 skill 后必须单独更新 cron prompt（`cronjob action=update job_id=90a2866775df prompt=...`）。prompt 独立于 skill 内容，不会自动同步。已踩坑多次（Trap 22-24, 37）。

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

## 输出规范（已固化 — 格式契约在 `render_markdown.py` docstring）

简报和深度分析由纯脚本（`render_markdown.py` / `render_deep_analysis.py`）生成，Agent 只做透传：

1. **不加工内容** — 输出 briefing 字段内容本身，不加任何前缀/后缀/说明文字（如"所有分析已完成""以下是今日晚报""Orchestrator completed with status ok, push_id=noon"等）。脚本输出的已经是完整 Markdown，直接透传即可。
2. **链接格式** — `[【媒体名】](url)`，不加"查看原文"前缀。用户明确拒绝 `[查看原文](url)【来源】` 格式（2026-05-25）。
3. **深度分析独立投递** — 晚间 3 条深度分析各自作为单独 final response 输出，不得拼接在简报末尾，不得与其他分析合并。
4. **空行铁律** — 板块标题后 `\n\n\n`，条目间 `\n\n\n`，条目内部标题→摘要→链接各 `\n\n`。全文无 `---`/`***` 横线。
5. **严禁 LLM 改写** — 简报和分析内容由脚本生成，Agent 不得修改、摘要、重排或添加解释性文字。
6. **格式契约** — 完整 7 条规则写在 `render_markdown.py` 的模块 docstring 中，任何格式修改必须先更新契约。

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
| `references/traps.md` | 已知陷阱全集（TCPConnector/_heat/日期/_is_cjk 等） |
| `references/pipeline.md` | 管线故障恢复 + 性能基线 + raw 缓存层故障模式 |
| `references/cron-operations.md` | Cron 运维：审计清单 + 技能名校验 |
| `references/render-format.md` | 简报输出格式（空行铁律/链接/emoji） |
| `references/deep-analysis-format.md` | 深度分析协议 + 格式化规范 |
| `scripts/render_markdown.py` | **格式契约** — docstring 顶部 7 条铁律，修改格式必须先改它 |

## 兴趣偏好
`config/ai_interests.yaml` — 正面+2分，排除=0分过滤。CLI: `python3 scripts/interest_cli.py {list,add,remove,exclude}`。
