# Source Management (RSS源管理)

## 新增源流程

1. 用户提供源名 + RSS URL + 板块分类
2. 测试连通性：`curl -sL --proxy http://127.0.0.1:7890 <URL>` 验证 200 + XML
3. 写入 `config/sources.json`，按 schema 填字段
4. 同步双副本：
   ```bash
   cp ~/.hermes/trendradar/trendradar/config/sources.json \
      ~/TrendRadar/trendradar/config/sources.json
   ```
5. 若为外媒（en/ja），确认 `_foreign_sources()` 平台名单已包含该源
6. git commit + push

## 源 Schema

```json
{
  "id": "唯一标识",
  "name": "显示名称（也是 source_platform 值）",
  "platform": "平台简称（用于 _authority() 匹配）",
  "type": "rss",
  "category": "tech|news|game|economy|foreign_china",
  "enabled": true,
  "feed_url": "RSS URL",
  "authority": "3(高)|2(中)|1(低)",
  "language": "zh|en|ja"
}
```

### 可选字段（2026-06-05 扩展）

- `priority`: `0`(P0 首位+120字摘要) / `1`(P1 次位+100字) / `2`(P2 末尾仅标题)。详见 SKILL.md「优先级排版系统」
- `freshness_days`: 覆盖全局 `RSS_FRESHNESS_MAX_AGE_DAYS=1`。日更源（WSJ 商业、CNBC Finance）需 `2` 才不饿死；Google News 替代源需 `3` 容纳 2-3 天滞后
- `needs_proxy`: 布尔值（`true`/`false`）。**显式覆盖 URL 模式匹配**——优先级最高。例如 CNBC Finance 直连 TimeoutError（中国 IP 被拒），设 `true` 强制走代理，避免改 `DOMESTIC_PROXY_PATTERNS` 全局列表的副作用

## 权威分（authority）三档

- **3(高)** — 核心信源，行业标杆或顶级科学期刊
- **2(中)** — 优质垂直媒体或权威综合媒体的子频道
- **1(低)** — 长尾补充，覆盖面窄或更新量少

用户提供权重表时的典型模式：
```
权重,媒体名称
高,"Bloomberg, Financial Times"
中,"纽约时报·商务, NPR 商务"
低,"NHK 商业, NHK 经济"
```

## 外媒注册

外媒源（en/ja）需要在 `_foreign_sources()`（`scripts/domain_metadata.py`，**不是** `curate_and_push.py`）的 platform 白名单中添加其 `platform` 值，否则涉华文章不会被分入 `foreign_china` 域。

**⚠️ 漏加白名单的后果（2026-06-23 Foreign Affairs 案例）**：

Foreign Affairs 在 `sources.json` 中有 `category: "foreign_china"`，但 `platform: "foreignaffairs"` **不在白名单内**。结果：

1. `classifier.py` 第 29 行 `src_is_foreign = False` → 不进 `foreign_china`
2. 标题/摘要关键词（"How to Survive the AI Shock"）不命中任何 domain 关键字集（GAME_KW、TECH_KW、ECONOMY_KW 均无 "AI"）
3. 兜底路由走到 `ALL_SRC_CAT["Foreign Affairs"] = "foreign_china"`，但 `foreign_china` 不在路由表内
4. `_likely_domain` 保住了 fetch 阶段的 `top_headlines`，但后续 curation 中某些 `top_headlines` 项被合并/冲进了 `gaming`
5. 最终表现：🎮 游戏板块出现 Foreign Affairs 的 AI 政策文章

**修复**：在 `_foreign_sources()` 白名单中添加 `'foreignaffairs'`。修改后新抓取的首批文章会被正确路由到 `foreign_china`（涉及中国）或经后续分类到 `top_headlines`（不涉华政策/科技类）。

**加源铁律**：每新增一个 en/ja 源，**必须在 `_foreign_sources()` 白名单中也加对应的 `platform` 值**，否则即使 `category: "foreign_china"` 也路由不到正确域。

