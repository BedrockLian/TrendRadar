from trendradar.scripts.common import CST
#!/usr/bin/env python3
from trendradar.scripts.settings import get_logger
log = get_logger('push-prepare')
"""TrendRadar 推送准备脚本 — Fetch + Curation + 精简输出 + 指纹查询 一键完成。
自动 fetch 兜底：raw JSON 不存在时自动调用 fetch_feeds.py，不再依赖外部 prefetch cron jobs。"""
import json, sys, asyncio
from pathlib import Path
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor  # noqa: F401

from trendradar.scripts.settings import get_data_dir, get_cache_dir, TRENDRADAR_HOME, DOMAINS
SCRIPTS_DIR = TRENDRADAR_HOME / 'scripts'
DATA_DIR = get_data_dir()
CACHE_DIR = get_cache_dir()

from trendradar.scripts.common import gen_run_id, run_id_marker, set_run_id_ctx
from trendradar.scripts.settings import write_compressed


def ensure_raw_exists(push_id: str):
    """按日期缓存 raw JSON。缓存有效时跳过，否则触发 fetch。"""
    today = datetime.now(CST).strftime('%Y%m%d')
    raw_path = CACHE_DIR / f'raw_{today}.json'
    
    cache_valid = False
    if raw_path.exists():
        age_hours = (datetime.now(CST) - datetime.fromtimestamp(raw_path.stat().st_mtime, tz=CST)).total_seconds() / 3600
        if age_hours < 4:
            # Quality gate: if previous fetch was degraded, force refresh
            try:
                cached = json.loads(raw_path.read_text())
                item_count = len(cached.get('items', []))
                if item_count < 50:
                    log.warning(f"raw_{today}.json low quality ({item_count} items < 50), forcing refresh")
                else:
                    cache_valid = True
                    log.info(f"HIT raw_{today}.json (龄{age_hours:.1f}h, {raw_path.stat().st_size:,} bytes, {item_count} items)")
            except Exception as e:
                log.warning(f"raw_{today}.json 损坏（{e}），强制刷新")
                cache_valid = False
    
    if cache_valid:
        return
        
    reason = "龄超4h需刷新" if raw_path.exists() else "首次fetch"
    log.info(f"{reason} — 触发 fetch（push-id={push_id}）")
    import sys as _sys
    print(f'[TRACE] ensure_raw_exists cwd={__import__("os").getcwd()}, fetch_feeds loaded: {__import__("trendradar.scripts.fetch_feeds", fromlist=["_make_parse_pool"]).__file__}', file=_sys.stderr, flush=True)
    from trendradar.scripts.fetch_feeds import fetch_all
    import os as _os, sys as _sys
    _t0 = datetime.now(CST)
    result = asyncio.run(fetch_all(push_id))
    _t1 = datetime.now(CST)
    print(f'[DEBUG] fetch_all returned {len(result["items"])} items in {(_t1-_t0).total_seconds():.1f}s, pid={_os.getpid()}, fetch_feeds_mod_id={id(_sys.modules.get("trendradar.scripts.fetch_feeds"))}', file=_sys.stderr, flush=True)
    start = _t0
    from trendradar.scripts.settings import atomic_write_json
    atomic_write_json(raw_path, {'items': result['items'],
        'saved_at': datetime.now(CST).isoformat()})
    elapsed = (datetime.now(CST) - start).total_seconds()
    log.info(f"fetch 完成 {len(result['items'])}条, 耗时{elapsed:.1f}s, 写入 raw_{today}.json")


def load_blog_articles() -> list:
    """每 slot 触发一次 blog scan，获取最新未读博客文章。"""
    _run_blog_bridge()
    blog_cache = CACHE_DIR / 'raw_blogs.json'
    if not blog_cache.exists():
        return []
    try:
        data = json.loads(blog_cache.read_text())
        items = data.get('items', [])
        if items:
            domains = {}
            for i in items:
                d = i.get('_likely_domain', 'unknown')
                domains[d] = domains.get(d, 0) + 1
            log.info(f"加载 {len(items)} 篇博客文章, 域分布: {domains}")
        return items
    except Exception as e:
        log.info(f"加载 blog 缓存失败: {e}")
        return []


def _run_blog_bridge():
    """Run the blogwatcher bridge script once."""
    bridge = SCRIPTS_DIR / 'blog_watcher_bridge.py'
    if not bridge.exists():
        log.info(f"bridge 脚本不存在: {bridge}")
        return
    import subprocess
    try:
        subprocess.run([sys.executable, str(bridge)], capture_output=True, text=True, timeout=130)
    except Exception as e:
        log.info(f"bridge 执行失败: {e}")


