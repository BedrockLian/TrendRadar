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
