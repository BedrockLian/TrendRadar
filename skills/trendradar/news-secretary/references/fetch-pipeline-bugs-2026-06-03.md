# Fetch Pipeline Bug 排查手册（2026-06-03 早报 0 条事故 + 后续修复）

## 症状

- 9:00 cron 跑 `pipeline_orchestrator.py` exit=0，但 curated JSON `total=0` 或 0 items
- `[FETCH] 43源` 行后**无** `[HEAT] 新增N条` 行
- 日志中 `WARN] 澎湃新闻: TimeoutError` / `ERROR] NameError: name '_get_parse_pool' is not defined` 大量堆积
- 早报 6 fragments 全是"共 0 条"占位
- 之后 slot（如 noon）读 `cache_valid=True` 跳过 fetch，沿用坏数据 → **整日静默失败**

## 4 个串联 bug + 排查顺序

按"先确认 import 路径正确 → 再确认 fetch 成功 → 最后确认编排"顺序排查：

### Bug 1: `scripts/` 双层目录冗余（最难发现，2026-06-05 修订）

**症状**：fetch 入口 logger 的 ERROR 行，但 `find_spec` 测试返回正确路径。pymodule 实际加载了**和测试不同**的副本，源码已修复却没生效（或生效了但没全生效）。

**2026-06-03 旧判断**（已过时）：当时 legacy 顶层**无** `__init__.py` → 被当 namespace package → runtime 命中 legacy。

**2026-06-05 实测修订**：legacy 顶层**已加** `__init__.py`（explicit package），runtime **实际命中嵌套真包**（`/home/asus/.hermes/trendradar/trendradar/scripts/`）。legacy 顶层是**孤儿**——runtime 不读，但**任何 git worktree / PYTHONPATH 调整 / 备份恢复时仍可能命中**。所以三副本同步仍然是必需的（不能省），但诊断判定标准反过来。

**诊断**（必跑）：
```python
python3 -c "
import sys
sys.path.insert(0, '/home/asus/.hermes')
import trendradar.scripts.fetch_feeds as ff
import trendradar.config.proxy as p
print('scripts:', ff.__file__)  # 期望: /home/asus/.hermes/trendradar/trendradar/scripts/fetch_feeds.py
print('config: ', p.__file__)   # 期望: /home/asus/.hermes/trendradar/trendradar/config/proxy.py
"
```
**2026-06-05 之后判定**：两行都指向嵌套真包（`.../trendradar/trendradar/...`）= 正常；指向 legacy 顶层（`.../trendradar/scripts/...`，无内层 `trendradar/trendradar/`）= 异常（没人用但 import 漂移了）。

**修复（保持不变）**：所有修改**三副本同步**（scripts + config 各 3 份）：
```bash
SRC=/home/asus/.hermes/trendradar/trendradar/scripts
cp $SRC/X.py /home/asus/.hermes/trendradar/scripts/X.py
cp $SRC/X.py /home/asus/TrendRadar/trendradar/scripts/X.py
# config 同理
SRC=/home/asus/.hermes/trendradar/trendradar/config
cp $SRC/X.py /home/asus/.hermes/trendradar/config/X.py
cp $SRC/X.py /home/asus/TrendRadar/trendradar/config/X.py
```

**根治方案**（待办）：删除 legacy 顶层 `scripts/` / `config/`（用 .gitkeep 保留 dir），runtime 只能命中嵌套真包。

### Bug 2: `Lazy(X)` wrapper 不可直接调

**症状**：`NameError: name '_get_parse_pool' is not defined` 在每个 fetch 任务中。

**根因**：`fetch_feeds.py` line 130 调 `_get_parse_pool()`，但变量定义是 `_PARSE_POOL = Lazy(_make_parse_pool)`（Lazy wrapper，**不是 callable**）。

**修复**：`loop.run_in_executor(_PARSE_POOL.get(), ...)`。

