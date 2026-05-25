# 管线故障恢复 + 性能基线

## 标准恢复（数据损坏/不完整）

```bash
rm -f ~/.hermes/trendradar/cache/batch_{slot}.json
rm -f ~/.hermes/trendradar/data/curated_{slot}.json
cronjob action=run job_id=90a2866775df
```

## Gateway 崩溃后补推（简报已产出但未送达）

**前置检查**（跳过则补推可能无效）：
1. `hermes config get security.tirith_enabled` — 若为 true，cron 内部命令会被中文拦截
2. cron job 的 skills 列表是否引用已重命名的技能
3. 确认 curated 数据还在（`ls -la ~/.hermes/trendradar/data/curated_{slot}_*.json`）

**补推步骤**：
```bash
hermes gateway start  # 先重启 Gateway
cd ~/.hermes/trendradar
BRIEFING=$(/usr/local/bin/python3.14t scripts/render_markdown.py --push-id {slot} 2>/dev/null)
# 输出 BRIEFING 给系统自动投递（不要用 send_message）
```

**关键判断**：不要重新跑完整 pipeline（push_prepare → batch_fetch），会变更数据状态（指纹去重、热度追踪）。直接用现有 curated JSON 做 render→输出。

## 性能基线（2026-05 实测）
- push_prepare: ~15s（含 RSS 抓取+分类+精选）
- ai_translate: ~8s（35条目并行翻译）
- batch_fetch: ~5s（URL 全文抓取）
- render_markdown: ~0.0s（纯脚本拼接）
- fragment_push: ~0.0s
- record_fingerprints: ~0.2s
- cron 端到端: ~35s（含 LLM 编排开销）

## Raw 缓存层故障模式

`push_prepare.py` 的 `run_curation()` 通过 `ensure_raw_exists()` + 两阶段并行(fetch+blog)获取数据：

```
ensure_raw_exists() → 检查 CACHE_DIR/raw_{YYYYMMDD}.json
  ├─ HIT (龄<4h) → 跳过 fetch
  └─ MISS → asyncio.run(fetch_all(push_id))
        │
        ├─ 成功 → 写入 raw_{YYYYMMDD}.json → 后续读 raw 出数据
        └─ 异常 → ThreadPoolExecutor 静默捕获（log.info）
                        raw_{YYYYMMDD}.json 不存在 → raw = []
                        → curate_all([]) → 总 output 为 0 条
```

**关键诊断**：产出 0 条时检查：
1. `ls ~/.hermes/trendradar/cache/raw_{today}.json` — 不存在说明 fetch 阶段失败
2. `ls ~/.hermes/trendradar/cache/raw_{yesterday}.json` — 可能存在上一日缓存（龄<4h 仍会被 HIT）
3. `TIMEOUT_SEC = 6` — 慢速源可能在并发压力下超时。临时调大至 10-15 可排查
4. 代理 `TRENDRADAR_PROXY` 是否可用：`curl -x http://127.0.0.1:7890 -s -o /dev/null -w '%{http_code}' https://feeds.bbci.co.uk/news/rss.xml`

**临时修复**：删除 raw cache 重跑
```bash
rm -f ~/.hermes/trendradar/cache/raw_$(date +%Y%m%d).json
cronjob action=run job_id=90a2866775df
```
