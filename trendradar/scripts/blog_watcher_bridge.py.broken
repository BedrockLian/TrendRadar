1|from trendradar.scripts.common import CST
2|#!/usr/bin/env python3
3|from trendradar.scripts.settings import get_logger
4|log = get_logger('blog-watcher-bridge')
5|"""blogwatcher ↔ TrendRadar bridge.
6|Runs blogwatcher-cli scan, reads unread articles from its SQLite DB,
7|transforms to TrendRadar article format, marks read after output."""
8|
9|import json
10|import subprocess
11|import sqlite3
12|import sys
13|import shutil
14|from pathlib import Path
15|from datetime import datetime, timezone, timedelta
16|
17|# ── paths ──────────────────────────────────────────────────────────────
18|BLOGWATCHER_DB = Path.home() / '.blogwatcher-cli' / 'blogwatcher-cli.db'
19|from trendradar.scripts.settings import get_data_dir, get_cache_dir
20|TR_DATA_DIR = get_data_dir()
21|TR_CACHE_DIR = get_cache_dir()
22|
23|# Category → TrendRadar domain mapping
24|# blogwatcher categories are free-text; we do keyword matching
25|BLOG_CATEGORY_MAP = {
26|    'tech': 'tech', 'technology': 'tech', 'engineering': 'tech',
27|    'programming': 'tech', 'software': 'tech', 'ai': 'tech',
28|    'startup': 'tech', 'startups': 'tech', 'cybersecurity': 'tech',
29|    'devops': 'tech', 'opensource': 'tech', 'data': 'tech',
30|    'science': 'tech',
31|    # economy
32|    'economy': 'economy', 'finance': 'economy', 'business': 'economy',
33|    'economics': 'economy', 'investing': 'economy', 'markets': 'economy',
34|    # gaming
35|    'gaming': 'gaming', 'games': 'gaming', 'game': 'gaming',
36|    'esports': 'gaming', 'gamedev': 'gaming',
37|    # foreign_china
38|    'china': 'foreign_china', 'world': 'foreign_china',
39|    'geopolitics': 'foreign_china', 'international': 'foreign_china',
40|    # default
41|}
42|DEFAULT_DOMAIN = 'tech'  # blogs tend toward analysis/tech
43|
44|# 博客名 → 域覆盖（当 categories 为空时兜底）
45|BLOG_NAME_DOMAIN = {
46|    'stratechery': 'tech',
47|    'astral codex ten': 'tech',
48|    'exponential view': 'tech',
49|    'stubborn attached': 'tech',
50|    'marginal revolution': 'economy',
51|    'noahpinion': 'economy',
52|    'the browser': 'tech',
53|    'daring fireball': 'tech',
54|    'read something wonderful': 'tech',
55|    'dev.to': 'tech',
56|    'andy pavlo': 'tech',
57|}
58|
59|
60|def get_bridge_version() -> str:
61|    return '1.0.0'
62|
63|
64|def scan_blogs() -> int:
65|    """Run blogwatcher-cli scan, return new article count."""
66|    try:
67|        bw = shutil.which('blogwatcher-cli')
68|        if not bw:
69|            log.info("blogwatcher-cli not found in PATH")
70|            return 0
71|        result = subprocess.run(
72|            [bw, 'scan', '--unsafe-client'],
73|            capture_output=True, text=True, timeout=120
74|        )
75|        # Parse "Found N new article(s) total!" from output
76|        for line in result.stdout.split('\n'):
77|            if 'new article' in line:
78|                import re
79|                m = re.search(r'(\d+)', line)
80|                if m:
81|                    n = int(m.group(1))
82|                    log.info(f"scan 完成, {n} 篇新文章")
83|                    return n
84|        log.info(f"scan 完成 (输出: {result.stdout.strip()[:80]})")
85|        return 0
86|    except subprocess.TimeoutExpired:
87|        log.info("scan 超时")
88|        return 0
89|    except Exception as e:
90|        log.info(f"scan 失败: {e}")
91|        return 0
92|
93|
94|def _load_today_fingerprints() -> list:
95|    """Load today's already-pushed article fingerprints from fingerprints.db."""
96|    db = TR_DATA_DIR / 'fingerprints.db'
97|    if not db.exists():
98|        return []
99|    try:
100|        conn = sqlite3.connect(str(db))
101|        today = datetime.now(CST).strftime('%Y-%m-%d')
102|        rows = conn.execute(
103|            "SELECT title FROM fingerprints WHERE push_time LIKE ?", (f'{today}%',)
104|        ).fetchall()
105|        conn.close()
106|        return [r[0] for r in rows]
107|    except Exception as e:
108|        log.info(f"指纹加载失败: {e}")
109|        return []
110|
111|
112|def fetch_blog_articles() -> list:
113|    """Query blogwatcher SQLite DB for unread articles, return TrendRadar-format list.
114|    Checks fingerprints.db to skip already-pushed articles.
115|    Blog content fetching for pipeline."""
116|    if not BLOGWATCHER_DB.exists():
117|        log.info(f"DB 不存在: {BLOGWATCHER_DB}")
118|        return []
119|
120|    # 加载今日指纹用于去重
121|    today_fingerprints = _load_today_fingerprints()
122|    dedup_set = set(fp.strip().lower()[:40] for fp in today_fingerprints)
123|
124|    try:
125|        with sqlite3.connect(str(BLOGWATCHER_DB)) as conn:
126|            conn.row_factory = sqlite3.Row
127|            # 确保索引存在（blogwatcher-cli 默认不建，避免全表扫描）
128|            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_unread ON articles(is_read, published_date)")
129|            conn.execute("CREATE INDEX IF NOT EXISTS idx_articles_blogid ON articles(blog_id)")
130|            rows = conn.execute("""
131|                SELECT a.id, a.title, a.url, a.published_date, a.categories, b.name AS blog_name
132|                FROM articles a
133|                JOIN blogs b ON a.blog_id = b.id
134|                WHERE a.is_read = 0
135|                ORDER BY a.published_date DESC
136|                LIMIT 20
137|            """).fetchall()
138|
139|            if not rows:
140|                log.info("无未读文章")
141|                return []
142|
143|            articles = []
144|            ids_to_mark = []
145|            skipped = 0
146|            for row in rows:
147|                domain = _map_domain(row['categories'], row['blog_name'])
148|                # fingerprints 去重：标题前 40 字匹配
149|                title_key = (row['title'] or '').strip().lower()[:40]
150|                if title_key and title_key in dedup_set:
151|                    skipped += 1
152|                    # 跳过的不标记已读，保留给后续推报时段
153|                    continue
154|                articles.append({
155|                    'title': row['title'],
156|                    'summary': '',
157|                    'url': row['url'],
158|                    'source_platform': row['blog_name'],
159|                    'domain': 'blogs',
160|                    '_likely_domain': domain,
161|                    '_source': 'blogwatcher',
162|                    '_needs_search': True,
163|                    'timestamp': row['published_date'] or '',
164|                    'published_date': row['published_date'] or '',
165|                    '_is_blog': True,  # 标识博客，在 _score 中给予 recency 保底
166|                })
167|                ids_to_mark.append(row['id'])
168|
169|            # 标记已读
170|            if ids_to_mark:
171|                placeholders = ','.join('?' for _ in ids_to_mark)
172|                conn.execute(f"UPDATE articles SET is_read = 1 WHERE id IN ({placeholders})", ids_to_mark)
173|                conn.commit()
174|
175|        if skipped:
176|            log.info(f"取出 {len(articles)} 篇博客文章({skipped} 篇因已推跳过), 已标记已读")
177|        else:
178|            log.info(f"取出 {len(articles)} 篇博客文章, 已标记已读")
179|        return articles
180|
181|    except Exception as e:
182|        log.info(f"查询失败: {e}")
183|        return []
184|
185|
186|def _map_domain(categories: str | None, blog_name: str) -> str:
187|    """Map blogwatcher categories + blog name to TrendRadar domain."""
188|    text = f"{categories or ''} {blog_name or ''}".lower()
189|    for keyword, domain in BLOG_CATEGORY_MAP.items():
190|        if keyword in text:
191|            return domain
192|    # 兜底：博客名匹配
193|    for name_key, domain in BLOG_NAME_DOMAIN.items():
194|        if name_key in text:
195|            return domain
196|    return DEFAULT_DOMAIN
197|
198|
199|def write_cache(articles: list):
200|    """Write to blog cache file that push_prepare.py will consume."""
201|    if not articles:
202|        # 写空缓存
203|        empty = {'items': [], 'fetched_at': datetime.now(CST).isoformat(), 'source': 'blogwatcher'}
204|        (TR_CACHE_DIR / 'raw_blogs.json').write_text(json.dumps(empty, ensure_ascii=False))
205|        log.info("无文章, 写入空缓存")
206|        return
207|
208|    cache = {
209|        'items': articles,
210|        'fetched_at': datetime.now(CST).isoformat(),
211|        'source': 'blogwatcher',
212|        'count': len(articles),
213|    }
214|    (TR_CACHE_DIR / 'raw_blogs.json').write_text(
215|        json.dumps(cache, ensure_ascii=False, indent=2)
216|    )
217|    per_domain = {}
218|    for a in articles:
219|        d = a['_likely_domain']
220|        per_domain[d] = per_domain.get(d, 0) + 1
221|    log.info(f"缓存写入 raw_blogs.json, 分布: {per_domain}")
222|
223|
224|def main():
225|    import argparse
226|    parser = argparse.ArgumentParser(description='blogwatcher → TrendRadar bridge')
227|    parser.add_argument('--version', action='version', version=get_bridge_version())
228|    args = parser.parse_args()
229|
230|    # 1. Scan
231|    n = scan_blogs()
232|    if n == 0:
233|        # 可能没新文章但 DB 仍有未读（首次导入等），直接查询
234|        pass
235|
236|    # 2. Fetch unread from DB
237|    articles = fetch_blog_articles()
238|
239|    # 3. Write cache
240|    write_cache(articles)
241|
242|    return 0
243|
244|
245|if __name__ == '__main__':
246|    sys.exit(main())
247|