**验证脚本**：
```python
from trendradar.scripts.common import Lazy
class _X: pass
X = Lazy(_X)
try: X()  # 错：TypeError: 'Lazy' object is not callable
except TypeError: pass
X.get()    # 对：返回 _X instance
```

### Bug 3: `InterpreterPoolExecutor` 在 `PYTHON_GIL=0` 下 NotShareableError

**症状**：`[ERROR] [trendradar.fetch-feeds] 澎湃新闻: NotShareableError` × 43 源，但 `_make_parse_pool` 内的 try/except 没兜住（异常在 sub-interpreter 边界抛出，try/except 收不到）。

**修复**：跳过 InterpreterPoolExecutor，直接默认 `ThreadPoolExecutor(max_workers=24)`：
```python
def _make_parse_pool():
    return concurrent.futures.ThreadPoolExecutor(max_workers=24)
```

`parse_rss` I/O-bound，thread 数 = 瓶颈。

### Bug 4: `asyncio.run()` 嵌套在 `ThreadPoolExecutor` 内

**症状**：`run_curation` 用 `ThreadPoolExecutor(max_workers=2)` 并行 fetch+blog，fetch 内 `asyncio.run(fetch_all(push_id))` 返 0 items 不报错，curated 是空但 `result['items'] = []` 写到 cache。

**修复**：fetch + blog 顺序执行（牺牲 ~1s 换确定性）：
```python
ensure_raw_exists(push_id)   # 内部 asyncio.run，OK
blog_articles = load_blog_articles()
```

不推荐继续用 ThreadPoolExecutor 包裹 asyncio.run（嵌套 event loop 行为依赖平台/Python 版本）。

## Timing Baseline（30 条精选, 5 板块, 6 碎片）

| 阶段 | Cold cache + cold fetch | Warm cache + fresh fetch | Warm cache + warm data |
|------|:---:|:---:|:---:|
| **push_prepare** (fetch+curate) | **17.2s** | 1.6s | 0.1s |
| **ai_translate** | 7.0s | 4.5s (缓存 50%) | 1.5s (缓存 100%) |
| render_markdown | 0.002s | 0.002s | 0.002s |
| fragment_push | 0s | 0s | 0s |
| record_fingerprints | 0.009s | 0.005s | 0.005s |
| **TOTAL** | **~24s** | **~6s** | **~1.7s** |

**网络抓取基线**：43 源并发 (EXTERNAL_CONCURRENT=43, TCPConnector limit=43, TIMEOUT=8s)。5 源重试失败平均多 8-10s。澎湃/Al Jazeera 重试率高（Akamai CDN 阻断），可考虑 blacklist 跳过。

**优化点**（2026-06-03 实施）：
- **ai_translate SHA-1 缓存**（7s → 1.5s warm data）— 详见下方
- **fetch 重试 2 → 1**（cold fetch 22.6s → 16.7s）— 2026-06-05 改回 2（详见下下节）
- 翻译+扩写合并为 1 个 prompt → 3 次 API → 1 次 → 预计再省 4-5s
- 增大 `TRANSLATE_BATCH_SIZE`（当前 10 → 16）让翻译 1 批完成 → 省 1 次 API 调用

## 抓 3 次 fresh run 找优化点的标准流程

```bash
cd /home/asus/.hermes/trendradar
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

for i in 1 2 3; do
  rm -f cache/raw_*.json data/curated_morning_*.json
  T0=$(date +%s%N)
  PYTHON_GIL=0 PYTHONPATH=/home/asus/.hermes /usr/local/bin/python3.14t \
    trendradar/scripts/pipeline_orchestrator.py --push-id morning 2>&1 \
    | grep -E '✅|精选' | head -6
  T1=$(date +%s%N)
  python3 -c "print(f'wall: {($T1 - $T0) / 1e9:.2f}s')"
  echo "---"
done
```

