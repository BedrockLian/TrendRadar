# RSS 源管理：发现与添加

## 源配置位置

`sources.json` — 54+ 条源定义。存在两份：

- **运行时**: `~/.hermes/trendradar/data/sources.json`（管线运行读这份）
- **仓库**: `~/TrendRadar/trendradar/config/sources.json`（版本管理）

修改后必须同步：修改运行时文件后 cp 到仓库并 git push。

```json
{
  "data_sources": [
    {
      "id": "bbc_china",
      "name": "BBC 中国",
      "platform": "bbc",
      "type": "rss",
      "category": "foreign_china",
      "enabled": true,
      "feed_url": "https://feeds.bbci.co.uk/news/world/asia/china/rss.xml",
      "authority": 3
    }
  ]
}
```

`category` 可选值: `tech` / `economy` / `foreign_china` / `game` / `news`。AC 自动机会按关键词将文章二次分类到具体板块。

### 源命名规范

- `name` 字段必须在 `source_platform` 中作为显示名出现
- **使用中文命名**，不使用日文片假名/平假名（例如 `NHK 商业` 而非 `NHK ビジネス`）
- 简短优先，方便 `kw in plat.lower()` 子串匹配

## 翻译配置解耦

翻译语言检测由 `config/translate.yaml` 驱动，不再硬编码在 `ai_translate.py`。
加新源需要两步：

1. `data/sources.json` 加 RSS 条目
2. `config/translate.yaml` 加对应语言的关键字（一行）

`translate.yaml` 使用短关键字子串匹配（如 `bbc` 同时覆盖 `BBC 商务`、`BBC 科技`、`BBC 商务+BBC 科技`）。

## 已知可用源

### BBC (feeds.bbci.co.uk) — 全部直连可用

```
/news/rss.xml                          综合头条
/news/world/rss.xml                    国际
/news/world/asia/china/rss.xml         中国话题
/news/business/rss.xml                 商务
/news/technology/rss.xml               科技
/news/politics/rss.xml                 政治
/news/health/rss.xml                   健康
/news/science_and_environment/rss.xml  科学环境
/news/entertainment_and_arts/rss.xml   娱乐文化
```

### NYT (rss.nytimes.com) — 全部直连可用

```
/services/xml/rss/nyt/World.xml        国际
/services/xml/rss/nyt/Technology.xml   科技
/services/xml/rss/nyt/Business.xml     商务
/services/xml/rss/nyt/Science.xml      科学
/services/xml/rss/nyt/Health.xml       健康
/services/xml/rss/nyt/HomePage.xml     头条
```

### NPR (feeds.npr.org)

格式: `https://feeds.npr.org/{ID}/rss.xml`

| ID | 栏目 | 分类 |
|----|------|------|
| 1001 | News | news |
| 1004 | World | foreign_china |
| 1006 | Business | economy |
| 1007 | Science | tech |
| 1013 | Education | — |
| 1014 | Politics | — |

### NHK (www3.nhk.or.jp)

格式: `https://www3.nhk.or.jp/rss/news/cat{N}.xml`

| cat | 栏目 | 分类 |
|-----|------|------|
| 0 | 総合 (General) | news |
| 1 | 社会 (Society) | — |
| 2 | 文化・エンタメ | — |
| 3 | 科学・医療 (Science) | tech |
| 4 | 政治 (Politics) | news |
| 5 | 経済 (Economy) | economy |
| 6 | ビジネス (Business) | economy |

### Reuters — 通过本地 RSSHub (localhost:1200)

Reuters 已关闭公开 RSS (`feeds.reuters.com` 全部 404)。通过本地 RSSHub 实例转译：

```
/reuters/business     商务          → economy
/reuters/technology   科技          → tech
/reuters/world/china  中国          → foreign_china
/reuters/world        国际          → foreign_china
```

### Korea Herald (koreaherald.com)

韩国英文媒体，覆盖韩国政治/经济/文化/韩流。直连可用：

```
https://www.koreaherald.com/rss/newsAll
```

### 已下线/不可用

- **AP (Associated Press)**: 公开 RSS 已全部下线。所有 `apnews.com/hub/*.rss`、`apnews.com/rss/*` 404。
- **韩联社 (Yonhap News, yna.co.kr)**: 本环境 DNS 不可达。替代：Korea Herald。
- **RSSHub 公网 (rsshub.app)**: 本环境不可达。本地版 `localhost:1200` 可用。

## 添加步骤

1. 验证源 URL 可用（curl 或用 web_extract 确认返回 RSS XML）
2. 确定 `category`
3. `name` 用中文命名，写入 `sources.json` 的 `data_sources` 数组
4. 确定语言归属，在 `config/translate.yaml` 的 `english:` 或 `japanese:` 列表中加入匹配关键字
5. `cp data/sources.json ~/TrendRadar/trendradar/config/sources.json`
6. `cd ~/TrendRadar && git add -A && git commit -m "feat: add <name> feed" && git push`
7. 下次管线自动抓取（无需重启）
