#!/usr/bin/env python3
"""TrendRadar 采集员 — 35个RSS源异步并行抓取（统一 TaskGroup + 3.14 异步优化版）"""
from trendradar.scripts.settings import get_logger
log = get_logger('fetch-feeds')
import json, re, sys, asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
import threading
from trendradar.config.keywords import has_keyword_match_ci
import feedparser
import aiohttp
import concurrent.futures
from trendradar.scripts.common import Lazy

def _make_parse_pool():
    # InterpreterPoolExecutor (3.14) can't pickle args in free-threaded mode
    # (NotShareableError under PYTHON_GIL=0). ThreadPoolExecutor is portable
    # and parse_rss is mostly I/O-bound, so the worker count is the limiter.
    return concurrent.futures.ThreadPoolExecutor(max_workers=24)

_PARSE_POOL = Lazy(_make_parse_pool)

from trendradar.scripts.common import CST

from trendradar.scripts.settings import get_data_dir, get_cache_dir, get_config_dir, write_compressed
from trendradar.scripts.settings import EXTERNAL_CONCURRENT, TIMEOUT_SEC
from trendradar.scripts.settings import PROXY_URL, needs_proxy, check_proxy_alive
DATA_DIR = get_data_dir()
CACHE_DIR = get_cache_dir()

USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'
RSS_FRESHNESS_MAX_AGE_DAYS = 1  # 全局默认，单源可在 sources.json 中覆盖 freshness_days


_CONFIG = Lazy(lambda: json.loads((get_config_dir() / 'sources.json').read_text()))

def _load_config() -> dict:
    """缓存 sources.json 读取（__main__ 多次调用时复用）"""
    return _CONFIG.get()


def _get_sources() -> list[tuple[str, str, int]]:
    """返回 [(name, feed_url, freshness_days), ...]"""
    config = _load_config()
    return [(s['name'], s['feed_url'],
             s.get('freshness_days', RSS_FRESHNESS_MAX_AGE_DAYS))
            for s in config.get('data_sources', [])
            if s.get('type') == 'rss' and s.get('feed_url') and s.get('enabled', True)]


def _parse_rss(data: str, platform: str, max_items: int, freshness_days: int = RSS_FRESHNESS_MAX_AGE_DAYS) -> list:
    """解析 RSS/Atom/RDF — feedparser 统一处理（CPU密集型，线程池中运行）"""
    items = []
    try:
        parsed = feedparser.parse(data)
        cutoff = datetime.now(timezone.utc) - timedelta(days=freshness_days) if freshness_days > 0 else datetime.min.replace(tzinfo=timezone.utc)

        for entry in parsed.entries[:max_items]:
            title = (getattr(entry, 'title', '') or '').strip()
            link = (getattr(entry, 'link', '') or '').strip()
            # URL 编码：某些 RSS 的路径含空格（如 Sixth Tone）
            if link and ' ' in link:
                from urllib.parse import urlparse, urlunparse, quote
                parsed = urlparse(link)
                safe_path = quote(parsed.path, safe='/:@!$&\'()*+,;=-._~')
                if safe_path != parsed.path:
                    link = urlunparse(parsed._replace(path=safe_path))
            if not title and not link:
                continue

            # 摘要：优先 summary，回退 description / content
            raw = (getattr(entry, 'summary', None)
                   or getattr(entry, 'description', None)
                   or (entry.content[0].value if getattr(entry, 'content', None) and len(entry.content) > 0 else None)
                   or '')
            summary = re.sub(r'<[^>]+>', '', raw)[:300].strip()

            # 时间戳：feedparser 内置解析（published_parsed / updated_parsed）
            ts_struct = getattr(entry, 'published_parsed', None) or getattr(entry, 'updated_parsed', None)
            if ts_struct:
                ts_dt = datetime(*ts_struct[:6], tzinfo=timezone.utc)
                ts = ts_dt.isoformat()
                # 新鲜度过滤
                if ts_dt < cutoff:
                    continue
            else:
                ts = datetime.now(CST).isoformat()

            items.append(dict(
                title=title, summary=summary, source_platform=platform,
                hot_rank=len(items) + 1, url=link, timestamp=ts, event_type='fermenting'
            ))
    except Exception as e:
        log.warning(f'RSS解析失败 {platform}: {e}')
    return items