**关键纪律**：
1. **清 `__pycache__` 必做** — 旧 pyc 可能藏 namespace shadow 解析结果
2. **删 `cache/raw_*.json`** — 否则跑 warm 路径看不出真实 fetch 耗时
3. **3 次取平均** — 首次 fetch 受 DNS 冷缓存影响耗时 30-50% 偏高
4. **`stats.stages` 字段是权威** — 不要相信 grep 出的 `✅` 行时间戳（编排器整体 wall clock，含 JSON 序列化）

## AI 翻译 SHA-1 缓存（2026-06-03 实施，最大优化）

**位置**：`ai_translate.py` `process_one_batch()` 入口

**机制**：
```python
cache = _load_cache()  # cache/translate_cache.json
cached_results = []
uncached_indices = []
for i, (t, s) in enumerate(pairs):
    key = f"{_content_hash(t)}|{_content_hash(s)}|{source_lang or 'auto'}"
    if cache.get(key):
        cached_results.append((i, cache[key]))
    else:
        uncached_indices.append(i)

if not uncached_indices:
    return (batch, [cache[f"...|...|..."] for t, s in pairs], None)  # 全缓存命中

uncached_pairs = [pairs[i] for i in uncached_indices]
api_results = await batch_func(items=uncached_pairs, ...)

# 写回 cache
for (t, s), res in zip(uncached_pairs, api_results):
    cache[f"{_content_hash(t)}|{_content_hash(s)}|{source_lang or 'auto'}"] = res
_save_cache(cache)
```

**Cache key 格式**：`{hash(title)} | {hash(summary)} | {source_lang}` — title+summary 标准化后 SHA-1 前 16 字符。同一篇文章 morning/noon/evening 共享，跨日也命中（除非标题/摘要被源微调）。

**原子写**：`tempfile.mkstemp` + `os.replace`，防止 cron 期间读到半文件。

**收益**：
- cron 9:00 cold：~24s
- cron 12:00 fresh fetch + 部分缓存：~6s（50% 命中）
- cron 21:00 100% 缓存：~1.7s

**测试隔离**：`TestBatchTranslateAllBatching` / `TestCircuitBreakerBoundary` 在 `setup_method` 中必须 `unlink(_get_cache_path())` — 否则测试 mock 的 `batch_translate` 因缓存命中不被调用，测试失败（4 个测试同时失败症状）。

**3 副本同步要求**：和 fetch / push_prepare 同样的 namespace shadow 坑，cache 逻辑也必须三副本同步（legacy + nested + git worktree）。

## Fetch 重试策略历史

- **2026-05-31**：默认 2 retries（每次指数 backoff）
- **2026-06-03 改 1**：节省 5.9s cold fetch 耗时（5 持续失败源无论如何都失败，2 retries 浪费 30s+）
- **2026-06-05 改回 2**：发现 mihomo URLTest 节点抽风时 1 retry 扛不住瞬态断流；17 源失联根因是 mihomo 切节点期间连接拒绝。第 2 次重试前 sleep 翻倍（0.5s → 1s → 2s），给 mihomo 切节点 + TCP 连接池回收留时间。同时加 `_fetch_batch()` 降级重试：43 并发 gather 后串行重试失败源一次。

**最终策略（2026-06-05 第三次修订）**：`max_retries=0` (batch 内不重试) + gather 后降级重试一次。**此版本推翻了 2026-06-05 早期的 max_retries=2 结论**——mihomo 切节点后 batch 内的瞬态 ClientConnectorError 实际不影响抓取成功率（其他源不受影响），让 batch 快速结束 + 失败源走独立降级通道反而更快（fetch 中位数 23.9s → 7.6s）。详细见「速度优化」节。

### Fetch 重试 2 → 1（2026-06-03 实施，**已被 2026-06-05 修订推翻**）

**位置**：`fetch_feeds.py` `_fetch_one()`

**2026-06-03 变更（已回滚）**：
```python
max_retries = 1  # 原 2
await asyncio.sleep(0.5 * (2 ** attempt))  # 原 1 * 2**attempt
```

