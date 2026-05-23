# TrendRadar 日报流水线 (cron 90a2866775df)

8 步执行，`0 9,12,21 * * *`。脚本阶段用 python3.14t（free-threaded），渲染用 render_briefing.py（5 路并行 API，~9s）。

## 步骤表

> **共 11 步（Step 0-10），详见下文。**
> 本文档保留以下补充内容：性能估算、故障恢复命令、脚本清单。

## 性能要点

- **RSS 抓取**：`TCPConnector(limit=40)` ≥ Semaphore 容量，防连接槽缺口
- **关键词分类**：AC 自动机替代 `any()`，curation CPU 4.4x
- **AI 翻译 ∥ 全文抓取**：Shell `& wait` 并行，省 5s
- **DB 层**：WAL + `synchronous=NORMAL` + mmap=256MB + 复合索引 `(status, last_seen)`
- **指纹**：`make_fingerprint(title, url)` 含 URL 前 3 段路径防日语标题碰撞

## 故障恢复

```bash
rm -f ~/.hermes/trendradar/cache/batch_{slot}.json
rm -f ~/.hermes/trendradar/data/curated_{slot}.json
cronjob action=run job_id=90a2866775df
```

## 脚本清单

`push_slot_detect.py` | 时段路由
`push_prepare.py` | fetch + curation 编排
`fetch_feeds.py` | 38 RSS 异步抓取
`curate_and_push.py` | 5 domain 并行精选
`ai_translate.py` | AI 批量翻译
`batch_fetch.py` | 10 并发全文抓取
`render_briefing.py` | 5 路并行渲染（替代 Agent 手动渲染）
`fragment_push.py` | 按 `### ` 板块分片，尾注仅末片
`track_events.py` | 跨日事件追踪
`record_fingerprints.py` | 指纹记录
`blog_watcher_bridge.py` | blogwatcher 集成