```python
def _foreign_sources() -> frozenset:
    return frozenset(s['name'].lower() for s in _sources()
                     if s.get('authority', 1) >= 2 and s.get('platform') in (
        'reuters', 'bbc', 'nytimes', 'scmp', 'nikkei',
        'foreignpolicy', 'foreignaffairs',  # ← Foreign Affairs 需手动加入
        ...
    ))
```

当前白名单完整值（`scripts/domain_metadata.py` 第 125-134 行）：
```python
'reuters', 'bbc', 'nytimes', 'arstechnica', 'techcrunch', 'nhk',
'VideoGamesChronicle', 'PCGamer', 'Eurogamer', 'RockPaperShotgun',
'GamersNexus', 'nintendoeverything', 'aftermath', 'automaton',
'guardian', 'scmp', 'nikkei', 'japantimes', 'koreaherald', 'npr',
'bloomberg', 'ft', 'wsj', 'apnews', 'aljazeera', 'economist',
'technologyreview', 'nature',
'restofworld', 'sixthtone', 'foreignpolicy', 'straitstimes',
'scmp_china',
# ↑ 'foreignaffairs' 不在这里 → 高权威(3)外媒路由失败
```

## 当前源列表（2026-06-05，43 个活动源，含 2 条新增替代）

```
💻 科学/技术 (14)
  3  MIT Technology Review · Wired · Nature News · Science News · The Decoder
  2  Ars Technica · TechCrunch · The Verge · 纽约时报·科学 · 纽约时报·科技
     VentureBeat · 量子位 · AI 前线 (InfoQ)   ← 2026-06-05 新增（替代机器之心）

📰 头条 (8)
  3  纽约时报·世界 · 南华早报 · AP News · Al Jazeera
  2  界面新闻 · 澎湃新闻 · 联合早报·中国 · 联合早报·国际

🎮 游戏 (9)
  3  GamesIndustry.biz · Video Games Chronicle · Eurogamer · Game Developer
  2  机核 · PC Gamer · Rock Paper Shotgun · The Verge·游戏 · Aftermath

📊 经济 (6)
  3  Bloomberg · Reuters · Financial Times · WSJ 世界新闻 · CNBC 财经   ← 2026-06-05 新增（替代 WSJ 商业）
  2  纽约时报·商务

🌏 国际/外媒看华 (7)
  3  BBC 中国 · BBC 世界 · NPR 国际 · SCMP 中国 · Nikkei Asia · **Foreign Affairs**   ← 2026-06-23 修复白名单
  2  Sixth Tone · Foreign Policy
```

**已删除源**（2026-06-05）：
- **WSJ 商业** — `feeds.a.dj.com/rss/WSJcomUSBusiness.xml` 自 2025-01-24 停更。Google News 替代变体（`intitle:business`）返 2019 旧文不可用。**完全删除**而非 `enabled: false`，因为：(1) 已有 CNBC 财经 P0/P1 替代；(2) 保留 entry 只会让未来 session 在 sources list 里看到一条 0 items 的死源（增加心智负担）。
- **机器之心** — `jiqizhixin.com/rss` 改版后跳 `/data-service` SPA 页面（返 HTML 而非 XML），`/articles/feed` 同样。**完全删除**，由 AI 前线 (InfoQ) 替代。

## 死源处理：删除 vs 禁用（2026-06-05 用户决策）

两种处理模式：

| 模式 | 适用场景 | 优点 | 缺点 |
|------|---------|------|------|
| **`enabled: false` + `_comment`** | 源有复活可能 / 替代源未验证 / 想保留历史 | 立即可恢复（改 enabled） | sources list 留有 0 items 死源，agent 看到会困惑 |
| **完全删除 entry** | 已有验证过的替代源 / 源已停更 ≥6 个月 / 源被网站永久关闭 | sources list 干净；git history 可回滚 | 恢复需重新查 feed_url |

**用户偏好**（2026-06-05）：**能用 feedparser 验证 + 至少 1 条替代源就绪时，倾向完全删除**。本 session 删除了 WSJ 商业 + 机器之心，因 CNBC Finance（6 条/天）和 AI 前线（17 条/天）已验证替代。