**2026-06-03 理由**：
- 5 持续失败源（澎湃/Al Jazeera/WSJ 商业/Reuters/Sixth Tone）重试还是失败
- 3 尝试 × 8s timeout + 1-2s backoff = ~30s per failed source
- 1 尝试 + 1 重试（2 次总）= ~16s per failed source → cold fetch 节省 5.9s

**2026-06-05 推翻**：发现 1 retry 在 mihomo URLTest 节点抽风场景不够——mihomo 切节点 1-2s 期间 1 retry 也撞同一个抽风节点。**实测**：单纯把 retries 改回 2 把失败源从 17 降到 2。详细修复记录见下一节。

---

## 2026-06-05 17 源失联修复

**症状**：cron 21:00 evening 跑出 17 源 `ClientConnectorError`，新闻量从 ~500 跌到 337，**外媒看华域 0 条**。

### 根因
1. **mihomo URLTest 组自动选节点失败**：`🌍 国外媒体` 是 URLTest 类型，每 5min 自动测 `gstatic.com/generate_204` 切换。但 gstatic 延迟≠RSS 服务器延迟（gstatic 是 CDN），url-test 选出的"最优"节点对 RSS 源可能慢/抽风
2. **单次重试扛不住瞬态断流**：max_retries=1 抓不住 mihomo 节点切换的瞬时抽风
3. **直连白名单不全**：`jiqizhixin.com` 等 5 个国内站被错误分到代理组（`.com` 域名不匹配 `.cn/.com.cn`）
4. **降级重试复用 connector**：失败源想重试时 connector 资源被挤

### 修复
1. **`fetch_feeds.py: fetch_all()`** 增加 mihomo 当前节点诊断日志（`mihomo 当前节点: ...`）—— **不主动切**（url-test 外部 PUT 在某些 mihomo 版本被拒）
2. **`fetch_feeds.py: _fetch_one()`** `max_retries: 1 → 2`，第 2 次重试前 sleep 翻倍（0.5s → 1s → 2s），给 mihomo 切节点 + TCP 连接池回收留时间
3. **`config/proxy.py`** DOMESTIC_PROXY_PATTERNS 加 `jiqizhixin.com` / `36kr.com` / `sspai.com`
4. **`fetch_feeds.py: _fetch_batch()`** 新增**降级重试**：43 并发 gather 后，收集失败源，**复用同一 session 串行重试一次**（不抢 connector 槽）
5. **三副本同步**（legacy 顶层 + 嵌套真包 + git worktree 全部 md5 一致）

### 验证
- 修复前：17/43 失败，337 items，0 条外媒看华
- 修复后：2/43 失败（**WSJ 商业限速 + 机器之心 302 重定向 + 限流**，已知长期问题），489 items，外媒看华 1 条（Nikkei）
- 2 个顽固源是 **WSJ feed 限速** + **机器之心 302 + 高并发限流**，需要单独决策（改 Google News 替代 / 降配额 / 接受失联），不在本次"修失联"范围

