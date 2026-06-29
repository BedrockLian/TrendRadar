# 性能参数决策记录

最后更新: 2026-06-02（P-01 实测修订）

## 当前值

| 参数 | 值 | 位置 | 理由 |
|------|-----|------|------|
| `TRANSLATE_BATCH_SIZE` | **10** | `config/translation.py` | 2026-06-02 实测最优（见下"P-01 实测反例"） |
| `TRANSLATE_BATCH_MAX_CONCURRENT` | **6** | `config/translation.py` | 配合 batch_size=10 提供并发余量 |
| `TIMEOUT_SEC` (RSS) | **8** | `config/fetching.py` | WSL2 代理到外网偶有 5-7s 延迟 |
| `CIRCUIT_BREAKER_THRESHOLD` | **5** | `ai_translate.py` | 瞬态 429 不应触发熔断 |
| `TCPConnector.limit_per_host` | **12** | `fetch_feeds.py` | 代理连接器所有外部源共享限制 |
| `API_CALL_TIMEOUT` | 60 | `config/fetching.py` | 无需改动（翻译超时已自适应） |
| `FETCH_RETRIES` | 3 | `config/fetching.py` | |
| `API_RETRIES` | 3 | `config/fetching.py` | |
| `API_RETRY_BACKOFF` | 2 | `config/fetching.py` | |

## P-01 实测反例：批次增大不是越快（2026-06-02）

**原假设**（b4f50ac）：BATCH_SIZE 10→20 → 2 批变 1 批，省 2.5s（~30% 加速）。

**实测反例**（12 条 expand，deepseek-v4-flash，6 次 trial）：

| BATCH | 批次数 | wall time | 加速 |
|-------|--------|-----------|------|
| 10 | 2 批 (10+2) | 12.4-12.7s | 基线 |
| 20 | 1 批 | 15.4-17.3s | **+30%**（变慢） |
| 30 | 1 批 | 16.5-16.9s | **+33%**（变慢） |

**根因**：deepseek-v4-flash 对长 prompt 吞吐非线性衰减。单批 LLM 响应时间随 item 数增长 50-70%，超过了"省 1 批"的网络往返节省。

**推论**：
- 切到更快模型（claude-haiku、gemini-flash）后**必须重测** P-01 假设 —— 长 prompt 延迟更小的话 1 批可能更优
- 切到更慢模型（opus、pro）后 batch_size 应**降到 5-7**
- 一般经验：**单批延迟与往返节省的交叉点决定最优 batch**。模型吞吐差时降 batch，模型吞吐好时升 batch

**铁律**：
1. **不要未经实测**改 BATCH_SIZE —— 理论 2 批→1 批 ≠ 实际更快
2. 改完后**用 prod 同等条目数**（不是 1-2 条 toy）跑 3 次取 min 看 wall time
3. 改完后用 LLM 日志看 `Translate batch X-Y/N: processed Z items` 验证**实际批次数**（不要看 BATCH_SIZE 常量）

## 历史 BATCH_SIZE=5 陷阱（已过时但保留记录）

旧版本（2026-05-30 之前）BATCH_SIZE=5。原因：DeepSeek 早期模型在 batch >5 时只翻摘要不翻标题（`title_cn == title`）。这是**早期模型行为 bug**，`deepseek-v4-flash` 已修复，当前 batch=10 标题正常翻译。

**回归测试**：每次升级模型后跑 `ai_translate.py --push-id evening`，检查 `title_cn == title` 的条目数应为 0。**新检查**：

```python
import json
d = json.load(open('data/curated_evening_<DATE>.json'))
bad = sum(1 for dom in ['top_headlines','foreign_china','tech','economy','gaming']
          for it in d[dom]
          if (it.get('title_cn','').strip() == it.get('title','').strip()
              and it.get('source_lang')))
assert bad == 0, f'{bad} items with title_cn == title (假翻译)'
```

## P-02：atomic_write_json 移除 indent=2

`scripts/settings.py` `atomic_write_json()` 之前 `json.dump(indent=2, ensure_ascii=False)`，输出 43KB curated 文件。改为 `json.dump(ensure_ascii=False)` 后：
- **文件体积 -21%**（43KB → 34KB）
- **写盘时间** 缩短 0.2-0.5s（4 个 curated 文件 × 3 slots = 12 次写）
- **git diff 可读性** 不变（已是 line-based diff，缩进不影响）

**保留价值**：永久有效，与 batch size 无关。b208dde revert 保留了 P-02。

## 自适应翻译超时

`ai_translate.py:batch_translate()` 超时公式：
```
timeout_seconds = 30 + len(messages) * 3 + (attempt * 15)
```
- 基础 30s + 每消息 3s + 每次重试加 15s
- 替代原来的 `120 + attempt * 30`

## 直连+代理并行抓取

`fetch_feeds.py` 2026-05-29 改为并行：
```
async with (direct_session, proxy_session):
    direct_results, proxy_results = await asyncio.gather(direct_task, proxy_task)
```
预期节约 ~5s/次。

## 性能基线（2026-06-02 测量）

全管线（推送 noon slot 实际跑）总耗时构成：
- fetch: ~3s（43 源，EXTERNAL_CONCURRENT=43）
- curate + score: ~0.5s
- ai_translate: ~7.6s（占 87%）
- render: ~0.1s
- 总计: ~8.7s

**主要优化空间集中在 ai_translate**。其他阶段已接近天花板（fetch 3s 受网络限制）。

## 手动 benchmark 流程

不要用 1-2 条 toy 数据测 batch size（噪声主导）。用 10-20 条真实数据：

```bash
# 1) 选一份已翻译过的 curated_evening_<OLD_DATE>.json 备份
cp ~/.hermes/trendradar/data/curated_evening_20260601.json /tmp/bench.bak.json

# 2) 准备脚本：还原 + 清空 summary_cn + 截短到 < 90 触发 expand
# 3) 跑 3 次取 min
for trial in 1 2 3; do
  cp /tmp/bench.bak.json ~/.hermes/trendradar/data/curated_evening_20260601.json
  # 清空 + 截短（必须 < 90 字符才会进 expand 队列）
  python3 -c "import json; d=json.load(open('...')); ..."
  /usr/bin/time -f "WALL=%e" python3 -m trendradar.scripts.ai_translate --push-id evening --batch-size $BS
done

# 4) 还原
cp /tmp/bench.bak.json ~/.hermes/trendradar/data/curated_evening_20260601.json
# 注：也要同步到内层 git 副本
cp /tmp/bench.bak.json ~/.hermes/trendradar/trendradar/data/curated_evening_20260601.json
```

**关键细节**：
- `summary_cn` 清空后还要把 `summary` 截到 < 90 字符（`_load_and_scan` 触发 expand 的硬条件）—— 否则脚本判 "No items need processing" 跳过整个翻译
- 用 `--push-id evening`（不是 morning/noon）—— evening 旧 dated 文件丰富，cleanest 隔离
- 注意**两 data 目录**（见 system-config SKILL）—— 改外层不影响内层，md5 比对验证
