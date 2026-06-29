# AI 翻译 SHA-1 内容缓存（2026-06-03 实装）

## 目标

跨 slot 重复条目去重：同一篇 BBC/Reuters 文章在 morning / noon / evening 三次推送里出现，只调一次 DeepSeek，后两次直接读 cache。

## 实现

### 缓存 key 设计

```python
key = f"{_content_hash(t)}|{_content_hash(s)}|{source_lang or 'auto'}"
```

- **title hash** + **summary hash** + **source_lang**
- title 和 summary 都做 `strip().lower()` 归一化
- SHA-1 截前 16 字符（防 collision 仍然 2^64 安全）
- source_lang 让 "Chinese → English" 和 "English → Chinese" 不串

### Lazy 路径初始化

```python
_CACHE_PATH = None  # 模块级 lazy

def _get_cache_path():
    global _CACHE_PATH
    if _CACHE_PATH is None:
        from trendradar.scripts.settings import get_cache_dir
        _CACHE_PATH = get_cache_dir() / 'translate_cache.json'
    return _CACHE_PATH
```

**为什么 lazy**：import 时强制读 disk 在测试环境下会失败（test runner 用 mocked cache_dir）。Lazy 推到首次 `process_batches` 调用时，届时 settings 已完全初始化。

### 原子写（避免半截 JSON）

```python
def _save_cache(cache: dict):
    p = _get_cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix='.tc_')
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, p)
```

**为什么 atomic**：cron 跑 9/12/21 三次，中断风险非零（OOM / SIGKILL）。`os.replace` 是 POSIX atomic rename，要么看到旧 cache，要么看到新 cache，不可能半截。

### batch 内合并逻辑

```python
# process_one_batch 内部
cache = _load_cache()
cached_results = []   # [(orig_idx, cached_translation), ...]
uncached_indices = [] # [orig_idx, ...]

for i, (t, s) in enumerate(pairs):
    key = f"..."
    if key in cache:
        cached_results.append((i, cache[key]))
    else:
        uncached_indices.append(i)

if not uncached_indices:
    # 100% cache hit — skip API entirely
    results = [cache[f"{_content_hash(t)}|{_content_hash(s)}|{source_lang or 'auto'}"]
               for t, s in pairs]
    log.info(f"cache hit {len(pairs)}/{len(pairs)} (skipped API)")
    return (batch, results, None)

# partial hit: only send uncached to API
uncached_pairs = [pairs[i] for i in uncached_indices]
api_results = await batch_func(items=uncached_pairs, ...)

# write back to cache
for (t, s), res in zip(uncached_pairs, api_results):
    cache[f"{_content_hash(t)}|{_content_hash(s)}|{source_lang or 'auto'}"] = res
if uncached_indices:
    _save_cache(cache)

# reassemble in original order
results = [None] * len(pairs)
for orig_i, res in cached_results:
    results[orig_i] = res
for uncached_i, res in zip(uncached_indices, api_results):
    results[uncached_i] = res
```

## 实测性能（3 back-to-back morning runs，30 items，5 foreign）

| 场景 | push_prepare | ai_translate | TOTAL | 加速比 |
|------|:---:|:---:|:---:|:---:|
| 冷 cache + 冷 fetch | 1.5s | 7.0s | **9.2s** | 2.6× |
| 暖 cache + 冷 fetch | 1.8s | 4.5s | **6.1s** | 3.9× |
| 暖 cache + 暖 fetch | 0.1s | 1.7s | **2.9s** | **8.3×** |

**实战影响**：cron 9/12/21 三次推送共享 60-80% 条目。早报写满 cache → 午/晚报 ai_translate 砍到 <2s。

## 测试 setUp 必清 cache

边界测试用 mock batch_func 测**调用次数**，cache 命中会让 batch_func 0 次调用，断言 `call_count == 2` 挂掉。**必须** setUp 清 cache：

```python
class TestBatchTranslateAllBatching:
    def setup_method(self, method):
        from ai_translate import _get_cache_path
        p = _get_cache_path()
        if p.exists():
            p.unlink()
```

**坑**：第一次写测试忘了 setup_method，看到 `assert 0 == 2` 错误还以为是 batch_func 逻辑错。查 30 分钟才发现是 cache 短路。

## 缓存击穿（cache avalanche）风险评估

**风险**：如果 24h 内没有调用，cache 文件会保留所有历史条目，可能达到几 MB 体积。但本项目 cache key 维度低（title + summary + lang），实际累积 < 50KB/天，不需要 LRU/TTL 清理。

**未来如果 cache > 10MB**：加 `max_size=10000` LRU 限制 + 30 天 TTL。

## 相关坑

- **JSON 中文 `ensure_ascii=False`**：必须设，否则 `json.dump` 会把中文转 `\uXXXX`，文件大 3×，读时还要 decode
- **dict key 顺序**：Python 3.7+ dict 是 ordered，但 `json.dump` 默认按 key 排序。改 key 顺序不会破坏 lookup，但 git diff 会乱——加 `sort_keys=False`
- **Empty cache**：首次调用 `cache = {}`，`cache.get(key)` 返回 None，正确走 uncached 路径
