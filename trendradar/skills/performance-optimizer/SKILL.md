---
name: trendradar-performance-optimizer
slug: trendradar-performance-optimizer
version: 2.2.0
description: 渐进优化TrendRadar日报质量与推送偏好。每日21:15自愈式收敛调优。
author: Hermes Agent
tags: [trendradar, quality, push-preference, self-healing]
metadata:
  hermes:
    companion_skills: [trendradar-news-secretary]
---

## 触发

每天 21:15 cron `718b663e8c04` 自动触发，或手动调用。

> 性能维度脚本阶段~7s，远低于阈值，不再作为优化目标。
> 瓶颈在外网HTTP，非CPU，非可优化范围。
> 实际耗时：push_prepare 2.0s + batch_fetch 5.2s（并行后~5.5s）。batch_fetch为全链路瓶颈。

## 质量协议

**评分**：空摘要<5%(+15)、重复<3%(+10)、头条命中≥60%(+10)、每板块≥3条(+10)、外媒满14条(+5)、分布均匀(+10)
扣分：空摘要≥20%(-15)、板块为0(-20)、单源≥50%(-15)。目标 ≥85。

**杠杆**：MIN_SCORE(5-8,±1)、MAX_PER_DOMAIN(±2)、blog recency保底(1-3,±1)、关键词(±5词)、白名单(增/删)。
详见 `references/param-tables.md`。

**交互**：评分<85时列出扣分项+建议，问"修哪个"(编号/all/跳过)。

## 推送偏好协议

**基准**：`settings.py` 中的 `BRIEFING_RATIO`（早24/午32/晚24）和 `DAILY_LIMIT=80` 为事实源。
5板块：top_headlines/foreign_china/tech/economy/gaming。

**偏差**：总量±30%→推送偏差；板块连续多天<3条→饿死；同源连续多天首位→垄断。

**交互**：列出偏差+选项，问"怎么调"。

## 通用规则

- **输出**：直接报告，禁止自述("Now let me"/"Here is"等)。两份维度都达标→`[SILENT]`
- **单参数调整**：每轮改1参数1方向。改善→继续；变差→回滚；3轮无改善→"收敛"，跳过7天后恢复
- **数据采集**：cron output + 脚本打点 + quality scripts

## 参考

| 文件 | 内容 |
|------|------|
| `references/param-tables.md` | 参数调整范围与步长 |
| `references/performance-pitfalls.md` | 已知瓶颈模式 |
