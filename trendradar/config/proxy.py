"""TrendRadar 代理配置。"""
import os

PROXY_URL = os.environ.get('TRENDRADAR_PROXY', 'http://127.0.0.1:7890')

DOMESTIC_PROXY_PATTERNS = (
    'plink.anyfeeder.com',
    '.cn',
    '.com.cn',
    'bbc.co.uk',
    'bbci.co.uk',
)


def needs_proxy(feed_url: str) -> bool:
    """判断 RSS 源是否需要走代理。"""
    url_lower = feed_url.lower()
    for pattern in DOMESTIC_PROXY_PATTERNS:
        if pattern in url_lower:
            return False
    return True


def check_proxy_alive(timeout: float = 2.0) -> bool:
    """检查代理是否可用（TCP 连接测试）。"""
    import socket
    from urllib.parse import urlparse
    parsed = urlparse(PROXY_URL)
    host = parsed.hostname or '127.0.0.1'
    port = parsed.port or 7890
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (socket.timeout, socket.error, OSError):
        return False


# ── Mihomo node auto-selection ────────────────────────────────────────────────
# mihomo (Clash Meta) runs as system proxy on this host. Its url-test group
# 🌍 国外媒体 auto-picks a node every 5min by probing gstatic.com — but
# gstatic.com latency is not representative of RSS server latency. So we
# pre-pick a node before each fetch using mihomo's own history of past
# probes (more realistic, no extra network cost).
#
# mihomo API: http://127.0.0.1:9090 (HTTP control port)
MIHOMO_API = os.environ.get('MIHOMO_API', 'http://127.0.0.1:9090')
MIHOMO_GROUP = os.environ.get('MIHOMO_GROUP', '🌍 国外媒体')

# Real proxy types per mihomo (URLTest/Selector/... are group types, skip)
REAL_PROXY_TYPES = frozenset({
    'AnyTLS', 'Trojan', 'VMess', 'VMessAEAD', 'VLESS', 'Hysteria',
    'Hysteria2', 'Shadowsocks', 'ShadowsocksR', 'SOCKS', 'SOCKS5', 'HTTP',
})

# Group name fragments to skip (selectors, not real nodes)
_SKIP_FRAGMENTS = ('节点选择', '自动选择', '全球直连', '国外媒体', '漏网之鱼', '微软服务')


def _mihomo_get(path: str, timeout: float = 2.0):
    """GET request to mihomo external-controller API. Returns parsed JSON or None."""
    import json
    import urllib.request
    try:
        with urllib.request.urlopen(f'{MIHOMO_API}{path}', timeout=timeout) as r:
            return json.loads(r.read())
    except Exception:
        return None


def _mihomo_put(path: str, body: dict, timeout: float = 2.0) -> bool:
    """PUT request to mihomo API. Returns True on success."""
    import json
    import urllib.request
    try:
        data = json.dumps(body).encode('utf-8')
        req = urllib.request.Request(
            f'{MIHOMO_API}{path}', data=data, method='PUT',
            headers={'Content-Type': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def pick_best_node(top_n: int = 5) -> str | None:
    """Pick the node with lowest avg latency from mihomo history.

    Returns the node name or None if mihomo is unavailable / no candidates.
    Does NOT switch the group — just identifies the best candidate.
    """
    d = _mihomo_get('/proxies')
    if not d or 'proxies' not in d:
        return None
    proxies = d['proxies']
    group = proxies.get(MIHOMO_GROUP, {})
    candidates = group.get('all', [])
    if not candidates:
        return None

    # Build (name, avg_delay) list, sorted ascending
    scored = []
    for name in candidates:
        if name in ('DIRECT', 'REJECT'):
            continue
        if any(frag in name for frag in _SKIP_FRAGMENTS):
            continue
        node = proxies.get(name, {})
        if node.get('type') not in REAL_PROXY_TYPES:
            continue
        hist = node.get('history', [])
        if not hist:
            continue
        delays = [h.get('delay', 0) for h in hist if h.get('delay', 0) > 0]
        if not delays:
            continue
        scored.append((name, sum(delays) / len(delays)))

    if not scored:
        return None
    scored.sort(key=lambda x: x[1])
    return scored[0][0]


def select_node_for_fetch(reason: str = '') -> str | None:
    """Pick the best node + switch the mihomo group to it.

    Returns the node name now active, or None on failure.
    Best-effort: if mihomo is unavailable, returns None without error.
    """
    from trendradar.scripts.logging_config import get_logger
    log = get_logger(__name__)
    best = pick_best_node()
    if not best:
        log.debug(f'mihomo: no candidate nodes found (reason={reason})')
        return None
    # Switch the group
    from urllib.parse import quote
    encoded = quote(MIHOMO_GROUP, safe='')
    ok = _mihomo_put(f'/proxies/{encoded}', {'name': best})
    if ok:
        log.info(f'mihomo: 🌍 国外媒体 → {best} ({reason})')
        return best
    log.warning(f'mihomo: failed to switch to {best}')
    return None


def current_node() -> str | None:
    """Return the currently selected node for the 国外媒体 group, or None."""
    d = _mihomo_get('/proxies')
    if not d or 'proxies' not in d:
        return None
    return d['proxies'].get(MIHOMO_GROUP, {}).get('now')