async def _fetch_one(session: aiohttp.ClientSession, name: str, url: str,
                     sem: asyncio.Semaphore, freshness_days: int = 1) -> tuple[str, list]:
    """抓取+解析单个 RSS 源，错误内部消化（带重试）"""
    max_retries = 2
    data = ""
    for attempt in range(max_retries + 1):
        async with sem:
            try:
                async with asyncio.timeout(TIMEOUT_SEC):
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.text()
                            break
                        elif attempt < max_retries:
                            log.warning(f'{name}: HTTP {resp.status} (重试 {attempt+1}/{max_retries})')
                            await asyncio.sleep(1 * (2 ** attempt))
                            continue
                        else:
                            return name, []
            except (asyncio.TimeoutError, aiohttp.ClientError) as e:
                if attempt < max_retries:
                    log.warning(f'{name}: {type(e).__name__} (重试 {attempt+1}/{max_retries})')
                    await asyncio.sleep(1)
                    continue
                log.warning(f'{name}: {type(e).__name__}')
                return name, []
    if not data:
        return name, []
    max_items = 25
    loop = asyncio.get_running_loop()
    items = await loop.run_in_executor(_PARSE_POOL.get(), _parse_rss, data, name, max_items, freshness_days)
    return name, items


async def fetch_all(push_id: str = '') -> dict:
    """统一 TaskGroup 并行抓取 + 热度追踪"""
    sources = _get_sources()

    # 分流：国内源直连，外媒源走米霍姆代理
    direct_sources = [(n, u, fd) for n, u, fd in sources if not needs_proxy(u)]
    proxy_sources = [(n, u, fd) for n, u, fd in sources if needs_proxy(u)]

    # 代理健康检查
    proxy_ok = check_proxy_alive()
    if not proxy_ok and proxy_sources:
        log.warning(f'代理 {PROXY_URL} 不可用！{len(proxy_sources)} 个外媒源将全部失败（WSL 直连互联网不可用）')
        # 降级：把 proxy_sources 也走直连尝试（虽然会失败，但至少明确记录原因）
        direct_sources.extend(proxy_sources)
        proxy_sources = []

    print(f'[FETCH] {len(sources)}源（直连 {len(direct_sources)} + 代理 {len(proxy_sources)}）')

    sem = asyncio.Semaphore(EXTERNAL_CONCURRENT)

    async def _fetch_batch(source_group: list, session):
        tasks = []
        names = []
        for n, u, fd in source_group:
            tasks.append(_fetch_one(session, n, u, sem, fd))
            names.append(n)
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)
        result: dict[str, list] = {}
        for name, outcome in zip(names, raw_results):
            if isinstance(outcome, Exception):
                log.error(f'{name}: {outcome.__class__.__name__}: {outcome}')
                result[name] = []
            elif isinstance(outcome, tuple) and len(outcome) == 2:
                result[outcome[0]] = outcome[1]
            else:
                result[name] = outcome if isinstance(outcome, list) else []
        return result

    # 直连 + 代理并行两批
    tout = aiohttp.ClientTimeout(total=30)
    direct_conn = aiohttp.TCPConnector(limit=43, limit_per_host=0, force_close=True)
    proxy_conn = aiohttp.TCPConnector(limit=43, limit_per_host=0, force_close=True)
    async with (
        aiohttp.ClientSession(connector=direct_conn,
                              headers={'User-Agent': USER_AGENT},
                              timeout=tout) as direct_session,
        aiohttp.ClientSession(connector=proxy_conn,
                              headers={'User-Agent': USER_AGENT},
                              proxy=PROXY_URL,
                              timeout=tout) as proxy_session,
    ):
        direct_task = _fetch_batch(direct_sources, direct_session)
        proxy_task = _fetch_batch(proxy_sources, proxy_session)
        direct_results, proxy_results = await asyncio.gather(direct_task, proxy_task)

    all_results = {**direct_results, **proxy_results}
    failures = sum(1 for v in all_results.values() if not v)
    if failures:
        log.info(f'{failures}源失败')

    # 去重 + 预分类
    merged = _dedup([{**item, 'source_platform': p} for p, items in all_results.items() for item in items])
    merged = _preclassify(merged)

    # 热度追踪 + 预附 heat_info
    try:
        import trendradar.scripts.heat_tracker as ht
        stats = ht.update_tracker(merged, push_id)
        hi = ht.get_heat_info(merged)
        for item in merged:
            if (fp := ht.make_fingerprint(item.get('title', ''), item.get('url', ''))) in hi:
                item['_heat'] = hi[fp]
        print(f'[HEAT] 新增{stats["new"]}条 更新{stats["updated"]}条 共{stats["total_active"]}活跃')
    except Exception as e:
        log.warning(f'热度追踪失败: {e}')

    return {'items': merged, 'platform_stats': {p: len(it) for p, it in all_results.items()},
            'fetch_time': datetime.now(CST).isoformat()}


