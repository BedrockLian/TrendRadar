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

外媒源（en/ja）需要在 `_foreign_sources()`（`scripts/curate_and_push.py`）的 platform 白名单中添加其 `platform` 值，否则涉华文章不会被分入 `foreign_china` 域。

```python
def _foreign_sources() -> frozenset:
    return frozenset(s['name'].lower() for s in _sources()
                     if s.get('authority', 1) >= 2 and s.get('platform') in (
        'reuters', 'bbc', 'nytimes', 'scmp', 'nikkei', ...
    ))
```

## 当前源列表（2026-05-31，43 个活动源）

```
💻 科学/技术 (13)
  3  MIT Technology Review · Wired · Nature News · Science News · The Decoder
  2  Ars Technica · TechCrunch · The Verge · 纽约时报·科学 · 纽约时报·科技
     VentureBeat · 机器之心 · 量子位

📰 头条 (8)
  3  纽约时报·世界 · 南华早报 · AP News · Al Jazeera
  2  界面新闻 · 澎湃新闻 · 联合早报·中国 · 联合早报·国际

🎮 游戏 (9)
  3  GamesIndustry.biz · Video Games Chronicle · Eurogamer · Game Developer
  2  机核 · PC Gamer · Rock Paper Shotgun · The Verge·游戏 · Aftermath

📊 经济 (6)
  3  Bloomberg · Reuters · Financial Times · WSJ 世界新闻 · WSJ 商业
  2  纽约时报·商务

🌏 国际/外媒看华 (7)
  3  BBC 中国 · BBC 世界 · NPR 国际 · SCMP 中国 · Nikkei Asia
  2  Sixth Tone · Foreign Policy
```

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
