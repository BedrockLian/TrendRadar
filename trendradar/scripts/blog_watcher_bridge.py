#!/usr/bin/env python3
from trendradar.scripts.settings import get_logger
log = get_logger('blog-watcher-bridge')
"""blogwatcher ↔ TrendRadar bridge.
Runs blogwatcher-cli scan, reads unread articles from its SQLite DB,
transforms to TrendRadar article format, marks read after output."""

import json
import subprocess
import sqlite3
import sys
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ── paths ──────────────────────────────────────────────────────────────
CST = timezone(timedelta(hours=8))
BLOGWATCHER_DB = Path.home() / '.blogwatcher-cli' / 'blogwatcher-cli.db'
from trendradar.scripts.settings import get_data_dir, get_cache_dir
TR_DATA_DIR = get_data_dir()
TR_CACHE_DIR = get_cache_dir()

# Category → TrendRadar domain mapping
# blogwatcher categories are free-text; we do keyword matching
BLOG_CATEGORY_MAP = {
    'tech': 'tech', 'technology': 'tech', 'engineering': 'tech',
    'programming': 'tech', 'software': 'tech', 'ai': 'tech',
    'startup': 'tech', 'startups': 'tech', 'cybersecurity': 'tech',
    'devops': 'tech', 'opensource': 'tech', 'data': 'tech',
    'science': 'tech',
    # economy
    'economy': 'economy', 'finance': 'economy', 'business': 'economy',
    'economics': 'economy', 'investing': 'economy', 'markets': 'economy',
    # gaming
    'gaming': 'gaming', 'games': 'gaming', 'game': 'gaming',
    'esports': 'gaming', 'gamedev': 'gaming',
    # foreign_china
    'china': 'foreign_china', 'world': 'foreign_china',
    'geopolitics': 'foreign_china', 'international': 'foreign_china',
    # default
}
DEFAULT_DOMAIN = 'tech'  # blogs tend toward analysis/tech

# 博客名 → 域覆盖（当 categories 为空时兜底）
BLOG_NAME_DOMAIN = {
    'stratechery': 'tech',
    'astral codex ten': 'tech',
    'exponential view': 'tech',
    'stubborn attached': 'tech',
    'marginal revolution': 'economy',
    'noahpinion': 'economy',
    'the browser': 'tech',
    'daring fireball': 'tech',
    'read something wonderful': 'tech',
    'dev.to': 'tech',
    'andy pavlo': 'tech',
}


def get_bridge_version() -> str:
    return '1.0.0'


def scan_blogs() -> int:
    """Run blogwatcher-cli scan, return new article count."""
    try:
        bw = shutil.which('blogwatcher-cli')
        if not bw:
            log.info("blogwatcher-cli not found in PATH")
            return 0
        result = subprocess.run(
            [bw, 'scan', '--unsafe-client'],
            capture_output=True, text=True, timeout=120
        )
        # Parse "Found N new article(s) total!" from output
        for line in result.stdout.split('\n'):
            if 'new article' in line:
                import re
                m = re.search(r'(\d+)', line)
                if m:
                    n = int(m.group(1))
                    log.info(f"scan 完成, {n} 篇新文章")
                    return n
        log.info(f"scan 完成 (输出: {result.stdout.strip()[:80]})")
        return 0
    except subprocess.TimeoutExpired:
        log.info("scan 超时")
        return 0
    except Exception as e:
        log.info(f"scan 失败: {e}")
        return 0


def _load_today_fingerprints() -> list:
    """Load today's already-pushed article fingerprints from fingerprints.db."""
    db = TR_DATA_DIR / 'fingerprints.db'
    if not db.exists():
        return []
    try:
        conn = sqlite3.connect(str(db))
        today = datetime.now(CST).strftime('%Y-%m-%d')
        rows = conn.execute(
            "SELECT title FROM fingerprints WHERE push_time LIKE ?", (f'{today}%',)
        ).fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception as e:
        log.info(f"指纹加载失败: {e}")
        return []