### 排查命令
```bash
# 1. 看 mihomo 当前节点
curl -s http://127.0.0.1:9090/proxies/%F0%9F%8C%8D%20%E5%9B%BD%E5%A4%96%E5%AA%92%E4%BD%93 | python3 -c "import json,sys;d=json.load(sys.stdin);print('now:',d['proxies']['🌍 国外媒体']['now'])"

# 2. 模拟 fetch_all 的 43 并发
PYTHON_GIL=0 /usr/local/bin/python3.14t -c "
import asyncio,aiohttp
from trendradar.scripts.fetch_feeds import _get_sources
from trendradar.config.proxy import needs_proxy,PROXY_URL
async def run():
    sources=_get_sources(); ps=[(n,u,fd) for n,u,fd in sources if needs_proxy(u)]
    conn=aiohttp.TCPConnector(limit=43,limit_per_host=0,force_close=True)
    sem=asyncio.Semaphore(43)
    async with aiohttp.ClientSession(connector=conn,headers={'User-Agent':'Mozilla/5.0'},proxy=PROXY_URL,timeout=aiohttp.ClientTimeout(total=8)) as s:
        async def one(n,u):
            async with sem:
                try: async with s.get(u) as r: await r.read(); return (n,'OK')
                except Exception as e: return (n,f'FAIL {type(e).__name__}')
        rs=await asyncio.gather(*[one(n,u) for n,u,fd in ps])
        print('成功:', sum(1 for _,r in rs if r=='OK'),'/',len(rs))
        print('失败:', [n for n,r in rs if r!='OK'])
asyncio.run(run())
"

# 3. 验证 import 命中正确副本
PYTHON_GIL=1 /usr/local/bin/python3.14t -c "
import sys; sys.path.insert(0,'/home/asus/.hermes')
import trendradar.scripts.fetch_feeds as ff
print('loaded:', ff.__file__)
"
```

---

## 2026-06-05 顽固源诊断：feed 已停更/关闭（不是失联）

**症状**：修了 fetch 17 源失联后，剩 2 源仍 0 items。降级重试 HTTP 200 但 `_parse_rss` 返 0 条。

### 根因（与"失联"不同）
两源不是网络问题，是**上游 feed 已停更或关闭**：
1. **WSJ 商业** (`feeds.a.dj.com/rss/WSJcomUSBusiness.xml`)：feedparser 解析成功但 20 条全是 **2025-01-24** 旧文 → freshness 过滤全清空
2. **机器之心** (`https://www.jiqizhixin.com/rss`)：返回 HTML SPA 页面（网站改版后 `/rss` 路径跳到 `/data-service`），feedparser 0 entries

**诊断命令**（**必须先用 feedparser 验证**才改 sources.json）：
```python
import feedparser
d = feedparser.parse('<URL>')
print('entries:', len(d.entries), 'bozo:', d.get('bozo'))
# 看最近 entry 的发布时间
for e in d.entries[:3]:
    print(e.get('title'), e.get('published'))
```

### 修复
**两源都设 `enabled: false`**，由其他源覆盖：
- WSJ 商业 → WSJ 世界新闻已用 `site:wsj.com+when:1d` Google News 覆盖（`freshness_days=3`）
- 机器之心 → 中文 tech 域由 qbitai/36kr/ifanr/huxiu 承担

**保留源信息**（带 `_comment` 标记），方便以后观察 RSS 复活时恢复。

### UA 升级（顺带做）
`fetch_feeds.py` USER_AGENT 改为 `Reeder/5.2 MacOSX`：
- WSJ CDN (`a.dj.com`) 对浏览器 UA 限速 15s/req，对 RSS 阅读器 UA（Reeder/NetNewsWire/Inoreader）不限速
- 测试 5 个 UA 后确认 Reeder UA 对 BBC/Reuters/Bloomberg/澎湃/联合早报都无负面影响
- 等同于给所有源加了 RSS 客户端白名单

### 3 副本同步教训
- `sources.json` 之前 3 副本不同步（legacy 顶层 vs 嵌套真包 vs git worktree）—— patch 只改 1 个，另 2 个是孤儿
- 教训：所有 `*.json` 配置改动后必须 `md5sum` 三副本

---

## 2026-06-05 速度优化：23.9s → 7.6s 中位数

**症状**：fetch 41 源吃 23.9s（南华早报 2 次重试 × 8s timeout = 16s 占 67%）。

### 改动
1. **删 2 源**（WSJ 商业 / 机器之心，feed 已停更/关闭）→ 41 源
2. **`config/fetching.py`**: `TIMEOUT_SEC: 8→6`, `FETCH_RETRIES: 1→0`
3. **`fetch_feeds.py`**: `max_retries: 2→0`（与 FETCH_RETRIES 一致）
4. **`fetch_feeds.py`** 降级重试通道超时 `15s→10s`（5s 太短反而救不回慢源）

