# Pipeline — TrendRadar 日报推送管线

v2.8.0 起使用 `pipeline_orchestrator.py` 一键编排。`0 9,12,21 * * *`。
脚本阶段用 python3.14t（free-threaded），渲染用 render_markdown.py（纯脚本，~0s）。

Agent 可通过 `--list-steps` 动态获取管道步骤定义（SSOT），不再依赖手动维护的步骤表。

## 性能要点

- **RSS 抓取**：`TCPConnector(limit=40)` ≥ Semaphore 容量，防连接槽缺口
- **关键词分类**：AC 自动机替代 `any()`，curation CPU 4.4x
- **AI 翻译 ∥ 全文抓取**：`ThreadPoolExecutor(max_workers=2)` 真并行（替代旧 Shell `& wait`），省 5-8s
- **DB 层**：WAL + `synchronous=NORMAL` + mmap=256MB + 复合索引 `(status, last_seen)`
  - 所有模块通过 `Storage.db()` 统一接入，自动启用 WAL + busy_timeout
  - `Storage.vacuum()` 可手动回收碎片空间
- **指纹**：`make_fingerprint(title, url)` 含 URL 前 3 段路径防日语标题碰撞
- **分片**：`fragment_push.py` 三级 UTF-8 字节拆分（段落 \n\n → 句子 。 → 硬切 3800B），防 WeCom 静默截断
- **迁移**：编排器启动时自动 `migrate()`，确保 Schema 最新

## 自动特性

- **Step -1 迁移检查**：`migrate(db)` — 启动前确保 DB schema 最新
- **Step 0 环境预检**：`push_slot_detect` + `PYTHONPATH` + `PYTHON_GIL`
- **SILENT 闭环**：无新内容时物理删除中间文件 + `fragments=[]` 显式空数组
- **熔断退避**：AI 翻译 5 次指数退避（2s→30s + jitter）+ 连续 3 失败熔断跳过
- **多样性惩罚**：curate 同源 >3 条权重减半，防单一来源霸榜
- **推送日志**：`push_log.json` 记录每次推送结果（状态/片数/耗时）

## 故障恢复

### 数据损坏
```bash
rm -f ~/.hermes/trendradar/cache/batch_{slot}.json
rm -f ~/.hermes/trendradar/data/curated_{slot}.json
cronjob action=run job_id=90a2866775df
```

### Gateway 崩溃后补推（简报已出但未送达）
```
hermes gateway start  # 先恢复通道
cd ~/.hermes/trendradar
# 绕过 slot 检测，三步直推：
/usr/local/bin/python3.14t scripts/render_markdown.py --push-id {slot} 2>/dev/null | \
  /usr/local/bin/python3.14t scripts/fragment_push.py 2>&1
# 末尾 JSON 数组 → 作为 final response 逐片输出，系统自动投递 WeCom，片间 1.5s
# 注意：不要重跑完整 pipeline（会破坏指纹/热度一致性）
```

### 翻译 API 断流（Trap 28）
自动重试已内置（5 次指数退避 + 熔断器）。若全部 batch 失败：
```bash
# 已有的 curated JSON 不会丢失，下个时段重新翻译
# 或手动重跑：
/usr/local/bin/python3.14t scripts/ai_translate.py --push-id {slot}
```

## 脚本清单

`push_slot_detect.py` | 时段路由
`push_prepare.py` | fetch + curation 编排
`fetch_feeds.py` | 38 RSS 异步抓取
`curate_and_push.py` | 5 domain 并行精选 + 来源多样性惩罚
`ai_translate.py` | AI 批量翻译 + 指数退避重试 + 熔断器
`batch_fetch.py` | 10 并发全文抓取
`render_markdown.py` | 纯脚本渲染（替代 Agent 手动渲染）
`render_deep_analysis.py` | Pro 深度分析格式化排版
`fragment_push.py` | UTF-8 字节计数分片（3800B/片），三级递降拆分
`track_events.py` | 跨日事件追踪
`record_fingerprints.py` | 指纹记录（Storage 统一接入）
`blog_watcher_bridge.py` | blogwatcher 集成
`pipeline_orchestrator.py` | 一键编排器 v2.8.0
`blind_spot_audit.py` | 盲点审计 + --json 机器可读模式
`aggregate_monthly.py` | 月度统计 + --suggest-interests 兴趣漂移
