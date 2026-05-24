---
name: weekly-trend-report
slug: weekly-trend-report
version: 2.1.0
description: 每周一推送深度趋势周报。五大板块+信息茧房突围，逐主题搜索验证。
author: Hermes Agent
metadata:
  hermes:
    tags: [weekly, research, trend, deep-dive]
    data_dir: ~/.hermes/trendradar
    cache_dir: ~/.hermes/trendradar/cache
    scripts_dir: ~/.hermes/trendradar/scripts
    companion_skills:
      - multi-search-engine
      - deep-research-cli
      - monthly-trend-report
    platform_delivery: wecom
---

## 触发

cron 每周一 09:30，或用户要求时手动触发。

## 核心规则

### 1. 依赖加载
`multi-search-engine` → `deep-research-cli` → `weekly-trend-report`。方法协议(六步)见 `deep-research-cli`。

### 2. 数据源
- `ls -lt {data_dir}/cache/raw_*.json` 列本周 raw
- `{data_dir}/data/curated_*.json` 精选结果
- 按板块归类趋势主题

### 3. 输出
模板见 `references/weekly-format.md`。不重复日报格式（无🆕🔥标记、无`[查看原文]`链接列表）。每主题100-200字，数据注来源。

### 4. 内容要求
每板块3-5主题。外文精确翻译。每主题：关键事件链→数据支撑→影响分析→展望→置信度(高/中/低+原因)→未覆盖gap。

### 5. 验证
固定结论找矛盾点，每条至少1个对立视角。低可信源降权。

### 6. 信息茧房突围
固定板块「🌱 本周意外发现」：
- 从 curated JSON 提取 `_serendipity: true` 条目
- 分析反偏好内容，列2-3个平时低关注但本周值得注意的领域
- 建议是否调整兴趣配置
- 检查 `python3 scripts/blind_spot_audit.py --days 7` 输出

## 参考

| 文件 | 内容 |
|------|------|
| `references/weekly-format.md` | 周报格式模板 |
