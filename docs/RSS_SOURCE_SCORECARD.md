# RSS 来源评判表

这是 TrendRadar 的来源评判规则和替代源登记表。机器可读评分规则在 [`source_evaluation.json`](../src/trendradar/config/source_evaluation.json)，实时结果通过以下命令生成：

```text
python ops/codex/source_audit.py --live --format markdown
```

## 评分规则

评分只回答“这个来源适不适合进入哪一层信息流”，不声称自动证明每一篇报道为真。

| 维度 | 权重 | 评判内容 |
|---|---:|---|
| 质量 | 40% | 原创性、编辑规范、事实核验、上下文完整度、专业深度 |
| 权威 | 40% | 通讯社、公共机构、专业机构、区域媒体或垂直媒体在对应领域的身份 |
| 更新频率 | 20% | 实时抓取时最新条目的年龄，相对该源的目标更新间隔计算 |

另外设置传输闸门：`official`、`licensed`、`news_aggregator`、`third_party_mirror`、`legacy_relay` 分开记录。聚合地址不会因为原媒体品牌高，就被当作官方直连源。

决策层级：

- `core`：核心事实和突发新闻，可提高精选权重，但重大事实仍应交叉验证。
- `supplement`：可信补充，适合提供区域、行业或视角信息。
- `specialist`：专业垂直源，只在对应主题中提高权重。
- `fallback_only`：传输或证据链存在明显风险，只作为备用。
- `repair`：连续失败或元数据不一致，修复前不应提高权重。

## 聚合源替代方案

| 当前来源 | 当前问题 | 首选替代 | 当前决策 |
|---|---|---|---|
| Reuters | Google News 聚合；Reuters 官方 RSS 交付需要授权 | 有授权时接入 [Reuters RSS/API](https://reutersagency.com/content-delivery-platforms/content-delivery)；无授权时使用 WSJ、FT、BBC 直连源交叉替代 | 保留，但标记 `news_aggregator` |
| AP News | Google News 聚合；公开 `apnews.com/index.rss` 现场返回 401 | 有授权时接入 [AP Media API RSS](https://api.ap.org/media/v/docs/Feed.htm)；无授权时使用纽约时报、BBC、DW 直连源 | 保留，但标记 `official_api_requires_license` |
| AFP | Google News 聚合；官方公开 RSS 主要是新闻稿，不等价于完整新闻流 | 使用 [AFP 官方授权交付](https://www.afp.com/en/agency/inside-afp/press-releases)；无授权时使用 BBC、Al Jazeera、Guardian 直连源 | 保留，但标记 `public_rss_press_releases_only` |
| 联合早报·中国/国际 | `plink.anyfeeder.com` 第三方中转，两轮现场检查均失败 | 优先自建并固定 RSSHub/网页采集适配器；无法维护时使用 BBC 中国、Sixth Tone、南华早报、DW、Nikkei 直连源 | `fallback_only` |
| IGN | FeedBurner 旧式中转；当前仍能返回有效条目 | 暂保留并监测；若直连 RSS 路径被官方确认，再切换 | `legacy_relay` |

## 当前数据质量边界

- `source_evaluation.json` 是评分规则和例外说明的单一事实源；`source_audit.py` 每次实时计算频率，不把一次抓取结果写成永久事实。
- 现有 `sources.json` 的 `authority` 字段仍用于旧的精选算法；新的三维表暂时只用于审计和报告，避免未经连续观测就改变生产排序。
- 未来应记录每个源 7 天和 30 天的成功率、解析失败率、最新条目年龄、重复率、标题/摘要完整率，以及聚合链接是否回到目标媒体域名。
- ArXiv、MIT News、Nature News 等来源必须按来源类型解释：研究预印本、机构新闻和科学出版物不能使用同一套“新闻快讯”标准。