def _dedup(items: list) -> list:
    """跨平台去重合并（按标题前 40 字符，保留序）。

    Returns: 去重后列表，含 _coverage_count 和 _coverage_platforms。
    """
    seen: dict[str, dict] = {}
    for item in items:
        domain = urlparse(item.get('url', '')).netloc
        key = f"{item['title'][:40].lower()}||{domain}"
        if key not in seen:
            item |= {'_coverage_count': 1, '_coverage_platforms': {item.get('source_platform', '')}}
            seen[key] = item
        else:
            ex = seen[key]
            p = item.get('source_platform', '')
            if p and p not in ex.get('_coverage_platforms', set()):
                ex['_coverage_count'] += 1
                ex.setdefault('_coverage_platforms', set()).add(p)
                ex['summary'] = f"[{ex['source_platform']}] {ex['summary']} // [{p}] {item['summary']}"
                ex.setdefault('url', item['url'])
                ex['source_platform'] = f"{ex['source_platform']}+{p}"
    for item in seen.values():
        if '_coverage_platforms' in item:
            item['_coverage_platforms'] = list(item['_coverage_platforms'])
    return list(seen.values())


_KW_SETS_LOCK = threading.Lock()
_KW_SETS_VAL = None
_KW_SETS_SENTINEL = object()

def _kw_sets():
    """Returns (GAME_KW, TECH_KW, ECONOMY_KW) from trendradar.config.keywords."""
    global _KW_SETS_VAL
    if _KW_SETS_VAL is not None:
        return _KW_SETS_VAL
    with _KW_SETS_LOCK:
        if _KW_SETS_VAL is not None:
            return _KW_SETS_VAL
        from trendradar.config.keywords import GAME_KW, TECH_KW, ECONOMY_KW
        _KW_SETS_VAL = (GAME_KW, TECH_KW, ECONOMY_KW)
        return _KW_SETS_VAL


_SRC_CAT_MAP_LOCK = threading.Lock()
_SRC_CAT_MAP_VAL = None
_SRC_CAT_MAP_SENTINEL = object()

def _source_category_map() -> dict[str, str]:
    """所有源 → category 映射。用于预分类兜底。"""
    global _SRC_CAT_MAP_VAL
    if _SRC_CAT_MAP_VAL is not None:
        return _SRC_CAT_MAP_VAL
    with _SRC_CAT_MAP_LOCK:
        if _SRC_CAT_MAP_VAL is not None:
            return _SRC_CAT_MAP_VAL
        cfg = _load_config()
        _SRC_CAT_MAP_VAL = {s.get('name', ''): s.get('category', '')
                            for s in cfg.get('data_sources', []) if s.get('name')}
        return _SRC_CAT_MAP_VAL


def _preclassify(items: list) -> list:
    """预分类：关键词 + 源 category 兜底 + 源级覆盖。"""
    G, T, E = _kw_sets()
    src_cat = _source_category_map()
    domains = [(G, 'gaming'), (T, 'tech'), (E, 'economy')]
    
    # 源级域覆盖 — 特定源固定分配到某个域（不参与关键词匹配）
    SOURCE_DOMAIN_OVERRIDE = {}
    
    for item in items:
        platform = item.get('source_platform', '')
        
        # 源级覆盖优先
        override = SOURCE_DOMAIN_OVERRIDE.get(platform)
        if override:
            item['_likely_domain'] = override
            continue
        
        text = f"{item.get('title', '')} {item.get('summary', '')}"
        
        # 游戏关键词假阳性过滤
        _game_false_positives = frozenset({'改变游戏规则', 'ゲームチェンジ'})
        if has_keyword_match_ci(text, 'game', _game_false_positives):
            # 假阳性命中 → 跳过 gaming 关键词匹配，走兜底
            pass
        else:
            domain = next((d for kw, d in domains
                           if has_keyword_match_ci(text, d, kw)), None)
            if domain:
                item['_likely_domain'] = domain
                continue
        
        # 关键词未命中或假阳性 → 按源 category 兜底
        cat = src_cat.get(platform, '')
        if cat == 'game':
            item['_likely_domain'] = 'gaming'
        elif cat in ('tech', 'economy'):
            item['_likely_domain'] = cat
        elif cat in ('news', 'foreign_china'):
            item['_likely_domain'] = 'top_headlines'
        else:
            item['_likely_domain'] = 'other'
    return items


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--push-id', required=True)
    args = parser.parse_args()

    start = datetime.now(CST)
    print(f'[{start:%H:%M:%S}] 开始异步抓取...')
    result = asyncio.run(fetch_all(args.push_id))
    # write raw cache with date key (matches push_prepare.py ensure_raw_exists expectation)
    from datetime import datetime
    from trendradar.scripts.common import CST
    today = datetime.now(CST).strftime('%Y%m%d')
    write_compressed(CACHE_DIR / f'raw_{today}', result)

    items = result['items']
    d = {dom: sum(1 for i in items if i.get('_likely_domain') == dom) for dom in ('gaming', 'tech', 'economy', 'top_headlines', 'other')}
    elapsed = (datetime.now(CST) - start).total_seconds()
    print(f'[{datetime.now(CST):%H:%M:%S}] 完成: {len(items)}条 '
           f'(g:{d["gaming"]} t:{d["tech"]} e:{d["economy"]} h:{d["top_headlines"]} o:{d["other"]}) {elapsed:.1f}s')
