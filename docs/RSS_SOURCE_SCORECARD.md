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

| 原来源 | 清洗原因 | 已启用替代 | 当前决策 |
|---|---|---|---|
| Reuters | Google News 聚合，不是 Reuters 官方直连 | WSJ、Financial Times、BBC、CNA 等已存在的官方直连源 | 已停用；授权 RSS/API 仅留档，官方交付见 [Reuters Content Delivery](https://reutersagency.com/content-delivery-platforms/content-delivery) |
| AP News | Google News 聚合；公开 AP RSS 现场返回授权错误 | NYT、BBC、DW、PBS NewsHour、CNA | 已停用；授权入口见 [AP Media API RSS](https://api.ap.org/media/v/docs/Feed.htm) |
| AFP | Google News 聚合；公开 RSS 主要是新闻稿，不等价于完整新闻流 | BBC、Al Jazeera、Guardian、PBS | 已停用；公开范围见 [AFP Press Releases](https://www.afp.com/en/agency/inside-afp/press-releases) |
| 联合早报·中国/国际 | `plink.anyfeeder.com` 第三方中转，连续现场检查失败 | 新增 CNA 亚洲/世界官方 RSS；保留 BBC、Sixth Tone、南华早报、DW、Nikkei | 已停用；不再让第三方中转进入生产抓取 |
| ArXiv AI | 预印本不是编辑审校后的新闻，且当前 RSS 抓取失败 | MIT AI、MIT Technology Review、Nature News | 已停用；研究候选保留在配置留档 |
| Nintendo Life | 官方站点 RSS 连续返回 HTTP 403 | VGC、PC Gamer、Eurogamer、IGN | 已停用；游戏专题由稳定直连源覆盖 |
| TechCrunch | RSS、栏目 feed 和 API 重复出现 TLS 提前断开 | Rest of World、Ars Technica、MIT Technology Review、Wired | 已停用；媒体价值保留，待传输恢复后重新核验 |
| IGN | FeedBurner 旧式中转，但现场仍有有效条目 | 暂保留；优先使用 VGC、PC Gamer、Eurogamer 交叉覆盖 | `legacy_relay`，持续监测 |

## 本轮新增直连源

| 来源 | 入口 | 用途 | 选择依据 |
|---|---|---|---|
| CNA 亚洲/世界 | [CNA 官方 RSS](https://www.channelnewsasia.com/rss) | 替代联合早报两路中转，覆盖亚洲与国际 | 官方页面公开列出 Asia、World RSS；现场抓取各返回 20 条有效条目 |
| PBS NewsHour | [PBS News RSS](https://www.pbs.org/newshour/about/pbs-news-rss-feeds) | 替代 AP 聚合入口，补充公共广播新闻 | 官方页面明确提供 Headlines RSS；现场抓取返回 20 条有效条目 |
| Rest of World | [Rest of World Platforms](https://restofworld.org/platforms/) | 补充全球科技、社会影响与中国以外视角 | 非营利专业出版物，官方页面公开 Latest Stories RSS；现场抓取返回有效条目 |

## 当前数据质量边界

- `source_evaluation.json` 是评分规则和例外说明的单一事实源；`source_audit.py` 每次实时计算频率，不把一次抓取结果写成永久事实。
- 本轮清洗后，生产启用源只保留官方直连、可解释的专业直连或明确的旧式中转；Google News、anyfeeder 等聚合/第三方中转不再进入生产抓取。
- 被停用的源保留 `enabled: false`、`disabled_reason` 和替代 `fallback_ids`，用于审计历史，不参与生产采集。
- 现有 `sources.json` 的 `authority` 字段仍用于旧的精选算法；新的三维表暂时只用于审计和报告，避免未经连续观测就改变生产排序。
- 未来应记录每个源 7 天和 30 天的成功率、解析失败率、最新条目年龄、重复率、标题/摘要完整率，以及聚合链接是否回到目标媒体域名。
- ArXiv、MIT News、Nature News 等来源必须按来源类型解释：研究预印本、机构新闻和科学出版物不能使用同一套“新闻快讯”标准。
