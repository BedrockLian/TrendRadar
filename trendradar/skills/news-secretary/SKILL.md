---
name: news-secretary
slug: news-secretary
version: 6.0.0
description: 聚合多RSS源+博客，推送Markdown简报至企业微信。编排器一键管线 + 晚间Pro深度分析。
author: Hermes Agent
metadata:
  hermes:
    tags: [news, trend, RSS, wecom]
    delivery: wecom
    push_schedule: { merged: "0 9,12,21 * * *" }
    companion_skills: [self-healing, weekly-report, monthly-report, performance-optimizer]
---

## 触发
cron `0 9,12,21 * * *` (morning 24条 / noon 32条 / evening 24条)。晚间追加 3×Pro 深度分析。

## 管线

```
pipeline_orchestrator.py（一键6阶段）
  ① push_slot_detect → ② push_prepare(fetch+curate) → ③ 并行(ai_translate ∥ batch_fetch)
  → ④ render_markdown → ⑤ fragment_push → ⑥ record_fingerprints
  → 输出 JSON: {status, fragments, briefing, stats, needs_deep_analysis}
```

LLM 运行编排器，解析 `fragments` 数组投递。编排器不可用时走 cron prompt 中的 fallback 6步手动管线。
无新条目 → [SILENT]。简报由 `render_markdown.py` 纯脚本生成，Agent 不修改内容。

## 晚间深度分析

仅 evening。`delegate_task` 并行 3 个 Pro 子 Agent（趋势/跨域/风险），各基于当日 curated JSON（不联网）。
输出经 `render_deep_analysis.py --topic "主题"` 管道格式化后作为 final response 逐篇投递（系统自动推送 WeCom）。
完整协议见 `references/deep-analysis-format.md`。

## 运行时
```bash
export PYTHON=/usr/local/bin/python3.14t PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0
```

## 关键参考

| 文件 | 何时读 |
|------|--------|
| `references/traps.md` | 任何异常 — 34条已知陷阱全集 |
| `references/pipeline.md` | 管线故障恢复 + 性能基线 |
| `references/cron-operations.md` | Cron 运维：审计清单 + 技能名校验 |
| `references/render-format.md` | 简报输出格式（板块/空行/emoji） |
| `references/deep-analysis-format.md` | 深度分析协议 + 格式化规范 |
| `references/translation-pipeline-sync.md` | 翻译管线：title_cn偏好 + 来源检测 |
| `references/import-architecture.md` | 脚本导入架构 + 裸导入修复模式 |
| `references/orchestrator-notes.md` | 编排器可靠性：解析/并行/回退 |
| `references/cron-sendmessage-fallback.md` | cron context 下投递机制：auto-delivery 协议 |
| `references/keyword-architecture.md` | 505词×6域完整词表 |
| `references/classification-architecture.md` | 分类规则/优先级 |

## 兴趣偏好
`config/ai_interests.yaml` — 正面+2分，排除=0分过滤。CLI: `python3 scripts/interest_cli.py {list,add,remove,exclude}`。