**何时保留 disabled**：源状态不明（如某 feed 偶尔 200 偶尔 502 抽风），或尚无验证过的替代源（避免真空）。

## 源清理历史（2026-05-31）

### 第一轮（71→50）: 清理"二道贩子"和"通稿搬运工"

**💻 科学/技术**: 删钛媒体、爱范儿、虎嗅（消费快讯，非深度）；BBC科技/科学环境、卫报科技、NPR科技、NHK科学医疗（副刊，信息差小）
**📰 头条**: 删法广、共同网、NHK政治、Korea Herald（译文源，有AP/Reuters无需二次加工）；Japan Times（Nikkei Asia已覆盖）
**🎮 游戏**: 删IGN（流量工厂）、Pocket Gamer/Nintendo Everything（垂直源，综合媒体已覆盖）；Automaton West/Inside Games/4Gamer（不懂日语不追求秒级更新）；GameLook（软文重）
**📊 经济**: 删NHK商业/经济、NPR商务、BBC商务（非专业财经，反应慢于Bloomberg/Reuters）
**🌏 国际**: 删The Straits Times（SCMP+Nikkei Asia已覆盖）

### 第二轮（50→45）: 按同源硬上限验证后清理
**📰 头条**: 删Japan Times
**🎮 游戏**: 删Nintendo Everything、Automaton West、Inside Games、4Gamer

### 第三轮（45→43）: 删除国内快讯源
**💻 科学/技术**: 删36氪（低质快讯）
**🎮 游戏**: 删触乐（中文游戏独立，用户认为不需要）

## 死源判定标准

- HTTP 403/404 → 检查 URL 是否过期
- TLS `unexpected eof` / HTTP 502 → CDN 地理封锁（Akamai/Cloudflare）
  - 尝试 Google News RSS 替代：`news.google.com/rss/search?q=site:bbc.com`
- 000 timeout → 代理或网络不可达
- `plink.anyfeeder.com/xxx` 404 → AnyFeeder 未配置该源

## ⚠️ "HTTP 200 但 0 items" = 上游 feed 已死（2026-06-05 实战教训）

**症状**：fetch 走完后某源仍 0 items。降级重试 HTTP 200 成功，但 `_parse_rss` 返 0 条 → 整源 0 items。

**根因（与"失联"不同）**：上游 feed 本身**已停更或网站改版关闭 RSS**。不是网络问题，不是反爬，是 RSS feed 死了。

**两类典型死亡模式**：

### A. feed 停更（HTTP 200 + XML 仍合法 + 但内容是几个月前）
例：`feeds.a.dj.com/rss/WSJcomUSBusiness.xml` 自 **2025-01-24** 起停更。feedparser 解析 20 条全 `published=2025-01-24` → freshness 过滤清空 → 源返 0 items。

**信号**：`entries > 0` 但所有 `published_parsed` 都早于 freshness 窗口。

### B. 网站改版关闭 RSS（HTTP 200 + 返 HTML SPA 而非 XML）
例：`https://www.jiqizhixin.com/rss` 改版后跳到 `/data-service` SPA 页面。feedparser 解析 0 entries。`/articles/feed` 同样返 HTML。

**信号**：`entries == 0` + `bozo == True` + `bozo_exception` 含 "not well-formed" 或 "no items"。

**⚠️ 必做的诊断命令**（**改 sources.json 前必须先跑**）：
```python
import feedparser
d = feedparser.parse('<URL>')
print('entries:', len(d.entries), '  bozo:', d.get('bozo'))
print('bozo_exception:', str(d.get('bozo_exception',''))[:100])
for e in d.entries[:3]:
    print('  -', e.get('title','?')[:60])
    print('    pub:', e.get('published','?')[:25])
```

**判定决策树**：
- `len(entries) == 0` → 网站改版/关闭 RSS → `enabled: false`（除非有 Google News 替代且验证过）
- `len(entries) > 0` 但 `published` 全部是几个月前 → feed 停更 → `enabled: false`
- `len(entries) > 0` 且 `published` 是近期 → fetch 内部问题（重试/降级），**不是源问题**

