# 管线性能分析方法 + 当前基线

## 运行全管线并获取耗时

```bash
set -a && source ~/.hermes/.env && set +a
python3 -m trendradar.scripts.pipeline_orchestrator --push-id {slot} 2>&1
```

输出 JSON 的 `stats.stages` 包含每阶段耗时。`total_elapsed` 是端到端时间。

## 分析框架

1. **关键路径** — 并行阶段的 `max()` 是实际瓶颈，不是 `sum()`
2. **死代码检测** — 某阶段写缓存文件但无下游读取 = 死代码，可安全移除
   - 方法：`grep -rn "cache/{name}\|read_compressed\|batch_path" scripts/*.py` 检查读取方
   - 案例（2026-06-02）：`batch_fetch` 写 `cache/batch_{slot}.json.zst`，但 `batch_path()` 函数全管线零调用 → 12s 纯浪费，移除后总耗时 21s → 8.7s
   - 验证范围：不仅检查 scripts/*.py，还需检查 skills/（周报/月报）、render、scorer、heat_tracker 是否读该输出
3. **LLM 调用次数** — `ai_translate` 耗时 ≈ (翻译批次数 + 扩写批次数) × API 往返时间。减少批次 = 省时间
4. **缓存命中率** — `push_prepare` 有 raw cache（4h 有效期）。`ai_translate` 有 SHA-1 translate cache（持久）。首次跑（无缓存）耗时远高于后续

## 当前基线（2026-06-03 实测，3 次 fresh morning run 平均）

| Stage | Cold cache + cold fetch | Warm cache + fresh fetch | Warm cache + warm data |
|-------|---:|---:|---:|
| push_prepare (fetch+curate) | 17.2s | 1.6s | 0.1s |
| ai_translate (含缓存命中) | 7.0s | 4.5s | 1.5s |
| render_markdown | 0.002s | 0.002s | 0.002s |
| fragment_push | 0s | 0s | 0s |
| record_fingerprints | 0.009s | 0.005s | 0.005s |
| **TOTAL** | **~24s** | **~6s** | **~1.7s** |

**3 次 back-to-back 后稳定状态**：cron 9/12/21 实际命中 warm cache + warm data 路径，**~3s/次**。

**fetch 阶段冷热差异 17s 来自网络**：43 源并发（含 6 直连 + 37 代理），代理冷启动 + DNS 解析 + 5 源持续失败（澎湃/Al Jazeera/WSJ/Reuters/Sixth Tone）拖累。warm 路径（raw 缓存 4h 内）秒过。

## 已实施的优化（2026-06-03 写入）

### AI 翻译 SHA-1 缓存（最大优化，7s → 1.5s）

**机制**：`ai_translate.py` 在 `process_one_batch()` 入口对每对 `(title, summary)` 计算 SHA-1，命中 `cache/translate_cache.json` 直接复用结果，跳过 API 调用。未命中才发请求，结果写回 cache。

**Cache key**：`{hash(title)} | {hash(summary)} | {source_lang}` — 同一篇文章 morning/noon/evening 三次推送共享。存储为 `cache/translate_cache.json`（原子写，temp + replace）。

**收益**：cron 9/12/21 实际命中 ~50% (fresh fetch) 或 100% (warm data)。11-12 条外媒翻译从 5-7s 降到 <1s。

**同步要求**：3 副本同步（legacy + nested + git worktree），否则 Python namespace shadow 加载 legacy 旧代码看不到缓存逻辑。

**测试隔离**：`TestBatchTranslateAllBatching` / `TestCircuitBreakerBoundary` 在 `setup_method` 中 `unlink(_get_cache_path())` — 否则测试 mock 的 `batch_translate` 因缓存命中不被调用，测试失败。

### fetch 重试 2 → 1（节省 ~6s cold fetch）

**机制**：`fetch_feeds.py` `_fetch_one()` `max_retries` 从 2 改为 1（2 次尝试），backoff 从 1-2s 减到 0.5-1s。

**理由**：3 源 × 8s timeout + 1-2s backoff = ~30s per failed source。5 持续失败源（澎湃/Al Jazeera/WSJ 商业/Reuters/Sixth Tone）2 次重试浪费 6s 关键路径预算，**0 收益**（它们重试还是失败）。1 次重试抓 transient proxy blip，2 次 bail out。

**实测**：cold fetch 22.6s → 16.7s（节省 5.9s）。

## 进一步优化思路（未实施）

- 翻译+扩写合并为 1 个 prompt → 3 次 API → 1 次 → 预计省 4-5s
- 增大 `TRANSLATE_BATCH_SIZE`（当前 10 → 16）让翻译 1 批完成 → 省 1 次 API 调用
- `fetch` 用 4s timeout 替换 8s（部分源确实 8s 才有响应，需要先观察）

## 已移除的死代码

| 模块 | 移除日期 | 原因 | 省时 |
|------|----------|------|------|
| `batch_fetch.py` | 2026-06-02 | 写 cache/batch_{slot}.json.zst 但全管线（日报/周报/月报）无读取方 | 12s |
| `validate_output.py` | 2026-06-02 | 0 引用，功能被 sanity_check + delivery_watchdog 覆盖 | 0s (纯代码) |
| `pipeline_stage.py` | 2026-06-02 | 16 行 `PipelineStageResult` Protocol 0 引用 | 0s (纯代码) |
