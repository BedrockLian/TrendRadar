<!-- version: 2.8.0 | last-reviewed: 2026-05-26 -->

# ai_translate 翻译检测进化史

> ⚠️ **本文档记录了翻译检测的历史演进**。当前代码已不再使用硬编码 frozenset，
> 改为从 `sources.json` 的 `language` 字段动态加载（`_load_source_languages()`）。
> 最终方案见 `translation-pipeline-sync.md`。

## 背景

日语新闻（NHK、4Gamer 等）最初未被翻译。经过三次迭代才稳定。

## 迭代 1：CJK 比率启发式（失败）

`_is_cjk()` 用 `[0x3000, 0x9FFF]` 范围，把平假名(0x3040-0x309F)和片假名(0x30A0-0x30FF)算作 CJK。日语文本 CJK 比率约 90%，`is_english_summary()`（阈值 50%）返回 False → 跳过。

## 迭代 2：排除假名 + kana 检测（部分成功）

拆分 `_is_cjk()` 排除假名范围；新增 `_has_japanese_kana()` 和 `detect_source_lang()`。日语标题 CJK 降至 36-48%，大部分被正确标记。

**遗留问题**：汉字占比高的日语标题（如 `茂木外相 イラン外相と電話会談` → CJK 77%）仍被跳过。

## 迭代 3：来源平台固定分类（最终方案）

放弃内容启发式，按 `source_platform` 固定分类：

```python
_ENGLISH_SOURCES = frozenset([
    'bbc 商务', 'bbc 科技', 'bbc 商务+bbc 科技',
    'reuters', '路透社·商业', '路透社·科技', '路透社·中国',
    '路透社·商业+路透社·科技', '路透社·商业+路透社·中国', '路透社·科技+路透社·中国',
    'nytimes', '纽约时报·世界', '纽约时报·科技', '纽约时报·世界+纽约时报·科技',
    'guardian', '卫报·商务', '卫报·科技+卫报·商务',
    'techcrunch', 'ars technica', 'pc gamer',
    'nintendo everything', 'video games chronicle',
    'rock paper shotgun', 'eurogamer',
])

_JAPANESE_SOURCES = frozenset([
    'nhk', 'nhk ビジネス', '4gamer',
])
```

匹配逻辑：`any(kw in source_platform.lower() for kw in _JAPANESE_SOURCES)` → Japanese。未匹配任何列表 → 中文源，跳过。

## 同时修复的文件同步问题

`ai_translate.py` 和 `render_markdown.py` 的 curated JSON 文件读取优先级也必须一致：

- `ai_translate.py` 旧：读 `curated_{push_id}.json`（非日期版）→ 已有翻译→跳过
- `render_markdown.py` 读：`curated_{push_id}_{YYYYMMDD}.json`（日期版）→ 无翻译→原文
- 修复：统一先读日期版，fallback 到非日期版

`render_markdown.py` 也需读 `title_cn`/`summary_cn` 字段，而非只用原始 `title`/`summary`：

```python
# 旧
title = item.get('title')
# 新
title = item.get('title_cn') or item.get('title')
```

详见 `references/translation-pipeline-sync.md`。

## 验证

```bash
cd ~/.hermes/trendradar
PYTHONPATH=/home/asus/.hermes python3 scripts/ai_translate.py --push-id noon
python3 -c "
import json
d = json.load(open('data/curated_noon_$(date +%Y%m%d).json'))
for sec in d:
    if isinstance(d[sec], list):
        for item in d[sec]:
            cn = item.get('title_cn','')
            if cn: print(f'  ✅ [{sec}] {cn[:60]}')
"
```
