<!-- version: 2.8.0 | last-reviewed: 2026-05-26 -->

# sources.json 格式 (v2.0)

位置: `~/.hermes/trendradar/data/sources.json`

## 结构
```json
{
  "version": "2.0",
  "last_updated": "ISO-8601",
  "data_sources": [{ ... }]
}
```

## 源对象
| 字段 | 类型 | 说明 |
|------|------|------|
| id | str | 唯一标识 |
| name | str | 显示名称 |
| type | str | rss / blog / hotlist |
| feed_url | str | RSS 源地址 |
| category | str | news / tech / economy / game / foreign |
| enabled | bool | 是否启用 |
| language | str | zh / en / ja |
| update_interval_minutes | int | 刷新间隔 |
| last_fetched | str (ISO) | 最后抓取时间 |

## 查询
```python
import json
d = json.load(open('data/sources.json'))
feeds = [s for s in d['data_sources'] if s['type'] == 'rss']
```

注意：v2.0 统一在 `data_sources` 数组内。v1.x 的顶层 `rss/blogs/hotlists` key 已不存在。
