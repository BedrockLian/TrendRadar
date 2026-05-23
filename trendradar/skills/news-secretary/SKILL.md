---
name: trendradar-news-secretary
slug: trendradar-news-secretary
version: 5.5.0
description: 聚合多RSS源+博客推送Markdown简报至企业微信。Flash管线策展+Pro晚间深度分析。即使slot_detect返回NO_SLOT也应主动尝试推送。
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

## 晚间深度分析协议（evening 专属）

仅在 evening 时段执行。用 `delegate_task` 并行启动 3 个 Pro 子 agent，分别做以下分析：

### 分析 1：趋势与模式识别
**目标**：从今日简报全量条目中识别跨板块的宏观趋势和模式。
**输出格式**：`pro_analysis_1_trends.md`
- 3-5 个核心趋势，每个趋势包含：趋势名称、关联条目数、跨板块分布、置信度
- 示例输出：
```markdown
| 趋势 | 条目数 | 涉及板块 | 置信度 |
|------|--------|---------|--------|
| AI焦虑商业化 | 12 | tech/economy/top_headlines | 高 |
```

### 分析 2：跨域影响分析
**目标**：分析事件之间的因果关系和传导链。例如地缘冲突→航运→供应链→经济的完整链路。
**输出格式**：`pro_analysis_2_cross_domain.md`
- 2-3 条传导链，每条包含：起点事件、中间传导、终端影响、证据条目

### 分析 3：风险与机会评估
**目标**：识别明日潜在风险和机会，按影响程度分级。
**输出格式**：`pro_analysis_3_risk_opportunity.md`
- 🔴 高风险（概率+影响）：1-2 条
- 🟢 机会（概率+影响）：1-2 条
- 每条附关联条目引用

### 通用规则
- 使用 Pro 模型（`deepseek-v4-pro`），每分析独立子 agent
- 3 个分析并行启动，不串行
- 输出保存到 `cache/` 目录，文件名带日期: `pro_{n}_{topic}_{YYYYMMDD}.md`
- 由 `record_fingerprints.py` 在下游记录分析产出

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
