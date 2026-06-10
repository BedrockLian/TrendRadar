from trendradar.scripts.common import CST
#!/usr/bin/env python3
from trendradar.scripts.settings import get_logger
log = get_logger('push-prepare')
"""TrendRadar 推送准备脚本 — Fetch + Curation + 精简输出 + 指纹查询 一键完成。
自动 fetch 兜底：raw JSON 不存在时自动调用 fetch_feeds.py，不再依赖外部 prefetch cron jobs。"""
import json, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

from trendradar.scripts.settings import get_data_dir, get_cache_dir, TRENDRADAR_HOME, DOMAINS
SCRIPTS_DIR = TRENDRADAR_HOME / 'scripts'
DATA_DIR = get_data_dir()
CACHE_DIR = get_cache_dir()

from trendradar.scripts.common import gen_run_id, run_id_marker, set_run_id_ctx
from trendradar.scripts.settings import write_compressed

# Sprint 3 perf: raw JSON 进程内共享缓存 (pipeline_orchestrator 和 push_prepare 各读一次 → 共享)
from trendradar.scripts.lazy import Lazy as _Lazy
_raw_today_cache = None  # type: ignore

def get_raw_today(force_reload: bool = False) -> dict:
    """返回今天 raw JSON 的内存缓存。首次调用自动加载，后续返回缓存。

    push_prepare 和 pipeline_orchestrator 共用此函数，避免同一次 pipeline 内两次 json.load。
    """
    global _raw_today_cache
    if _raw_today_cache is None or force_reload:
        from datetime import datetime as _dt
        today = _dt.now(CST).strftime('%Y%m%d')
        raw_path = CACHE_DIR / f'raw_{today}.json'
        if raw_path.exists():
            try:
                _raw_today_cache = json.loads(raw_path.read_text())
            except Exception:
                _raw_today_cache = {'items': []}
        else:
            _raw_today_cache = {'items': []}
    return _raw_today_cache


def ensure_raw_exists(push_id: str):
    """按日期缓存 raw JSON。缓存有效时跳过，否则触发 fetch。"""
    now = datetime.now(CST)  # Sprint 3: 单次快照，避免重复取系统时间
    today = now.strftime('%Y%m%d')
    raw_path = CACHE_DIR / f'raw_{today}.json'
    
    cache_valid = False
    if raw_path.exists():
        age_hours = (now - datetime.fromtimestamp(raw_path.stat().st_mtime, tz=CST)).total_seconds() / 3600
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

    # Before fetching, pre-select the best mihomo node for foreign RSS.
    # Reads mihomo's own history (no extra network probes) and switches the
    # 国外媒体 group to the lowest-latency node. ~100ms overhead.
    from trendradar.scripts.settings import select_node_for_fetch
    select_node_for_fetch(reason='pre-fetch')

    reason = "龄超4h需刷新" if raw_path.exists() else "首次fetch"
    log.info(f"{reason} — 触发 fetch（push-id={push_id}）")
    from trendradar.scripts.fetch_feeds import fetch_all
    from trendradar.scripts.settings import atomic_write_json
    start = datetime.now(CST)
    result = fetch_all(push_id)
    atomic_write_json(raw_path, {'items': result['items'],
        'failed_sources': result.get('failed_sources', []),
        'proxy_url': result.get('proxy_url', ''),
        'saved_at': datetime.now(CST).isoformat()})
    # 顺手写 zst 压缩版本（如 zstd 可用）— Agent B audit P1-11
    # write_compressed 期望 path 无后缀（它会同时写 .json 和 .json.zst），
    # 而 raw_path 已经有 .json 后缀, 剥掉
    try:
        from trendradar.scripts.file_utils import _get_zstd
        if _get_zstd():
            import zstandard as zstd_lib
            raw = raw_path.read_bytes()
            zst_path = raw_path.with_suffix('.json.zst')
            zst_path.write_bytes(zstd_lib.ZstdCompressor(level=3).compress(raw))
            log.debug(f"zst 写入: {zst_path.name} ({zst_path.stat().st_size}B)")
    except Exception as _e:
        log.debug(f"zst 写入失败（非阻塞）: {_e}")
    elapsed = (datetime.now(CST) - start).total_seconds()
    log.info(f"fetch 完成 {len(result['items'])}条, 耗时{elapsed:.1f}s, 写入 raw_{today}.json (失败源 {len(result.get('failed_sources', []))} 个)")


def run_curation(push_id: str) -> dict:
    """编排 fetch + curation 流程。

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
    
    # RSS fetch
    ensure_raw_exists(push_id)
    
    today = datetime.now(CST).strftime('%Y%m%d')
    try:
        raw = json.loads((CACHE_DIR / f'raw_{today}.json').read_text()).get('items', [])
    except (json.JSONDecodeError, FileNotFoundError, OSError) as e:
        log.info(f"读取 raw_{today}.json 失败: {e}")
        raw = []
    log.info(f"读取 {len(raw)} 条 raw")

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
