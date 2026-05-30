---
name: report-generator
slug: report-generator
version: 1.0.0
description: 周/月度趋势深度报告。五大板块+信息茧房突围，逐主题搜索验证。
author: Hermes Agent
metadata:
  hermes:
    tags: [report, research, trend, deep-dive, weekly, monthly]
    companion_skills: [multi-search-engine, deep-research-cli]
    platform_delivery: wecom
---

## 触发
- **周报**: cron 每周一 09:30 (job `c20e2c82deda`)，或手动
- **月报**: cron 每月 1 日 09:00 (job `0b14c67429ba`)，或手动

## 数据源

**周报**: `ls -lt ~/.hermes/trendradar/cache/raw_*.json` + `data/curated_*.json`，按板块归类趋势。

**月报（三层聚合）**:
① 近 4 周周报（叙事骨架）
② `scripts/aggregate_monthly.py --days 32 --suggest-interests`（量化统计 + 兴趣漂移检测）
③ `deep-research-cli` 六步协议深度搜索，≤10 次 web_search

## 核心规则

1. **依赖**: 加载 `multi-search-engine` → `deep-research-cli` → `report-generator`。协议见 `deep-research-cli`。
2. **每主题**: 事件链→数据支撑→影响分析→展望→置信度(高/中/低+原因)→未覆盖gap。外文精确翻译，来源内联标注（如[路透社]）。每主题 100-200 字。
3. **验证**: 固定结论找矛盾点，每条至少 1 个对立视角。低可信源降权。
4. **信息茧房突围**:
   - 提取 curated JSON 中 `_serendipity: true` 条目
   - 列 2-3 个低关注但本周值得注意的领域
   - 建议是否调整兴趣配置
   - 周报: `scripts/blind_spot_audit.py --days 7`；月报: `--days 30`

## 输出结构

**周报** — 5 板块 + 意外发现，3-5 主题/板块。不重复日报格式（无🆕🔥标记）：
```
### Hermes趋势周报 · YYYY/MM/DD - YYYY/MM/DD
📰 本周头条趋势 → 🌏 外媒看华趋势 → 🚀 科技数码趋势
📊 民生经济趋势 → 🎮 游戏市场趋势 → 📝 本周总结 → 🌱 本周意外发现
```

**月报** — 概览 + Top 10 + 板块深度 + 趋势 + 追溯：
```
📊 月度概览（抓取/推送量+源分布+关键事件时间线）
🔥 热度Top10（跨源覆盖+热度分+趋势走向）
📰 各板块深度 → 📈 趋势研判（跨域交叉+下月新兴话题）
📋 推送批次追溯（run_id清单）→ 🌱 信息茧房附录
```

## 格式铁律
- 全文无 `---`/`***` 横线，板块间双空行
- 主题间双空行，主题内单空行
- 来源内联标注，不用「查看原文」链接
- 禁止 LLM 重写格式——严格按模板输出
- 完整模板+空行规范见 `references/report-templates.md`

## Cron 同步
修改 skill 后必须同步 cron prompt：
- 周报: `cronjob action=update job_id=c20e2c82deda prompt="..."`
- 月报: `cronjob action=update job_id=0b14c67429ba prompt="..."`

## 参考

| 文件 | 内容 |
|------|------|
| `references/report-templates.md` | 周报+月报格式模板 & 空行规范 |
| `../../references/PIPELINE.md` | 管线流程 + 渲染格式规范 |
