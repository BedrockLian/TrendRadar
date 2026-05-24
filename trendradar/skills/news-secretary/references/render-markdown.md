# render_markdown.py — 纯脚本渲染器

## 位置
`/home/asus/.hermes/trendradar/scripts/render_markdown.py`

## 用途
替代 `render_briefing.py`（已删除），从 curated JSON 直接拼接 Markdown 简报。
**cron 引用必须用此脚本名**，不可回退到已删除的旧名。

## 优点
- **速度**：~0s（vs LLM ~9s）
- **成本**：零 token（vs LLM 消耗 API）
- **格式**：100% 一致，无 LLM 输出漂移
- **摘要截断**：150 字上限，句号边界智能切分（`_shorten()`）

## 用法
```bash
cd /home/asus/.hermes/trendradar
/usr/local/bin/python3.14t scripts/render_markdown.py --push-id evening 2>/dev/null
```
stdout = 完整 Markdown 简报，兼容 `fragment_push.py`。

## 格式铁律（自动保证）
| 位置 | 空行 | 示例 |
|------|------|------|
| 标题 ↔ 摘要 | `\n\n` | `标题\n\n摘要` |
| 摘要 ↔ 链接 | `\n\n` | `摘要\n\n[查看原文]()【源】` |
| 条目之间 | `\n\n\n` | `【源】\n\n\n🆕 N. **标题**` |
| 板块标题后 | `\n\n\n` | `### 📰 头条\n\n\n🆕` |

## 数据结构（关键！）

curated JSON 的结构是 **domain→items 映射**，不是扁平列表：

```python
{
  "top_headlines": [{item_dict}, ...],
  "foreign_china": [{item_dict}, ...],
  "tech": [{item_dict}, ...],
  "economy": [{item_dict}, ...],
  "gaming": [{item_dict}, ...],
  "total": 54,
  "push_id": "morning",
  ...
}
```

脚本的 `main()` 直接按 `DOMAINS` 顺序遍历 data[domain]，不是通过 `data.get('items', data)` 取扁平列表。

## 文件命名规则（常见陷阱）

- **curated 文件**：`curated_{push_id}_{YYYYMMDD}.json`（无连字符）
- **显示日期**：`2026-05-24`（带连字符，用于标题正文）
- **fallback**：无日期后缀时读 `curated_{push_id}.json`
- 脚本中用两个变量区分：`today_file`（文件路径用）、`today_display`（展示用）

## _heat 字段结构

`_heat` 是 **dict** 不是 int，含以下键：

```python
{
  "appearances": int,      # 出现次数，>=2 → 🔥
  "heat_score": float,     # 热度评分 0-1，>=0.8 → 🔥
  "is_new": bool,
  "is_sustained": bool,
  "trend": "new"|"rising"|"stable",
  "fingerprint": str,
  "platforms": [str, ...],
  "span_hours": float
}
```

### emoji 判定逻辑
```python
if heat_value:
    if isinstance(heat_value, dict):
        if appearances >= 2:  → 🔥
        if heat_score >= 0.8: → 🔥
    elif isinstance(heat_value, (int, float)) and heat_value >= 2: → 🔥
return 🆕  # 默认
```

## 各函数职责

| 函数 | 职责 |
|------|------|
| `_detect_emoji()` | 根据 _heat / _track 判断 🔥🔄🆕 |
| `_format_item()` | 单条目 3 行：标题 → 摘要 → 链接 |
| `_generate_section()` | 板块头＋条目列表，`\n\n\n` 拼接 |
| `_shorten()` | 截断至 max_len，句号边界优先切分 |
| `main()` | 加载 curated JSON → 遍历 DOMAINS → 组装 header + sections + footer |
