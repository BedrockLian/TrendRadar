---
name: trendradar-news-secretary
slug: trendradar-news-secretary
version: 5.5.0
description: 聚合多RSS源+博客推送Markdown简报至企业微信。Flash管线策展+Pro晚间深度分析。
author: Hermes Agent
metadata:
  hermes:
    tags: [news, trend, RSS, wecom]
    delivery: wecom
    push_schedule: { merged: "0 9,12,21 * * *" }
    data_dir: ~/.hermes/trendradar
    scripts_dir: ~/.hermes/trendradar/scripts
    companion_skills: [monthly-trend-report, trendradar-self-healing]
---

## Pipeline

```
timeline.yaml → push_slot_detect → push_prepare(RSS+blog+AC分类)
  → track_events / batch_fetch ∥ ai_translate → render_briefing(5路并行API,~9s)
  → fragment_push(板块分片) → record_fingerprints(zstd)
  → [晚间] delegate_task 3×Pro并行分析
```

## 调度
`0 9,12,21 * * *` 对应 morning(24条) / noon(32条) / evening(24条)。晚间增加 3 Pro Agent 深度分析。

## 运行时
- free-threaded Python 3.14t — `export PYTHON=/usr/local/bin/python3.14t PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0`
- 依赖: `python3.14t -m pip install feedparser zstandard`
- 模型: Flash(deepseek-v4-flash)管线 + Pro(deepseek-v4-pro)晚间分析

## 关键参考
| 文件 | 什么时候看 |
|------|-----------|
| `references/render-format.md` | 简报格式终极规范（渲染脚本产出格式） |
| `references/traps.md` | 遇到异常时排查（16条已知陷阱） |
| `references/pipeline.md` | 管线故障恢复 + 性能基线 |
| `references/classification-architecture.md` | 分类规则/优先级/关键词规模 |
| `references/keyword-architecture.md` | 505词×6域完整词表 |
| `references/free-threaded-build.md` | python3.14t 编译/安装/zstd降级 |
| `references/sources-format.md` | sources.json v2.0 schema |

## 兴趣偏好
`config/ai_interests.yaml` — 正面+2分，排除=0分过滤。CLI: `python3 scripts/interest_cli.py {list,add,remove,exclude}`。

## 故障恢复
```bash
rm -f ~/.hermes/trendradar/cache/batch_{slot}.json
rm -f ~/.hermes/trendradar/data/curated_{slot}.json
cronjob action=run job_id=90a2866775df
```

## 静默规则
- 无新条目 → 返回 [SILENT]
- 仅异常时告警，正常无声
- 简报由 render_briefing.py 生成，Agent 不修改格式
