---
name: weekly-report
slug: weekly-report
version: 2.2.0
description: 每周一推送深度趋势周报。五大板块+信息茧房突围，逐主题搜索验证。
author: Hermes Agent
metadata:
  hermes:
    tags: [weekly, research, trend, deep-dive]
    companion_skills: [multi-search-engine, deep-research-cli, monthly-report]
    platform_delivery: wecom
---

## 触发
cron 每周一 09:30（job `c20e2c82deda`），或手动。

## 核心规则

### 1. 依赖加载
加载 `multi-search-engine` → `deep-research-cli` → `weekly-report`（本 skill）。六步协议见 `deep-research-cli`。

### 2. 数据源
- `ls -lt ~/.hermes/trendradar/cache/raw_*.json` 本周 raw
- `~/.hermes/trendradar/data/curated_*.json` 精选结果
- 按板块归类趋势主题

### 3. 输出
模板见 `references/weekly-format.md`。不重复日报格式（无🆕🔥标记、无`[查看原文]`链接列表）。每主题 100-200 字，数据注来源。

### 4. 内容要求
每板块 3-5 主题。外文精确翻译。每主题：关键事件链→数据支撑→影响分析→展望→置信度(高/中/低+原因)→未覆盖 gap。

### 5. 验证
固定结论找矛盾点，每条至少 1 个对立视角。低可信源降权。

### 6. 信息茧房突围
固定板块「🌱 本周意外发现」：
- 从 curated JSON 提取 `_serendipity: true` 条目
- 分析反偏好内容，列 2-3 个平时低关注但本周值得注意的领域
- 建议是否调整兴趣配置
- 检查 `python3 scripts/blind_spot_audit.py --days 7` 输出

## 格式
简报格式和空行规范见 `references/render-format.md`。

## 参考

| 文件 | 内容 |
|------|------|
| `references/weekly-format.md` | 周报格式模板 |
| `references/render-format.md` | 简报格式规范 |
