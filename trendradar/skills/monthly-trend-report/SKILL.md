---
name: monthly-trend-report
slug: monthly-trend-report
version: 2.1.0
description: 每月初推送月度趋势研究报告。聚合四周数据+深度搜索验证。
author: Hermes Agent
metadata:
  hermes:
    tags: [monthly, research, trend, deep-dive]
    data_dir: ~/.hermes/trendradar
    scripts_dir: ~/.hermes/trendradar/scripts
    companion_skills:
      - multi-search-engine
      - deep-research-cli
    platform_delivery: wecom
---

## 触发

cron `0b14c67429ba` 每月1日 09:00(Pro)，或手动。

## 核心规则

### 1. 数据源（三层聚合）
① 近4周周报（叙事骨架）
② `scripts/aggregate_monthly.py` 月度统计（量化支撑）
③ `deep-research-cli` 六步协议深度搜索，≤10次 web_search

### 2. 报告结构
```
📊 月度概览（抓取/推送量+源分布+5-8关键事件时间线）
🔥 热度Top10（heat_tracker跨源覆盖+热度分+趋势走向）
📰 各板块深度（每板块3-5事件，事件链→数据→影响→展望→置信度）
📈 趋势研判（跨域交叉+下月新兴话题）
📋 推送批次追溯（run_id清单）
```
完整模板见 `references/monthly-template.md`。

### 3. 信息茧房
引用 `blind_spot_audit.py --days 30`。汇总 `_serendipity: true` 到附录。

### 4. 格式
简报模板 → `trendradar-news-secretary` skill 的 news-format.md。无表格/引用/斜体。外文翻中文。每条至少1对立视角。零前置文本。

## 参考

| 文件 | 内容 |
|------|------|
| `references/monthly-template.md` | 完整模板 |
| `references/monthly-queries.md` | 聚合查询示例 |
| `references/aggregate-usage.md` | aggregate_monthly.py 指南 |
