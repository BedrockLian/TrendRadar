<!-- version: 2.8.0 | last-reviewed: 2026-05-26 -->

# 分类管线架构

## 双关键词集陷阱

| 位置 | 变量 | 作用 | 词数 |
|------|------|------|------|
| `fetch_feeds.py::_kw_sets()` | — | fetch 预分类 | ~130（子集） |
| `curate_and_push.py::_config()` | — | curate 主分类 | ~505（全集） |

`_preclassify()` 将 `_likely_domain` 写入 raw JSON。不同步则 raw JSON 大量 `other`。**改 `_kw()` 必须同步更新 `_kw_sets()`**。

## 分类管线（curate_all）

```
foreach item:
  1. foreign_china: src_is_foreign ∧ china_hit  → foreign_china
  2. gaming:       src∈GAME_SRC ∨ game_kw_hit  → gaming
  3. junk:         junk_kw_hit                  → _drop=True
  4. headline:     safety_kw ∨ politics_kw      → headline
  5. tech:         tech_kw_hit                  → tech
  6. economy:      economy_kw_hit               → economy
  7. 兜底（按源 category）:
     news    → headline
     game    → gaming
     tech    → tech
     economy → economy
     无匹配  → _drop=True
```

## 关键设计决策

**兜底路由**：`_all_source_category()` 函数按源 category 兜底。`news` 类别源（联合早报、澎湃等 12 个）→ `headline`，与 safety/politics 条目竞争 top-10。

**politics 特殊处理**：124 词命中后路由到 `headline`，但 **不在** `_kw_sets()` 中——fetch 预分类标记为 `other`，curate 阶段由 politics 关键词正确路由。不要把 politics 词加到 economy 集。

## 源覆盖审计误判

`blind_spot_audit.py` 只看 curated JSON。MAX_PER_DOMAIN 导致活跃源在 curated 零出现但 raw 正常。**真死源 = raw 为零**。2026-05-21 审计：报告 18 死源 → 实际 4 真死源（已删），35 源存活。

## 关键词规模

| domain | 中文 | 英文 | 日文 | 总计 |
|--------|------|------|------|------|
| game | 34 | 58 | 39 | 131 |
| tech | 39 | 48 | 0 | 87 |
| economy | 59 | 35 | 0 | 94 |
| politics | 63 | 61 | 0 | 124 |
| safety | 31 | 0 | 0 | 31 |

详细词表见 `keyword-architecture.md`。

## 相关文件

- `curate_and_push.py` — `_kw()`, `_all_source_category()`, `curate_all()`
- `fetch_feeds.py` — `_kw_sets()`, `_preclassify()`
- `blind_spot_audit.py` — 源覆盖率审计
- `diversity_injector.py` — 反偏好注入
- `classification-traps.md` — 已知分类陷阱（游戏源 vs 外媒看华冲突）
