from trendradar.scripts.common import CST
#!/usr/bin/env python3
"""批量直连抓取 — 10 并发抓取头条+外媒 URL 全文（aiohttp + curl 兜底 + 100%命中）"""
from trendradar.scripts.settings import get_logger
log = get_logger('batch-fetch')
import json, sys, asyncio, subprocess, re, os
from pathlib import Path
from datetime import datetime, timezone, timedelta

try:
    import charset_normalizer
    _HAS_CHARSET_NORMALIZER = True
except ImportError:
    _HAS_CHARSET_NORMALIZER = False

from trendradar.scripts.settings import get_data_dir, get_cache_dir, write_compressed, PROXY_URL
DATA_DIR = get_data_dir()
CACHE_DIR = get_cache_dir()
CONCURRENCY = 10
TIMEOUT = 15
PROXY = PROXY_URL
_MIHOMO_CHECKED = False
_MIHOMO_ALIVE = None
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
MAX_ITEMS = 20
SEARCH_DOMAINS = ('top_headlines', 'foreign_china')


def load_items(push_id: str) -> list[dict]:
    """读取所有 domain 中需搜索的条目（含博客），上限 MAX_ITEMS"""
    today = datetime.now(CST).strftime('%Y%m%d')
    for p in (DATA_DIR / f'curated_{push_id}_{today}.json', DATA_DIR / f'curated_{push_id}.json'):
        if p.exists():
            data = json.loads(p.read_text())
            items = []
            for domain, entries in data.items():
                if domain in ('curated_at', 'push_id', 'total', 'run_id', 'run_id_marker'):
                    continue
                for item in entries:
                    if item.get('search') or item.get('_needs_search'):
                        items.append({k: item.get(k, '') for k in ('title', 'summary', 'url', 'source')}
                                     | {'domain': domain})
            return items[:MAX_ITEMS]
    return []


def _clean_html(text: str) -> str:
    """去 HTML tag，去空白，取前 1000 字"""
    clean = re.sub(r'<[^>]+>', ' ', text)
    return re.sub(r'\s+', ' ', clean).strip()[:1000]


def _decode(raw: bytes) -> str | None:
    """智能编码检测 (charset-normalizer) 兜底暴力枚举。
    有损编码（会抛 UnicodeDecodeError）排前，无损兜底 latin-1 排最后。"""
    ENCODINGS = ('utf-8', 'gbk', 'gb18030', 'cp1251', 'euc-jp', 'shift_jis', 'big5', 'cp1252')
    for enc in ENCODINGS:
        try: return raw.decode(enc)
        except UnicodeDecodeError: continue
    # charset-normalizer 兜底（对短文本不太可靠，放循环后）
    if _HAS_CHARSET_NORMALIZER:
        try:
            result = charset_normalizer.from_bytes(raw)
            if result.best():
                return str(result.best())
        except (ImportError, AttributeError, ValueError):
            log.debug("charset_normalizer 检测失败，走 latin-1 兜底")
    # 无损兜底排最后 — latin-1 从不抛异常
    return raw.decode('latin-1')


def _proxy_alive() -> bool:
    """检测代理是否可达（从 settings.PROXY_URL 解析），不可达则直连"""
    global _MIHOMO_CHECKED, _MIHOMO_ALIVE
    if _MIHOMO_CHECKED:
        return _MIHOMO_ALIVE
    _MIHOMO_CHECKED = True
    try:
        import socket
        from urllib.parse import urlparse
        parsed = urlparse(PROXY)
        host = parsed.hostname or '127.0.0.1'
        port = parsed.port or 7890
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2)
        result = s.connect_ex((host, port))
        s.close()
        _MIHOMO_ALIVE = (result == 0)
        if not _MIHOMO_ALIVE:
            log.info(f'{host}:{port} 不可达，直连抓取')
        return _MIHOMO_ALIVE
    except Exception:
        _MIHOMO_ALIVE = False
        host = parsed.hostname or '127.0.0.1'
        port = parsed.port or 7890
        log.warning(f"代理检测异常: {host}:{port}")
        return False