def run_curation(push_id: str) -> dict:
    """编排 fetch + blog + curation 流程。并行抓取 RSS 和博客，合并后精选。

    Returns: curated dict with domains
    """
    import trendradar.scripts.curate_and_push as curate
    
    # ── 加载来源惩罚与健康评分（盲点审计 → curator 权重反馈） ──
    penalty_path = DATA_DIR / 'source_penalty.json'
    if penalty_path.exists():
        curate.load_penalty_file(str(penalty_path))
    health_path = DATA_DIR / 'source_health.json'
    if health_path.exists():
        curate.load_source_health(str(health_path))
    
    # RSS fetch 和 blog scan 顺序执行（之前用 ThreadPoolExecutor 包 fetch+blog
    # 并行，但 fetch 内部嵌套 asyncio.run() 会与子线程的 event loop 死锁——
    # 表现：fetch 返回 0 items；改为顺序执行，节省 ~1s 换稳定）。
    try:
        ensure_raw_exists(push_id)
        blog_items_result = load_blog_articles() or []
    except Exception as e:
        log.warning(f"fetch/blog 失败: {e}")
        blog_items_result = []
    
    today = datetime.now(CST).strftime('%Y%m%d')
    try:
        raw = json.loads((CACHE_DIR / f'raw_{today}.json').read_text()).get('items', [])
    except (json.JSONDecodeError, FileNotFoundError, OSError) as e:
        log.info(f"读取 raw_{today}.json 失败: {e}")
        raw = []
    log.info(f"读取 {len(raw)} 条 raw")
    
    # 合并博客文章到 raw items
    if blog_items_result:
        raw.extend(blog_items_result)
        log.info(f"合并 {len(blog_items_result)} 篇博客, raw 共计 {len(raw)} 条")

    result = curate.curate_all(raw, push_id)
    # 在脚本内部生成追溯号（不依赖 LLM prompt 执行）
    run_id = gen_run_id(push_id)
    result['run_id'] = run_id
    result['run_id_marker'] = run_id_marker(run_id)
    set_run_id_ctx(run_id)  # Python 3.14: auto-propagates to child threads
    log.info(f'RUN_ID={run_id}')
    out_path = DATA_DIR / f'curated_{push_id}.json'
    from trendradar.scripts.settings import atomic_write_json
    atomic_write_json(out_path, result)
    # 同时保存带日期后缀的副本，供 track_events 跨日比对
    dated_path = DATA_DIR / f'curated_{push_id}_{datetime.now(CST).strftime("%Y%m%d")}.json'
    from trendradar.scripts.settings import atomic_write_json
    atomic_write_json(dated_path, result)
    n = {d: len(result.get(d, [])) for d in DOMAINS}
    log.info(f"精选: 头条{n['top_headlines']} 外媒看华{n['foreign_china']} 科技{n['tech']} 经济{n['economy']} 游戏{n['gaming']} 共{result['total']}条")
    return result


def strip_item(item: dict) -> dict:
    return {
        'title': item.get('title', ''),
        'summary': (item.get('summary', '') or '')[:120],
        'source': item.get('source_platform', ''),
        'url': item.get('url', ''),
        'domain': item.get('_likely_domain', ''),
        'search': item.get('_needs_search', False),
    }


def strip_curated(curated: dict) -> dict:
    result = {'curated_at': curated.get('curated_at'), 'push_id': curated.get('push_id')}
    total = 0
    for domain in DOMAINS:
        items = curated.get(domain, [])
        stripped = [strip_item(i) for i in items]
        result[domain] = stripped
        total += len(stripped)
    result['total'] = total
    return result


def get_today_fingerprints() -> list:
    db = DATA_DIR / 'fingerprints.db'
    if not db.exists():
        return []
    import sqlite3
    try:
        import trendradar.scripts.heat_tracker as ht
        conn = ht.get_db()
    except Exception:
        conn = sqlite3.connect(str(db))
    today = datetime.now(CST).strftime('%Y-%m-%d')
    rows = conn.execute(
        "SELECT title FROM fingerprints WHERE push_time LIKE ?", (f'{today}%',)
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


def count_new_items(curated: dict, fingerprints: list) -> int:
    """统计精选结果中真正新增（不在今日指纹库中）的条数"""
    if not fingerprints:
        return sum(len(curated.get(d, [])) for d in DOMAINS)
    fps_set = set(fingerprints)
    count = 0
    for domain in DOMAINS:
        for item in curated.get(domain, []):
            title = item.get('title', '')
            # 取标题前 20 字匹配（与 fingerprint 生成逻辑一致）
            if not any(title[:20] in fp or fp[:20] in title for fp in fps_set):
                count += 1
    return count


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='TrendRadar 推送准备')
    parser.add_argument('--push-id', required=True)
    parser.add_argument('--dedup', action='store_true', help='同时查询今日已推指纹（午/晚报用）')
    args = parser.parse_args()

    import sys
    from trendradar.scripts.common import EXIT_CONFIG_ERROR, EXIT_FATAL

    try:
        curated = run_curation(args.push_id)
    except FileNotFoundError as e:
        log.error(f"必要文件缺失: {e}")
        sys.exit(EXIT_CONFIG_ERROR)
    except json.JSONDecodeError as e:
        log.error(f"JSON 解析失败: {e}")
        sys.exit(EXIT_CONFIG_ERROR)
    except Exception as e:
        import traceback
        log.error(f"未预期异常: {e}\n{traceback.format_exc()}")
        sys.exit(EXIT_FATAL)

    light = strip_curated(curated)
    print(json.dumps(light, ensure_ascii=False))

    if args.dedup:
        fps = get_today_fingerprints()
        new_count = count_new_items(curated, fps)
        log.info(f"今日 {len(fps)} 条已推, 其中 {new_count} 条新增")
        print(f"NEW_COUNT={new_count}")
        print("=== FINGERPRINTS ===")
        for t in fps:
            print(t)
