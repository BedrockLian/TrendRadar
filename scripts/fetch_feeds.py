#!/usr/bin/env python3
"""TrendRadar 采集员 — 46个RSS源多线程并行抓取（ThreadPoolExecutor + urllib 同步版）

针对标准 Python 3.14 (GIL=ON) 优化：移除 aiohttp/asyncio，改用 ThreadPoolExecutor。
I/O bound 任务在 GIL=ON 下多线程本就能并行执行 HTTP 请求，
消除 asyncio 单线程事件循环的隐式串行化开销。
"""
from trendradar.scripts.settings import get_logger
log = get_logger('fetch-feeds')
import json, re, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
import urllib.request
import urllib.error
import concurrent.futures
import threading
from trendradar.config.keywords import has_keyword_match_ci
import feedparser

from trendradar.scripts.common import CST, Lazy

from trendradar.scripts.settings import get_data_dir, get_cache_dir, get_config_dir, write_compressed
from trendradar.scripts.settings import EXTERNAL_CONCURRENT, TIMEOUT_SEC
from trendradar.scripts.settings import PROXY_URL, needs_proxy, check_proxy_alive
DATA_DIR = get_data_dir()
CACHE_DIR = get_cache_dir()

USER_AGENT = 'Reeder/5.2 MacOSX'
RSS_FRESHNESS_MAX_AGE_DAYS = 1  # 全局默认，单源可在 sources.json 中覆盖 freshness_days

# ── proxy opener 缓存（线程安全：每个线程创建自己的 opener） ──
_proxy_opener_lock = threading.Lock()
_proxy_opener = None

def _get_proxy_opener():
    """获取带代理的 urllib opener（懒初始化，线程安全）"""
    global _proxy_opener
    if _proxy_opener is None:
        with _proxy_opener_lock:
            if _proxy_opener is None:
                proxy_handler = urllib.request.ProxyHandler({
                    'http': PROXY_URL,
                    'https': PROXY_URL,
                })
                _proxy_opener = urllib.request.build_opener(proxy_handler)
    return _proxy_opener


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
    """解析 RSS/Atom/RDF — feedparser 统一处理"""
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
                parsed_u = urlparse(link)
                safe_path = quote(parsed_u.path, safe='/:@!$&\'()*+,;=-._~')
                if safe_path != parsed_u.path:
                    link = urlunparse(parsed_u._replace(path=safe_path))
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


def _fetch_one(name: str, url: str, freshness_days: int = 1, use_proxy: bool = False) -> tuple[str, list]:
    """同步抓取+解析单个 RSS 源（在线程池中并行运行）

    Returns: (name, items_list)
    """
    data = ""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        if use_proxy:
            opener = _get_proxy_opener()
            resp = opener.open(req, timeout=TIMEOUT_SEC)
        else:
            resp = urllib.request.urlopen(req, timeout=TIMEOUT_SEC)
        data = resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        log.warning(f'{name}: {type(e).__name__}: {str(e)[:80]}')
        return name, []

    if not data:
        return name, []

    items = _parse_rss(data, name, 25, freshness_days)
    return name, items


def _fetch_one_with_retry(name: str, url: str, freshness_days: int = 1,
                          use_proxy: bool = False) -> tuple[str, list]:
    """带降级重试的抓取（type annot 兼容旧接口）"""
    name_result, items = _fetch_one(name, url, freshness_days, use_proxy)
    return name_result, items


def fetch_all(push_id: str = '') -> dict:
    """多线程并行抓取所有 RSS 源 + 热度追踪

    使用 ThreadPoolExecutor 实现真正的多线程并发。
    在标准 Python 3.14 (GIL=ON) 下 I/O bound 任务可并行执行 HTTP 请求。
    """
    sources = _get_sources()

    # 分流：国内源直连，外媒源走代理
    direct_sources = [(n, u, fd) for n, u, fd in sources if not needs_proxy(u)]
    proxy_sources = [(n, u, fd) for n, u, fd in sources if needs_proxy(u)]

    # 代理健康检查
    proxy_ok = check_proxy_alive()
    if not proxy_ok and proxy_sources:
        log.warning(f'代理 {PROXY_URL} 不可用！{len(proxy_sources)} 个外媒源将全部失败')
        direct_sources.extend(proxy_sources)
        proxy_sources = []

    # 主动切到延迟最低的节点
    if proxy_ok and proxy_sources:
        from trendradar.config.proxy import select_node_for_fetch, current_node
        before = current_node() or '(unknown)'
        after = select_node_for_fetch(reason=f'pre-fetch {push_id or "manual"}')
        if after and after != before:
            log.info(f'节点: {before} → {after}')
        elif before and before != '(unknown)':
            log.info(f'节点: 保持 {before}（{after or "无可用历史"}）')

    print(f'[FETCH] {len(sources)}源（直连 {len(direct_sources)} + 代理 {len(proxy_sources)}）')

    all_results: dict[str, list] = {}
    failed: list[tuple[str, str, int, bool]] = []  # (name, url, fd, use_proxy)

    # Phase 1: 主批次并行抓取
    with concurrent.futures.ThreadPoolExecutor(max_workers=EXTERNAL_CONCURRENT) as executor:
        futures: dict[concurrent.futures.Future, str] = {}

        for name, url, fd in direct_sources:
            f = executor.submit(_fetch_one, name, url, fd, False)
            futures[f] = name
        for name, url, fd in proxy_sources:
            f = executor.submit(_fetch_one, name, url, fd, True)
            futures[f] = name

        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                result_name, items = future.result()
                all_results[result_name] = items
                if not items:
                    # 标记失败源用于降级重试
                    src = next((s for s in sources if s[0] == result_name), None)
                    if src:
                        failed.append((src[0], src[1], src[2], needs_proxy(src[1])))
            except Exception as e:
                log.error(f'{name}: {type(e).__name__}: {e}')
                all_results[name] = []
                src = next((s for s in sources if s[0] == name), None)
                if src:
                    failed.append((src[0], src[1], src[2], needs_proxy(src[1])))

    # Phase 2: 降级重试失败源（独立线程池，小批次）
    if failed:
        log.info(f'降级重试 {len(failed)} 个失败源')
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(failed))) as executor:
            retry_futures = {}
            for name, url, fd, use_proxy in failed:
                f = executor.submit(_fetch_one, name, url, fd, use_proxy)
                retry_futures[f] = name

            for future in concurrent.futures.as_completed(retry_futures):
                name = retry_futures[future]
                try:
                    result_name, items = future.result()
                    if items:
                        all_results[result_name] = items
                        log.info(f'  降级 {result_name}: 成功 ({len(items)} 条)')
                    else:
                        log.info(f'  降级 {result_name}: 解析得 0 条（feed 空或全过老）')
                except Exception as e:
                    log.info(f'  降级 {name}: 失败 {type(e).__name__}: {str(e)[:80]}')

    failures = sum(1 for v in all_results.values() if not v)
    if failures:
        log.info(f'{failures}源失败')

    # 收集失败源清单
    failed_sources = sorted([name for name, items in all_results.items() if not items])

    # 去重 + 预分类
    merged = _dedup(all_results)
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
            'failed_sources': failed_sources,
            'proxy_url': PROXY_URL,
            'fetch_time': datetime.now(CST).isoformat()}


