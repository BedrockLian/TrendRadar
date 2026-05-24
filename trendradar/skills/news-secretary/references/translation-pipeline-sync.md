# 翻译管线同步问题

## 问题：翻译存在但渲染时丢失

当用户反馈「没翻译」时，先检查 curated JSON 中是否有 `title_cn`/`summary_cn` 字段。

### 检查步骤

```bash
cd ~/.hermes/trendradar
python3 -c "
import json
d = json.load(open('data/curated_noon.json'))
# 检查 foreign_china 等域是否有 title_cn
for sec in ['top_headlines','foreign_china','tech','economy','gaming']:
    for item in d.get(sec,[]):
        src = item.get('source_platform','')
        cn = item.get('title_cn','')
        if 'bbc' in src.lower() or 'reuters' in src.lower() or 'nhk' in src.lower():
            print(f\"  {'✅' if cn else '❌'} [{src}] {cn[:60] if cn else item.get('title','')[:60]}\")
            break
"
```

## 陷阱 31：render_markdown.py 不读 title_cn/summary_cn

**问题**：`ai_translate.py` 正确将翻译写入 `title_cn`/`summary_cn` 字段，但 `render_markdown.py` 的 `_format_item()` 只读 `item.get('title')` 和 `item.get('summary')`，忽略翻译字段。

**表现**：curated JSON 中有 `title_cn`（✅ 有翻译），但渲染后的 Markdown 仍显示原文（❌ 没翻译）。

**修复**（`_format_item()` 函数内）：

```python
# 旧（原文优先）：
title = _shorten(item.get('title') or '', 80)
summary = _shorten(item.get('summary') or '', 150)

# 新（翻译优先）：
title = _shorten(item.get('title_cn') or item.get('title') or '', 80)
summary = _shorten(item.get('summary_cn') or item.get('summary') or '', 150)
```

## 陷阱 32：ai_translate 与 render_markdown 文件读取优先级不一致

**问题**：每天 pipeline 运行时会生成两个 curated 文件：
- `curated_noon.json`（非日期版，先创建）
- `curated_noon_20260524.json`（日期版，后创建）

旧版 `ai_translate.py` 的 `_load_and_scan()` 优先读非日期版，而 `render_markdown.py` 优先读日期版。当重新跑 pipeline 时：
1. `push_prepare.py` 新建日期版（无翻译）
2. `ai_translate.py` 读非日期版（已有翻译）→ 跳过
3. `render_markdown.py` 读日期版（无翻译）→ 原文输出

**表现**：`cat curated_noon.json | grep title_cn` 有翻译结果，但简报仍是原文。

**修复**：两者都优先读日期版，fallback 到非日期版。

```python
# ai_translate.py _load_and_scan():
today_file = datetime.now(CST).strftime('%Y%m%d')
curated_path = DATA_DIR / f'curated_{push_id}_{today_file}.json'
if not curated_path.exists():
    curated_path = DATA_DIR / f'curated_{push_id}.json'

# render_markdown.py main() — 已用相同逻辑
today_file = datetime.now(CST).strftime('%Y%m%d')
curated_path = DATA_DIR / f'curated_{push_id}_{today_file}.json'
if not curated_path.exists():
    curated_path = DATA_DIR / f'curated_{push_id}.json'
```

## 陷阱 33：ai_translate 内容启发式检测不可靠

**问题**：早期版本用 CJK 比率 < 50% 判断是否需要翻译。即使修复了 kana 排除问题，仍对以下情况失效：
- 汉字占比高的日语标题（如 `茂木外相 イラン外相と電話会談` → CJK 77% → 被跳过）
- 含英文专有名词的中文标题（如 `SpaceX抢跑，OpenAI追击` → CJK < 50% → 被标记翻译）

**修复**：改为按来源平台（`source_platform`）固定分类。

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

匹配逻辑：`any(kw in source_platform.lower() for kw in _JAPANESE_SOURCES)` → Japanese。English 同理。未匹配 → 中文源，跳过翻译。

### 验证

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
            if cn: print(f\"  ✅ [{sec}] {cn[:60]}\")
"
```