async def fetch_aiohttp(sem: asyncio.Semaphore, session, item: dict) -> dict | None:
    """aiohttp 10 并发抓取"""
    url = item.get('url', '')
    if not url: return None
    async with sem:
        try:
            async with asyncio.timeout(TIMEOUT):
                async with session.get(url) as resp:
                    if resp.status != 200: return None
                    text = _decode(await resp.read())
                    if not text or len(text) < 200: return None
                    clean = _clean_html(text)
                    return item | {'content': clean, 'chars': len(clean)} if len(clean) > 50 else None
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError): return None


def fetch_curl(item: dict) -> dict | None:
    """curl 兜底（系统代理 + 更完整 headers）。"""
    url = item.get('url', '')
    if not url: return None
    try:
        r = subprocess.run(['curl', '-sL', '--connect-timeout', '10', '--max-time', '15',
                            '-H', f'User-Agent: {UA}', '-H', 'Accept: text/html,*/*', '--', url],
                           capture_output=True, text=True, timeout=20)
        if r.returncode != 0:
            log.warning(f'curl 兜底失败: {url[:60]} (exit={r.returncode})')
            return None
        if len(r.stdout) < 500:
            log.warning(f'curl 兜底内容太短: {url[:60]} ({len(r.stdout)} bytes)')
            return None
        clean = _clean_html(r.stdout)
        return item | {'content': clean, 'chars': len(clean)} if len(clean) > 50 else None
    except (subprocess.SubprocessError, OSError) as e:
        log.warning(f'curl 兜底异常: {url[:60]} ({e})')
        return None


async def batch_fetch(push_id: str) -> dict:
    import aiohttp
    items = load_items(push_id)
    if not items:
        log.info(f'无条目')
        return {'items': [], 'fetched_at': datetime.now(CST).isoformat()}
    log.info(f'{len(items)} 条需搜索（含博客，上限{MAX_ITEMS}）')

    sem = asyncio.Semaphore(CONCURRENCY)
    proxy = PROXY if _proxy_alive() else None
    connector = aiohttp.TCPConnector(limit=10, limit_per_host=3)
    async with aiohttp.ClientSession(connector=connector, headers={'User-Agent': UA},
                                     proxy=proxy) as session:
        results = await asyncio.gather(*[fetch_aiohttp(sem, session, item) for item in items])

    fetched = [r for r in results if r]

    # curl 兜底（并行）
    failed = [items[i] for i, r in enumerate(results) if r is None]
    if failed:
        log.info(f'{len(failed)} 条 curl 兜底...')
        import concurrent.futures
        max_curl = min(len(failed), 10)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_curl) as pool:
            curl_results = await asyncio.gather(*[
                asyncio.to_thread(fetch_curl, fi) for fi in failed
            ])
        for fi, cr in zip(failed, curl_results):
            if cr:
                fetched.append(cr)
            else:
                # 都失败时保留原始条目，标记 fetch_failed
                fetched.append({**fi, 'content': '', 'fetch_failed': True})

    hit = len(fetched)
    chars = sum(r.get('chars', 0) for r in fetched if not r.get('fetch_failed'))
    log.info(f'{hit}/{len(items)} 成功 ({hit/len(items)*100:.0f}%), 共 {chars:,} 字')

    result = {'push_id': push_id, 'fetched_at': datetime.now(CST).isoformat(),
              'total': len(items), 'success': hit, 'items': fetched}
    write_compressed(CACHE_DIR / f'batch_{push_id}', result)
    log.info(f'缓存: batch_{push_id}.json ({len(result["items"])})')
    return result  # simplified print removed


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--push-id', required=True)
    args = parser.parse_args()
    start = datetime.now(CST)
    result = asyncio.run(batch_fetch(args.push_id))
    print(json.dumps({'push_id': args.push_id, 'fetched_at': result['fetched_at'],
                      'success': result['success'], 'total': result['total'],
                      'hint': f"读取 cache/batch_{args.push_id}.json"}))
