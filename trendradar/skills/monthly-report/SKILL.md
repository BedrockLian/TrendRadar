---
name: monthly-report
slug: monthly-report
version: 2.3.0
description: 每月初推送月度趋势研究报告。聚合四周数据+深度搜索验证。
author: Hermes Agent
metadata:
  hermes:
    tags: [monthly, research, trend, deep-dive]
    companion_skills: [multi-search-engine, deep-research-cli]
    platform_delivery: wecom
---

## 触发
cron 每月 1 日 09:00 (Pro, job `0b14c67429ba`)，或手动。

## 核心规则

### 1. 数据源（三层聚合）
① 近 4 周周报（叙事骨架）
② `scripts/aggregate_monthly.py --days 32 --suggest-interests`（量化统计 + 兴趣漂移建议）
③ `deep-research-cli` 六步协议深度搜索，≤10 次 web_search

**兴趣漂移检测**：`--suggest-interests` 分析近 30 天标题高频词对比当前 `ai_interests.yaml`，输出建议新增/删除的关键词。

**量化统计输出**：JSON 含板块分布、来源排名、兴趣漂移建议。

### 2. 报告结构
```
📊 月度概览（抓取/推送量+源分布+5-8关键事件时间线）
🔥 热度Top10（heat_tracker 跨源覆盖+热度分+趋势走向）
📰 各板块深度（每板块3-5事件，事件链→数据→影响→展望→置信度）
📈 趋势研判（跨域交叉+下月新兴话题）
📋 推送批次追溯（run_id 清单）
```
完整模板见 `references/PIPELINE.md  # was monthly-template → pipeline`。

### 3. 信息茧房
引用 `blind_spot_audit.py --days 30`。汇总 `_serendipity: true` 到附录。

### 4. 格式
简报格式和空行规范见 `references/PIPELINE.md  # was render-format → pipeline`。无表格/引用/斜体。外文翻中文。每条至少 1 对立视角。零前置文本。

## 参考

| 文件 | 内容 |
|------|------|
| `references/PIPELINE.md  # was monthly-template → pipeline` | 完整模板 |
| `references/PIPELINE.md  # was render-format → pipeline` | 简报格式规范 |
