# foreign_china 域扩展指南

> 晚间推送中外媒中国报道分类不足时，通过扩充源列表和关键词提升覆盖。

## 分类逻辑

`curate_and_push.py` 的 `_classify_items()` 将条目归入 `foreign_china` 需同时满足两个条件：

1. **`src_is_foreign`** — `source_platform` 包含 `_foreign_sources()` 中的任意名称
2. **`china_hit`** — 标题或摘要包含 `_china_kw()` 中的任意关键词
3. **不是游戏源**

## 扩展源列表

### `_foreign_sources()`

位于 `scripts/curate_and_push.py` 第 51-55 行。

```python
def _foreign_sources() -> frozenset:
    return frozenset(s['name'].lower() for s in _sources()
                     if s.get('authority', 1) >= 2 and s.get('platform') in (...))
```

**匹配机制**：返回 source NAME 的 frozenset（如 `"南华早报"`、`"Japan Times"`）。`_classify_items` 用 `any(fs in source_platform.lower() for fs in FOREIGN)` 做子串匹配。

**添加新平台**：在 `s.get('platform') in (...)` 的元组中加入新平台的 `platform` 字段值（来自 `sources.json`）。同时确保该源 `authority >= 2`。

2026-05-28 新增的平台：

| 平台值 | 对应 NAME | 权威分 |
|--------|-----------|--------|
| `guardian` | 卫报·科技、卫报·商务 | 3 |
| `scmp` | 南华早报 | 3 |
| `nikkei` | 日经亚洲 | 3 |
| `japantimes` | Japan Times | 2 |
| `koreaherald` | Korea Herald | 3 |
| `npr` | NPR 国际/商务/科技 | 3 |

## 扩展关键词

### `_china_kw()`

位于 `scripts/curate_and_push.py` 第 128-138 行。返回 frozenset，匹配时做 `kw.lower() in text.lower()` 子串匹配。

**添加新关键词时**：确保是英文外媒文章中真正频繁出现且能唯一指向中国话题的词。避免过于通用的词汇（如 `"trade"` 会命中全球贸易文章）。

2026-05-28 新增的关键词分类：

| 类别 | 新增词 |
|------|--------|
| 地理 | `Macau`, `South China Sea`, `Xinjiang`, `Tibet` |
| 贸易/制裁 | `trade deficit`, `tariff`, `technology war`, `chip ban`, `AI ban`, `overcapacity` |
| 机构 | `foreign ministry`, `CPTPP`, `Belt and Road` |
| 公司 | `字节跳动`, `小红书`, `DeepSeek`, `百度`, `小米`, `中兴`, `中芯`, `中石油`, `中石化`, `工商银行` |
| 财经 | `中概股`, `renminbi`, `Chinese stocks`, `China market` |
| 产业 | `EVs`, `electric vehicle` |

## 验证方法

修改后必须用真实 `source_platform` 值测试：

```python
from scripts.curate_and_push import _foreign_sources, _china_kw

fs = _foreign_sources()
ck = _china_kw()

# 用真实的 source_platform 值（来自 sources.json 的 name 字段）
test_cases = [
    ('南华早报', 'China hits back at US tariff hikes'),
    ('卫报·科技', 'ByteDance faces new AI chip ban'),
    ('日经亚洲', 'South China Sea tensions rise'),
    ('Japan Times', 'Sino-Japanese trade talks resume'),
    ('Korea Herald', 'Chinese overcapacity challenges'),
    ('NPR 国际', 'Tibet autonomy under threat'),
]

for src, title in test_cases:
    plat_lower = src.lower()
    src_is_foreign = any(fs in plat_lower for fs in fs)
    china_hit = any(k.lower() in title.lower() for k in ck)
    result = '✅' if (src_is_foreign and china_hit) else '❌'
    print(f'{src:15s} | {src_is_foreign} {china_hit} | {result}')
```

**注意**：`source_platform` 在 curated JSON 中是 `sources.json` 的 `name` 字段值（如 `"南华早报"`），不是 `platform` 字段值（如 `"scmp"`）。测试时用 name。