### 关键架构改动
**双层超时策略**：
- **Batch 内**：每源最多 1 次尝试，6s 超时上限 → 1 个慢源不会拖累 batch
- **降级通道**：失败的源串行用独立尝试 + 10s 超时救回（如 mihomo 节点瞬时抽风）

之前架构（max_retries=2 + TIMEOUT=8s）下，南华早报类慢源串行重试 16s 是固定成本。改成"1 次快速失败 + 独立通道重试"后，最坏情况 6+10=16s，但只有 1 个慢源时，且**其他 40 源不等它**（batch 独立 gather 完 1-2s 就结束，降级在 batch 之后串行）。

### 5 次实测
- 3.8s / 7.5s / 7.6s / 8.5s / 18.0s
- 中位数 7.6s（之前 23.9s，**~3x 提速**）
- 最坏 18.0s = mihomo 抽风 + 1-2 源走降级
- 5/5 都 41/41 源成功

### 经验
- `FETCH_RETRIES=0` + 降级通道 > `FETCH_RETRIES=2` 内联重试：失败源不被"绑在 batch 里慢慢重试"
- `TIMEOUT_SEC` 砍一刀反而**提高总体吞吐**：5s 内失败的源快速被降级通道救回，10s+ 才失败的源在 batch 阶段直接放弃
- 不要无脑给所有源宽松超时——**最慢源决定总时长**

---

## 2026-06-05 添加替代源：CNBC Finance + AI 前线 (InfoQ)

WSJ 商业（停更）和机器之心（RSS 关闭）删除后，**用 feedparser 验证候选 → 选 2 条替代**：

| 替代 | feed | 验证 | 配置 |
|---|---|---|---|
| **CNBC Finance** (WSJ 商业替代) | `https://www.cnbc.com/id/10000664/device/rss/rss.html` | HTTP 200 30 条，日更 1-2 条 | `freshness_days=2`, `needs_proxy=true`（CNBC 拒绝中国 IP），`authority=3` |
| **AI 前线 (InfoQ)** (机器之心替代) | `https://www.infoq.cn/feed.xml` | HTTP 200 20 条/6-05 18:xx 实时 | `authority=2`, `priority=1` |

**关键发现**：
- **CNBC 拒绝非美国/欧盟 IP**（直连 TimeoutError），必须走代理——**改 per-source 标记 `needs_proxy=true` 比改 URL 模式更稳**
- **CNBC Finance 日更 1-2 条/天**（类似 WSJ 商业），freshness=1 几乎 0 条，**必须设 2 天**

**测试流程铁律**（用 feedparser 验证后才加 sources.json）：
```python
import feedparser
d = feedparser.parse('URL')
print(f'entries: {len(d.entries)}')  # 必须 > 0
# 看最新 entry 时间
e = d.entries[0]
print(e.get('published'))  # 必须是新时间，不是 2019
```

5 次实测 43/43 全成功，CNBC=6/InfoQ=16 稳定。

---

## 2026-06-05 Per-source `needs_proxy` 字段（新增特性）

**需求**：某些源**只对部分 IP 区域限速**（如 CNBC 拒绝中国 IP、WSJ CDN 限速浏览器 UA）。全局 `DOMESTIC_PROXY_PATTERNS` 模式匹配不灵活——WSJ `a.dj.com` 已被代理组自动命中，但有时新源 URL 模式无法归类。

**实现**：`config/proxy.py` `needs_proxy()` 改为**先看 sources.json 显式标记**再回退到 URL 模式匹配：