**Google News 替代验证**（不一定有效）：
```bash
# 试多个变体，看哪个返新文
for q in 'source:Wall+Street+Journal' 'site:wsj.com' 'site:wsj.com+intitle:business'; do
  curl -sL --proxy http://127.0.0.1:7890 "https://news.google.com/rss/search?q=$q+when:1d&hl=en-US&gl=US&ceid=US:en" | python3 -c "
import feedparser, sys
d = feedparser.parse(sys.stdin.read())
print('  $q: entries=', len(d.entries))
for e in d.entries[:2]:
    print('    pub:', e.get('published','?')[:20])
"
done
```

**踩坑**：Google News `intitle:` 操作符有时会让结果混入**几年前**的旧文（Google 内部索引异常）。`site:` 配合 `when:1d` 通常最稳。**任何替代源上线前必须 feedparser 验证最近 3 条 `published` 是近 7 天内**。

**保存源信息**：如选禁用而非删除，**保留源信息**：`enabled: false` + `_comment` 写明停更时间和替代方案，方便以后观察 RSS 复活。

## 5-run 稳定性验证（2026-06-05 新增源铁律）

**问题**：新增一个 RSS 源后，单次 fetch 报"成功"不代表它真稳。CNBC Finance 单测 30 条 OK，5 次连续 fetch 仍 0 条——是 mihomo 节点抽风 + per-source `needs_proxy` 标记首次生效时 fetch 调度路径不同的组合假象。

**铁律**：新加源后**必须跑 5 次连续 fetch**，看 (a) 命中率稳定 / (b) 抓取数稳定 / (c) 不挤压其他源（fetch 总时长无明显恶化）。

```bash
cd ~/.hermes/trendradar
for i in 1 2 3 4 5; do
  rm -f cache/raw_$(date +%Y%m%d).json
  $PYTHON -c "
import asyncio
from trendradar.scripts.fetch_feeds import fetch_all
r = asyncio.run(fetch_all('evening'))
ps = r['platform_stats']
new_src = ps.get('<新源 name>', 0)
ok = sum(1 for v in ps.values() if v)
print(f'Run $i: items={len(r[\"items\"])} ok={ok}/<N>  <新源>={new_src}')
" 2>&1 | grep "^Run"
done
```

**判定**：
- 5/5 命中且抓取数方差 < 30% → 加源成功
- 4/5 命中 → 降级到 `enabled: false`，等待 mihomo 节点稳定后重试
- <3/5 命中 → 撤回新源（git revert 或手动从 sources.json 删），找其他候选

**陷阱**：本 session 第 1 次跑 5 轮全 CNBC=0/InfoQ=0，第 2 次重跑 5 轮全 6/17。区别是**节点状态**——mihomo URLTest 组每隔 5 min 自动切节点，切完稳定 5-10 min。如果首次跑 mihomo 正处于切换窗口，结果会假阴性。

**速查：诊断"假 0"还是"真 0"**：
```python
# 单源 vs batch 抓取结果对比
import asyncio, aiohttp, feedparser
async def main():
    async with aiohttp.ClientSession(headers={'User-Agent':'Reeder/5.2 MacOSX'}) as s:
        # 直连测
        for proxy in [None, 'http://127.0.0.1:7890']:
            kw = {'proxy': proxy} if proxy else {}
            kw['timeout'] = aiohttp.ClientTimeout(total=6)
            try:
                async with s.get('<URL>', **kw) as r:
                    body = await r.text()
                    d = feedparser.parse(body)
                    print(f'  proxy={proxy!s:6s}  HTTP={r.status}  entries={len(d.entries)}  body={len(body)}B')
            except Exception as e:
                print(f'  proxy={proxy!s:6s}  FAIL {type(e).__name__}: {str(e)[:50]}')
asyncio.run(main())
```

- 单源直连 OK → 走代理 OK → batch 内 0 items → 必是 mihomo 节点瞬间抽风
- 单源直连 OK → 走代理 OK → batch 内 N items → 真 0 items（freshness/分类问题）

## User-Agent 选择（2026-06-05 WSJ CDN 验证）

