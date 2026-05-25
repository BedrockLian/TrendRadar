# 翻译管线：同步与检测

## 核心规则

### 1. 来源平台检测（来自 sources.json）

2026-05-25: `language` 字段嵌入 `data/sources.json` 每个源条目，`ai_translate.py` 启动时读取并按 language 提取 `platform` + `name` 做子串匹配。

```python
# sources.json 条目示例
{"name": "BBC 商务", "platform": "bbc", "language": "en", ...}
```

**单真相源**：加新源只需修改 `data/sources.json`（加 RSS 条目 + 设 `language` 字段），不再维护独立语言映射文件。

匹配规则：`name` + `platform` 两字段都参与匹配，`bbc` 匹配 `BBC 商务`/`BBC 科技`/`BBC 商务+BBC 科技` 等。

### 2. 文件优先级（关键陷阱）

`ai_translate.py` 和 `render_markdown.py` 的 `_load_and_scan` 必须读取**同一文件**。

**优先级规则**（两者一致）:
1. 先尝试日期版: `curated_{push_id}_{YYYYMMDD}.json`
2. 回退到非日期版: `curated_{push_id}.json`

**陷阱**: 2026-05-24 发现 ai_translate 读非日期版（已有 title_cn→跳过），render_markdown 读日期版（无 title_cn→原文输出）。两者读取倒序导致翻译存在却不可见。

### 3. render_markdown 优先使用翻译字段

```python
title = _shorten(item.get('title_cn') or item.get('title') or '', 80)
summary = _shorten(item.get('summary_cn') or item.get('summary') or '', 150)
```

总是先取 `title_cn`/`summary_cn`（翻译结果），不存在时 fallback 到原始 title/summary。

### 4. items_to_translate tuple 格式

`needs_title` / `needs_summary` 由 `bool(source_lang)` 驱动，不再靠 CJK 比率。

```python
source_lang = get_source_lang(item.get('source_platform', ''))
needs_title = not has_title_cn and title and bool(source_lang)
needs_summary = not has_summary_cn and summary and bool(source_lang)

items_to_translate.append((
    domain, idx, item, title, summary,
    needs_title, needs_summary,
    source_lang  # 'English' | 'Japanese' | None
))
```

第8个元素 `source_lang` 必须存在，供 `_batch_translate_all` 读取传给 prompt。
