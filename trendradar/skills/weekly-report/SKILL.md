---
name: weekly-report
slug: weekly-report
version: 2.4.0
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
模板见 `references/PIPELINE.md  # was weekly-format → pipeline`。不重复日报格式（无🆕🔥标记）。

**格式铁律（与 render_markdown.py 格式契约一致）：**
- 全文不允许使用 `---` 或 `***` 横线分隔线
- 板块标题后跟双空行（`\n\n\n`）
- 主题之间用双空行（`\n\n\n`）分隔
- 主题内部用单空行（`\n\n`）分隔段落
- 不要用「查看原文」链接，来源直接在文本中标注（如[路透社]）
- 禁止 LLM 重写格式——严格按模板输出

每主题 100-200 字，数据注来源。

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

### 7. 常见陷阱

**格式违规**：Agent 自行添加 `---` 横线分隔板块、输出长篇散文而非结构化列表。
**修复**：cron prompt 已包含格式铁律，agent 必须严格遵守 weekly-format.md 模板。
**不得**在分析前后加 `---`、`***` 或类似分隔符——板块间用双空行即可。

**深度分析格式**：深度分析是结构化趋势研判，不是新闻综述或散文。
每主题必须包含：事件链→数据支撑→影响分析→展望→置信度→未覆盖gap。
来源在文本中标注（如[路透社]），不要用「查看原文」链接。

## 格式
简报格式和空行规范见 `references/PIPELINE.md  # was render-format → pipeline`。周报独立模板见 `references/PIPELINE.md  # was weekly-format → pipeline`。

## Cron prompt 注意事项
cron prompt 独立于 skill 内容，修改 weekly-report skill 后必须单独更新 cron prompt：
`cronjob action=update job_id=c20e2c82deda prompt="..."`

当前 cron prompt 已包含格式铁律（无 `---`、双空行间距、来源内联标注）。更新 skill 后需同步 prompt。

## 参考

| 文件 | 内容 |
|------|------|
| `references/PIPELINE.md  # was weekly-format → pipeline` | 周报格式模板 + 格式铁律 |
| `references/PIPELINE.md  # was render-format → pipeline` | 简报格式规范 |