`fetch_feeds.py` 全局 `USER_AGENT` 选 `Reeder/5.2 MacOSX` 优于浏览器 UA：
- 浏览器 UA（`Mozilla/5.0 (Windows NT 10.0; Win64; x64)` 等）会被 RSS CDN 识别为人类浏览器，触发严格限速/反爬
- RSS 阅读器 UA（Reeder / NetNewsWire / Inoreader / Feedbin）通常在 CDN 白名单内，**不被限速**

**WSJ 实测**：`feeds.a.dj.com` 对浏览器 UA 限速 15s/req（多次 8s 超时），`Reeder/5.2 MacOSX` / `NetNewsWire/6.1.1` / `Reeder/5.2 MacOSX` 全部 0.7-1.5s 200。Googlebot UA 也通但不应使用（滥用）。

**适用范围**：所有 RSS 抓取场景。换 UA 是无副作用的全局优化（对 BBC/Reuters/Bloomberg/澎湃/联合早报等所有验证过的源都无负面影响），不是 WSJ 特例。

**何时不换**：抓 RSSHub 等代理服务时保留浏览器 UA（避免 RSSHub 反向反爬）。

## "RSS 拉得到但精选 0%" 诊断（2026-06-03 Nikkei 案例）

**症状**：源 RSS 拉到 N 条（`raw_{date}.json` 中有源名），但 `curated_*.json` 中该源条目永远为 0。

**根因分析顺序**（每步独立验证）：

1. **RSS 拉取成功？** — 检查 `cache/raw_*.json` 中 `source_platform` 含该源名，且 `len(items) > 0`
2. **`_likely_domain` 正确？** — `curate_domain()` 第一关过滤 `_likely_domain == domain`。源 25 条里如果 17 条被分到 `top_headlines`，5 条到 `tech`，说明分类正常（一个源跨域合理）
3. **`score_item` 分数足够？** — `score_item(it, 'top_headlines')['total'] >= MIN_SCORE`（默认 5），且 `recency > 0`
4. **被兴趣关键词压制？** — `score_item` 第 178-186 行有 `pos_kw` (+2) 和 `neg_kw` (0)。**220 个 pos 关键词偏中国话题**（中国、中美、华为、半导体、AI、互联网、台海、经济、财报、大模型等）。一个 Japan/泛亚源（Nikkei Asia）的标题基本不命中任何 pos 关键词，**+2 优势被中国源拿走** → 即使 `authority=3` 也无法进 top N
5. **被 `MAX_SAME_SOURCE=2` 硬截？** — `curate_domain()` 第 235-242 行：同源 >2 条直接 drop 末尾。源 25 条场景下，1-2 条幸存，其余全丢

**修复方向**（按 ROI 排序）：

| 方向 | 改动 | 代价 |
|------|------|------|
| A. 保持现状 | 啥也不做 | 失去日本/泛亚深度，但保留 raw 数据给 deep analysis 阶段 |
| B. 调整 `ai_interests.yaml` | 加入泛亚/日本半导体/汽车关键词 | 主观、易稀释其他源；不推荐 |
| C. `scorer.py` 加全局 boost | `if 'Nikkei' in platform: total += 1` | 简单粗暴；绕过兴趣 profile；不推荐 |
| D. 接受"top_headlines 8 槽"限制 | 不修，但加注释 | 已通过"专题 5-Nikkei"绕过 |

**实操验证**（Nikkei Asia 已验证）：
- priority 从 0 改到 2 → **完全无效**（`curate_domain()` 第 230 行 `result.sort(key=lambda x: x['_curator_scores']['total'], reverse=True)` 重新按分数排序，priority 只影响 diversity_penalty 时机，不影响最终结果）
- 实际进不去的根因是分数差 3-4 分（13-14 vs 10-12），不是 priority/authority

**何时选 A**：当一个源**确实 RSS 正常 + 评分通过 + 但因为兴趣 profile 失配落选**。这是 by design 的过滤行为，不是 bug。

**何时不选 A**：当分类错了（应到 `foreign_china` 跑到 `tech`），或分数 < MIN_SCORE，或 hard cap 误伤——这些是真 bug，要修。