def _dedup(all_results: dict[str, list]) -> list:
    """跨平台去重合并（按标题前 40 字符，保留序）。

    Sprint 3 perf: 直接接受 all_results dict (platform→items), 避免调用侧 listcomp 全量拷贝。
    """
    seen: dict[str, dict] = {}
    for platform, items in all_results.items():
        for item in items:
            item['source_platform'] = platform
            domain = urlparse(item.get('url', '')).netloc
            key = f"{item['title'][:40].lower()}||{domain}"
            if key not in seen:
                item |= {'_coverage_count': 1, '_coverage_platforms': {platform}}
                seen[key] = item
            else:
                ex = seen[key]
                if platform and platform not in ex.get('_coverage_platforms', set()):
                    ex['_coverage_count'] += 1
                    ex.setdefault('_coverage_platforms', set()).add(platform)
                    ex['summary'] = f"[{ex['source_platform']}] {ex['summary']} // [{platform}] {item['summary']}"
                    ex.setdefault('url', item['url'])
                    ex['source_platform'] = f"{ex['source_platform']}+{platform}"
    for item in seen.values():
        if '_coverage_platforms' in item:
            item['_coverage_platforms'] = list(item['_coverage_platforms'])
    return list(seen.values())


def _load_kw_sets():
    """内部: 实际加载逻辑"""
    from trendradar.config.keywords import GAME_KW, TECH_KW, ECONOMY_KW
    return (GAME_KW, TECH_KW, ECONOMY_KW)

_KW_SETS = Lazy(_load_kw_sets)


def _kw_sets():
    return _KW_SETS.get()


def _load_source_category_map() -> dict:
    cfg = _load_config()
    return {s.get('name', ''): s.get('category', '')
            for s in cfg.get('data_sources', []) if s.get('name')}

_SRC_CAT_MAP = Lazy(_load_source_category_map)


def _source_category_map() -> dict[str, str]:
    return _SRC_CAT_MAP.get()


def _preclassify(items: list) -> list:
    """预分类：关键词 + 源 category 兜底 + 源级覆盖。"""
    G, T, E = _kw_sets()
    src_cat = _source_category_map()
    domains = [(G, 'gaming'), (T, 'tech'), (E, 'economy')]

    SOURCE_DOMAIN_OVERRIDE = {}

    for item in items:
        platform = item.get('source_platform', '')

        override = SOURCE_DOMAIN_OVERRIDE.get(platform)
        if override:
            item['_likely_domain'] = override
            continue

        text = f"{item.get('title', '')} {item.get('summary', '')}"

        _game_false_positives = frozenset({'改变游戏规则', 'ゲームチェンジ'})
        if has_keyword_match_ci(text, 'game', _game_false_positives):
            pass
        else:
            domain = next((d for kw, d in domains
                           if has_keyword_match_ci(text, d, kw)), None)
            if domain:
                item['_likely_domain'] = domain
                continue

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
    print(f'[{start:%H:%M:%S}] 开始多线程抓取...')
    result = fetch_all(args.push_id)

    today = datetime.now(CST).strftime('%Y%m%d')
    write_compressed(CACHE_DIR / f'raw_{today}', result)

    items = result['items']
    d = {dom: sum(1 for i in items if i.get('_likely_domain') == dom)
         for dom in ('gaming', 'tech', 'economy', 'top_headlines', 'other')}
    elapsed = (datetime.now(CST) - start).total_seconds()
    print(f'[{datetime.now(CST):%H:%M:%S}] 完成: {len(items)}条 '
          f'(g:{d["gaming"]} t:{d["tech"]} e:{d["economy"]} h:{d["top_headlines"]} o:{d["other"]}) {elapsed:.1f}s')