def fetch_blog_articles() -> list:
    """Query blogwatcher SQLite DB for unread articles, return TrendRadar-format list.
    Checks fingerprints.db to skip already-pushed articles.
    Enables batch_fetch for blog content fetching."""
    if not BLOGWATCHER_DB.exists():
        log.info(f"DB 不存在: {BLOGWATCHER_DB}")
        return []

    # 加载今日指纹用于去重
    today_fingerprints = _load_today_fingerprints()
    dedup_set = set(fp.strip().lower()[:40] for fp in today_fingerprints)

    try:
        with sqlite3.connect(str(BLOGWATCHER_DB)) as conn:
            conn.row_factory = sqlite3.Row
            # 确保索引存在（blogwatcher-cli 默认不建，避免全表扫描）
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_unread ON articles(is_read, published_date)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_blogid ON articles(blog_id)")
            rows = conn.execute("""
                SELECT a.id, a.title, a.url, a.published_date, a.categories, b.name AS blog_name
                FROM articles a
                JOIN blogs b ON a.blog_id = b.id
                WHERE a.is_read = 0
                ORDER BY a.published_date DESC
                LIMIT 20
            """).fetchall()

            if not rows:
                log.info("无未读文章")
                return []

            articles = []
            ids_to_mark = []
            skipped = 0
            for row in rows:
                domain = _map_domain(row['categories'], row['blog_name'])
                # fingerprints 去重：标题前 40 字匹配
                title_key = (row['title'] or '').strip().lower()[:40]
                if title_key and title_key in dedup_set:
                    skipped += 1
                    # 跳过的不标记已读，保留给后续推报时段
                    continue
                articles.append({
                    'title': row['title'],
                    'summary': '',
                    'url': row['url'],
                    'source_platform': row['blog_name'],
                    'domain': 'blogs',
                    '_likely_domain': domain,
                    '_source': 'blogwatcher',
                    '_needs_search': True,
                    'timestamp': row['published_date'] or '',
                    'published_date': row['published_date'] or '',
                    '_is_blog': True,  # 标识博客，在 _score 中给予 recency 保底
                })
                ids_to_mark.append(row['id'])

            # 标记已读
            if ids_to_mark:
                placeholders = ','.join('?' for _ in ids_to_mark)
                conn.execute(f"UPDATE articles SET is_read = 1 WHERE id IN ({placeholders})", ids_to_mark)
                conn.commit()

        if skipped:
            log.info(f"取出 {len(articles)} 篇博客文章({skipped} 篇因已推跳过), 已标记已读")
        else:
            log.info(f"取出 {len(articles)} 篇博客文章, 已标记已读")
        return articles

    except Exception as e:
        log.info(f"查询失败: {e}")
        return []


def _map_domain(categories: str | None, blog_name: str) -> str:
    """Map blogwatcher categories + blog name to TrendRadar domain."""
    text = f"{categories or ''} {blog_name or ''}".lower()
    for keyword, domain in BLOG_CATEGORY_MAP.items():
        if keyword in text:
            return domain
    # 兜底：博客名匹配
    for name_key, domain in BLOG_NAME_DOMAIN.items():
        if name_key in text:
            return domain
    return DEFAULT_DOMAIN


def write_cache(articles: list):
    """Write to blog cache file that push_prepare.py will consume."""
    if not articles:
        # 写空缓存
        empty = {'items': [], 'fetched_at': datetime.now(CST).isoformat(), 'source': 'blogwatcher'}
        (TR_CACHE_DIR / 'raw_blogs.json').write_text(json.dumps(empty, ensure_ascii=False))
        log.info("无文章, 写入空缓存")
        return

    cache = {
        'items': articles,
        'fetched_at': datetime.now(CST).isoformat(),
        'source': 'blogwatcher',
        'count': len(articles),
    }
    (TR_CACHE_DIR / 'raw_blogs.json').write_text(
        json.dumps(cache, ensure_ascii=False, indent=2)
    )
    per_domain = {}
    for a in articles:
        d = a['_likely_domain']
        per_domain[d] = per_domain.get(d, 0) + 1
    log.info(f"缓存写入 raw_blogs.json, 分布: {per_domain}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='blogwatcher → TrendRadar bridge')
    parser.add_argument('--version', action='version', version=get_bridge_version())
    args = parser.parse_args()

    # 1. Scan
    n = scan_blogs()
    if n == 0:
        # 可能没新文章但 DB 仍有未读（首次导入等），直接查询
        pass

    # 2. Fetch unread from DB
    articles = fetch_blog_articles()

    # 3. Write cache
    write_cache(articles)

    return 0


if __name__ == '__main__':
    sys.exit(main())