```python
def needs_proxy(feed_url: str) -> bool:
    try:
        cfg_path = os.environ.get('TRENDRADAR_CONFIG_DIR', '/home/asus/.hermes/trendradar/config')
        import json as _json
        sources = _json.loads(open(f'{cfg_path}/sources.json').read()).get('data_sources', [])
        for s in sources:
            if s.get('feed_url', '').lower() == feed_url.lower() and 'needs_proxy' in s:
                return bool(s['needs_proxy'])
    except Exception:
        pass
    # URL 模式匹配（fallback）
    url_lower = feed_url.lower()
    for pattern in DOMESTIC_PROXY_PATTERNS:
        if pattern in url_lower:
            return False
    return True
```

**使用**：
```json
{
  "id": "cnbc_finance",
  "name": "CNBC 财经",
  "feed_url": "https://www.cnbc.com/id/10000664/device/rss/rss.html",
  "needs_proxy": true,
  ...
}
```

**优先级**：`needs_proxy` 显式标记 > URL 模式匹配。**显式 `false` 可强制源走直连**（即便 URL 看起来应该走代理）——例如某站有中国 CDN 镜像但 RSS 路径仍在外网域名。

**故障安全**：`try/except` 包裹 sources.json 读取，sources.json 损坏或字段缺失时**回退到原 URL 模式**——不破坏现有抓取。

**与 `freshness_days` 区别**：
- `freshness_days` 是**数据层**配置（影响哪些 entry 被纳入）
- `needs_proxy` 是**网络层**配置（影响走哪条连接路径）

## 2026-06-05 双层超时策略（可复用性能模式）

**问题**：单层超时无法兼顾"快"和"救回"。
- 太短（如 5s）：慢源永远救不回，被误判为失联
- 太长（如 15s × 2 重试）：1 个慢源拖整个 batch 30s+（其他 40 源不等它）

**双层超时架构**：
```
Batch gather (N 源并发)
   ├─ 源 A: 1s 成功
   ├─ 源 B: 6s 成功
   ├─ 源 C: TimeoutError → 标记失败
   └─ 源 D: ClientConnectorError → 标记失败

# batch 6s 后结束（取最慢源耗时）
# 但 A/B 不等 C/D —— gather 完成后 batch 立即返回

降级重试通道（串行，1 源接 1 源）
   ├─ 源 C: 10s 重试 → 成功
   └─ 源 D: 10s 重试 → 失败（接受）
```

**实现**（`fetch_feeds.py`）：
```python
# Batch 内：FETCH_RETRIES=0, TIMEOUT_SEC=6 → 失败源快速出列
max_retries = 0  # 配合 FETCH_RETRIES

# 降级重试：gather 后串行，10s 超时
async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
    ...
```

**实测效果**（41 源）：
- 旧（max_retries=2, TIMEOUT=8s）：23.9s 中位数
- 新（max_retries=0, TIMEOUT=6s + 10s 降级）：7.6s 中位数，**~3x 提速**
- 5/5 仍 41/41 成功（无成功率损失）

**关键洞察**：
1. **失败源不该绑在 batch 里慢慢重试**——其他源不等它
2. **降级通道用独立超时**——不影响 batch 的最坏耗时
3. **降级通道串行而非并发**——避免重试风暴打爆代理节点

**适用条件**：
- 抓取源数 N ≥ 10（太小看不出差别）
- 有清晰的代理/直连分流
- 部分源偶发失败但值得救（不是持续 0）

**何时不适用**：
- 所有源都同等重要（不能容忍任一源失败）→ 用回退方案 max_retries=2
- 网络极其稳定（mihomo/代理从未抽风）→ 单层 5s 足够

---

## 2026-06-05 User-Agent 升级为 RSS 阅读器 UA

详见 `references/source-management.md`「User-Agent 选择」节。简短结论：
- `Mozilla/5.0 (Windows NT 10.0; Win64; x64)` → 浏览器 UA，被 WSJ CDN 等识别为浏览器，触发限速
- `Reeder/5.2 MacOSX` → RSS 阅读器 UA，CDN 白名单内
- 5 个 UA 实测：Reeder/NetNewsWire 0.7-1.5s 200，浏览器 UA 15s 超时
- 适用所有 RSS 抓取场景，无副作用
