---
name: performance-optimizer
slug: performance-optimizer
version: 2.3.0
description: 渐进优化 TrendRadar 日报质量与推送偏好。每日 21:15 自愈式收敛调优。
author: Hermes Agent
tags: [trendradar, quality, push-preference, self-healing]
metadata:
  hermes:
    companion_skills: [news-secretary]
---

## 触发
每天 21:15 cron `718b663e8c04` 自动触发，或手动。

> 性能维度已达目标（脚本阶段 ~7s），不再优化。瓶颈在外网 HTTP，非可优化范围。

## 质量协议

**评分** (>85 达标): 空摘要<5%(+15)、重复<3%(+10)、头条命中≥60%(+10)、每板块≥3条(+10)、外媒满14条(+5)、分布均匀(+10)。扣分: 空摘要≥20%(-15)、板块为0(-20)、单源≥50%(-15)。

**单源集中度预警**: ≥40% 即使未达扣分线也应标注塌缩风险。

**杠杆**: MIN_SCORE(5-8,±1)、MAX_PER_DOMAIN(±2)、blog recency(1-3,±1)、关键词(±5词)、白名单(增/删)。详见 `references/param-tables.md`。

**交互**: 评分<85 → 列出扣分项+建议 → 问修哪个(编号/all/跳过)。单参数调整，3轮无改善→收敛，跳过 7 天恢复。

## 推送偏好协议

**基准**: `settings.py` 的 `BRIEFING_RATIO`（早24/午32/晚24）和 `DAILY_LIMIT=80`。5 板块: top_headlines/foreign_china/tech/economy/gaming。

**偏差检测**: 总量±30%→偏差；板块连续多天<3条→饿死；同源连续首位→垄断；单源≥40%→来源集中。饿死检测需同时看来源数，即使数量达标也可能"来源脆弱型饱和"。

**交互**: 列出偏差+选项 → 问"怎么调"。

## 通用规则

- **输出**: 直接报告，禁止自述。两维度都达标→`[SILENT]`
- **数据采集**: cron output + 脚本打点 + quality scripts

## 已验证修复

详见 `references/fix-recipes.md`：短摘要扩写、tech 上限调整、tirith 关闭、foreign_china 扩充。

## 参考

| 文件 | 内容 |
|------|------|
| `references/fix-recipes.md` | 已验证修复脚本和验证命令 |
| `references/param-tables.md` | 参数调整范围与步长 |
| `references/performance-pitfalls.md` | 已知瓶颈模式 |
| news-secretary `references/render-format.md` | 简报格式规范（交叉引用） |
