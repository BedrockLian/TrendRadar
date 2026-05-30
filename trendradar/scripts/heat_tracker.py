#!/usr/bin/env python3
from trendradar.scripts.common import CST
"""
TrendRadar 热度追踪器 - 跨周期持久化追踪新闻热度变化
功能：时间轴追踪 / 热度变化 / 新热点检测 / 持续性分析 / 跨平台对比
"""

from trendradar.scripts.settings import get_logger
log = get_logger('heat-tracker')

import sqlite3
import hashlib
import json
import re
import threading
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple

from trendradar.scripts.settings import get_data_dir, get_storage

from functools import lru_cache

DB_PATH = str(get_data_dir() / 'fingerprints.db')
_STORE = get_storage()  # 统一存储入口（单例）
_INITIALIZED = False
_local = threading.local()  # per-thread connection storage


def _configure_connection(conn: sqlite3.Connection):
    """PRAGMA 优化：WAL 模式 + 读写加速。
    
    核心 PRAGMA 与 Storage.db() 保持一致，per-thread 连接额外设置
    mmap_size 优化大事务性能。
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8000")       # 8MB
    conn.execute("PRAGMA mmap_size=268435456")    # 256MB
    conn.execute("PRAGMA busy_timeout=5000")


def get_db() -> sqlite3.Connection:
    """获取 per-thread 持久连接（WAL 优化，线程安全）。
    
    首次连接通过 Storage.db() 建立（统一 WAL + busy_timeout），
    后续复用 per-thread 连接池以提升性能。
    """
    if not hasattr(_local, 'conn') or _local.conn is None:
        # 优先通过 Storage 统一入口建立连接
        try:
            _local.conn = _STORE.db('fingerprints.db', row_factory=sqlite3.Row)
        except Exception as e:
            log.warning(f"Storage.db 失败，直连兜底: {e}")
            # 兜底：直接连接（兼容测试/非标准部署）
            _local.conn = sqlite3.connect(DB_PATH)
            _local.conn.row_factory = sqlite3.Row
            _configure_connection(_local.conn)
    _ensure_indexes(_local.conn)
    return _local.conn


def init_db():
    """初始化数据库 schema（懒加载 — 首次调用时执行，后续秒过）。"""
    global _INITIALIZED
    if _INITIALIZED:
        return
    from trendradar.scripts.settings import ensure_db_migrated
    ensure_db_migrated(DB_PATH)
    conn = get_db()
    conn.execute("PRAGMA journal_mode=WAL")
    _INITIALIZED = True


def _ensure_indexes(conn: sqlite3.Connection):
    """确保复合索引存在（每次连接都检查，幂等）。"""
    conn.execute("CREATE INDEX IF NOT EXISTS idx_heat_status_lastseen ON heat_tracker(status, last_seen)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_heat_status_platcount ON heat_tracker(status, platform_count)")


@lru_cache(maxsize=1024)
def make_fingerprint(title: str, url: str = '') -> str:
    """生成指纹（保留中日文字符 + URL域/首段防碰撞）。
    4Gamer等日语源标题相似度高，加入URL特征避免重复项占据TOP10。"""
    norm = title.lower().strip()
    # 保留 CJK（中日韩）+ 片假名/平假名 + 字母数字
    norm = re.sub(r'[^\w\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', '', norm)
    # 加入 URL 域名 + 前3段路径防碰撞（如 4Gamer 同一游戏不同文章）
    if url:
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            from trendradar.scripts.settings import FINGERPRINT_URL_SEGMENTS
            segments = [s for s in parsed.path.split('/') if s][:FINGERPRINT_URL_SEGMENTS]
            url_key = parsed.netloc + '/' + '/'.join(segments)
            norm += url_key.lower()
        except (ValueError, AttributeError):
            log.debug("URL 解析失败，使用原始 URL: %s", url)
    from trendradar.scripts.settings import FINGERPRINT_MD5_LEN
    return hashlib.md5(norm.encode()).hexdigest()[:FINGERPRINT_MD5_LEN]


def _gen_fingerprints(items: list, push_id: str, now: str) -> dict:
    """生成指纹映射表。返回 {fingerprint: (item, signal)}。"""
    fp_map = {}
    from trendradar.scripts.settings import HEAT_WORDS
    for item in items:
        title = item.get('title', '')
        if not title:
            continue
        fp = make_fingerprint(title, item.get('url', ''))
        hw = sum(1 for w in HEAT_WORDS if w in title)
        signal = {
            'time': now, 'push_id': push_id,
            'platform': item.get('source_platform', ''),
            'coverage': item.get('_coverage_count', 1),
            'heat_words': hw,
        }
        fp_map[fp] = (item, signal)
    return fp_map


def _merge_entries(conn, fp_map: dict, existing_rows: dict, now: str, push_id: str, stats: dict):
    """对比已存在记录，生成 update/insert 批次。"""
    update_batch = []
    insert_batch = []
    for fp, (item, signal) in fp_map.items():
        platform = item.get('source_platform', '')
        domain = item.get('_likely_domain', '')

        if fp in existing_rows:
            row = existing_rows[fp]
            old_platforms = json.loads(row['platforms'])
            old_signals = json.loads(row['heat_signals'])
            old_rank_history = json.loads(row['rank_history'] or '[]')
            hot_rank = item.get('hot_rank')
            if hot_rank is not None:
                old_rank_history.append({'rank': hot_rank, 'time': now})
                if len(old_rank_history) > 20:
                    old_rank_history = old_rank_history[-20:]
            new_platforms = set(p.strip() for p in platform.split('+') if p.strip())
            existing_set = set(old_platforms)
            added = [p for p in new_platforms if p not in existing_set]
            old_platforms.extend(added)
            old_signals.append(signal)
            old_push_ids = [s['push_id'] for s in old_signals]
            is_new_cycle = 0 if push_id in old_push_ids else 1
            update_batch.append((
                now, is_new_cycle,
                json.dumps(old_platforms), len(old_platforms),
                json.dumps(old_signals), json.dumps(old_rank_history), fp))
            stats['updated'] += 1
        else:
            platforms = list(set(p.strip() for p in platform.split('+') if p.strip()))
            hot_rank = item.get('hot_rank')
            init_rank_history = [{'rank': hot_rank, 'time': now}] if hot_rank is not None else []
            insert_batch.append((
                fp, item.get('title', ''), now, now,
                json.dumps(platforms), len(platforms),
                json.dumps([signal]), domain,
                json.dumps(init_rank_history)))
            stats['new'] += 1
    return update_batch, insert_batch


def _write_batch(conn, update_batch: list, insert_batch: list, stats: dict) -> dict:
    """显式事务批量写入 + 休眠标记。"""
    conn.execute("BEGIN")
    try:
        if update_batch:
            conn.executemany("""
                UPDATE heat_tracker SET
                    last_seen = ?,
                    appearance_count = appearance_count + 1,
                    fetch_cycles = fetch_cycles + ?,
                    platforms = ?,
                    platform_count = ?,
                    heat_signals = ?,
                    rank_history = ?,
                    status = 'active'
                WHERE fingerprint = ?
            """, update_batch)
        if insert_batch:
            conn.executemany("""
                INSERT INTO heat_tracker
                    (fingerprint, title, first_seen, last_seen, appearance_count,
                     fetch_cycles, platforms, platform_count, heat_signals, domain, rank_history, status)
                VALUES (?, ?, ?, ?, 1, 1, ?, ?, ?, ?, ?, 'active')
            """, insert_batch)
        from trendradar.scripts.settings import HEAT_SLEEP_HOURS
        cutoff = (datetime.now(CST) - timedelta(hours=HEAT_SLEEP_HOURS)).isoformat()
        conn.execute("UPDATE heat_tracker SET status = 'dormant' WHERE last_seen < ? AND status = 'active'", (cutoff,))
        stats['total_active'] = conn.execute(
            "SELECT COUNT(*) FROM heat_tracker WHERE status = 'active'"
        ).fetchone()[0]
        conn.commit()
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return stats


def update_tracker(items: list, push_id: str) -> dict:
    """更新热度追踪（拆分为 _gen_fingerprints / _merge_entries / _write_batch）。"""
    init_db()
    conn = get_db()
    now = datetime.now(CST).isoformat()
    stats = {'new': 0, 'updated': 0, 'total_active': 0}

    fp_map = _gen_fingerprints(items, push_id, now)

    fps = list(fp_map.keys())
    existing_rows = {}
    CHUNK = 500
    for i in range(0, len(fps), CHUNK):
        chunk = fps[i:i+CHUNK]
        placeholders = ','.join('?' * len(chunk))
        for row in conn.execute(
            f"SELECT fingerprint, platforms, heat_signals, rank_history FROM heat_tracker WHERE fingerprint IN ({placeholders})",
            chunk
        ).fetchall():
            existing_rows[row['fingerprint']] = row

    update_batch, insert_batch = _merge_entries(conn, fp_map, existing_rows, now, push_id, stats)
    stats = _write_batch(conn, update_batch, insert_batch, stats)
    return stats


def _query_heat_rows(conn, items: list) -> dict[str, any]:
    """批量查询热度追踪行。返回 {fingerprint: {'title': str, 'row': Row|None}}。"""
    fp_to_title = {}
    for item in items:
        title = item.get('title', '')
        if not title:
            continue
        fp = make_fingerprint(title, item.get('url', ''))
        fp_to_title[fp] = title

    fps = list(fp_to_title.keys())
    rows_by_fp = {}
    CHUNK = 500
    for i in range(0, len(fps), CHUNK):
        chunk = fps[i:i+CHUNK]
        placeholders = ','.join('?' * len(chunk))
        for row in conn.execute(
            f"SELECT * FROM heat_tracker WHERE fingerprint IN ({placeholders})", chunk
        ).fetchall():
            rows_by_fp[row['fingerprint']] = row

    return {fp: {'title': fp_to_title[fp], 'row': rows_by_fp.get(fp)} for fp in fp_to_title}


def _calc_heat(fp: str, title: str, row, now: datetime) -> dict:
    """计算单条指纹的热度信息。"""
    info = {
        'fingerprint': fp,
        'is_new': False,
        'is_sustained': False,
        'is_deep': False,
        'trend': 'new',
        'heat_score': 0,
        'appearances': 1,
        'platforms': [],
        'span_hours': 0,
        'rank_timeline': [],
    }

    if row:
        signals = json.loads(row['heat_signals'])
        info['appearances'] = row['appearance_count']
        info['platforms'] = json.loads(row['platforms'])
        info['span_hours'] = _calc_span_hours(row['first_seen'], row['last_seen'])
        info['rank_timeline'] = json.loads(row['rank_history'] or '[]')

        from trendradar.scripts.settings import HEAT_DEEP_CYCLES, HEAT_DEEP_SPAN, HEAT_SUSTAINED_CYCLES, HEAT_SUSTAINED_SPAN
        if row['fetch_cycles'] >= HEAT_DEEP_CYCLES and info['span_hours'] >= HEAT_DEEP_SPAN:
            info['is_deep'] = True
            info['is_sustained'] = True
        elif row['fetch_cycles'] >= HEAT_SUSTAINED_CYCLES or info['span_hours'] >= HEAT_SUSTAINED_SPAN:
            info['is_sustained'] = True

        if row['fetch_cycles'] <= 1 and info['span_hours'] < 1:
            info['is_new'] = True
        elif row['appearance_count'] <= 2:
            info['is_new'] = True

        if len(signals) >= 2:
            recent = signals[-1]
            prev = signals[-2]
            recent_heat = recent.get('coverage', 1) + recent.get('heat_words', 0)
            prev_heat = prev.get('coverage', 1) + prev.get('heat_words', 0)
            if recent_heat > prev_heat:
                info['trend'] = 'rising'
            elif recent_heat < prev_heat:
                info['trend'] = 'fading'
            else:
                info['trend'] = 'stable'

        freq_score = min(row['appearance_count'] / 10, 1.0) * 3
        span_score = min(info['span_hours'] / 48, 1.0) * 2
        plat_score = min(len(info['platforms']) / 10, 1.0) * 3
        trend_bonus = 1.0 if info['trend'] == 'rising' else (0.5 if info['trend'] == 'stable' else 0)
        info['heat_score'] = round(freq_score + span_score + plat_score + trend_bonus, 1)

    return info


def get_heat_info(items: list) -> dict:
    """为 items 中的每条新闻加载热度追踪数据（拆分为 _query_heat_rows / _calc_heat）。"""
    init_db()
    conn = get_db()
    now = datetime.now(CST)
    entries = _query_heat_rows(conn, items)
    result = {fp: _calc_heat(fp, e['title'], e['row'], now) for fp, e in entries.items()}
    return result


def _calc_span_hours(first_seen: str, last_seen: str) -> float:
    try:
        first = datetime.fromisoformat(first_seen)
        last = datetime.fromisoformat(last_seen)
        return (last - first).total_seconds() / 3600
    except (ValueError, TypeError):
        return 0


def print_tracker_status():
    """打印追踪器状态（用于验证/调试）"""
    init_db()
    conn = get_db()
    
    total = conn.execute("SELECT COUNT(*) FROM heat_tracker").fetchone()[0]
    active = conn.execute("SELECT COUNT(*) FROM heat_tracker WHERE status='active'").fetchone()[0]
    dormant = conn.execute("SELECT COUNT(*) FROM heat_tracker WHERE status='dormant'").fetchone()[0]
    
    print(f"[HEAT] 追踪器: {total}条总记录, {active}活跃, {dormant}休眠")
    
    top = conn.execute("""
        SELECT title, appearance_count, platform_count, 
               first_seen, last_seen, status
        FROM heat_tracker 
        WHERE status='active' 
        ORDER BY appearance_count DESC 
        LIMIT 10
    """).fetchall()
    
    if top:
        print(f"[HEAT] 当前最热TOP 10:")
        for i, row in enumerate(top, 1):
            span = _calc_span_hours(row['first_seen'], row['last_seen'])
            print(f"  {i}. [{row['appearance_count']}次/{row['platform_count']}平台] {row['title'][:40]}")
            print(f"     跨度{span:.1f}h, {row['status']}")


if __name__ == '__main__':
    print_tracker_status()
