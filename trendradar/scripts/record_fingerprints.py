#!/usr/bin/env python3
from settings import get_logger
log = get_logger('record-fingerprints')
"""记录本次推送指纹到 DB，供后续时段去重。"""
import json, sys, sqlite3
from pathlib import Path
from datetime import datetime, timezone, timedelta

from heat_tracker import make_fingerprint

CST = timezone(timedelta(hours=8))
from settings import get_data_dir, DOMAINS
DATA_DIR = get_data_dir()
DB_PATH = DATA_DIR / 'fingerprints.db'


def record(push_id: str):
    today = datetime.now(CST).strftime('%Y%m%d')
    push_time = datetime.now(CST).isoformat()

    paths = [
        DATA_DIR / f'curated_{push_id}_{today}.json',
        DATA_DIR / f'curated_{push_id}.json',
    ]
    curated = None
    for p in paths:
        if p.exists():
            try:
                curated = json.loads(p.read_text())
                break
            except json.JSONDecodeError, Exception:
                continue
    if not curated:
        log.info(f'未找到 {push_id} 精选数据')
        return

    run_id = curated.get('run_id', '')

    with sqlite3.connect(str(DB_PATH)) as conn:
        before = conn.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]

        # 确保 run_id 列存在
        try:
            conn.execute("ALTER TABLE fingerprints ADD COLUMN run_id TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # 列已存在

        batch = []
        for domain in DOMAINS:
            for item in curated.get(domain, []):
                title = item.get('title', '')
                if not title:
                    continue
                batch.append((
                    make_fingerprint(title, item.get('url', '')),
                    title[:200],
                    (item.get('summary', '') or '')[:200],
                    (item.get('source_platform', '') or '')[:50],
                    (item.get('url', '') or '')[:200],
                    push_id,
                    push_time,
                    push_time,
                    run_id,
                ))

        conn.execute("BEGIN")
        try:
            conn.executemany('''INSERT OR IGNORE INTO fingerprints
                (fingerprint, title, summary, source_platform, url, push_id, push_time, created_at, run_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', batch)
            conn.commit()
        except Exception:
            conn.execute("ROLLBACK")
            raise
        after = conn.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]

    log.info(f'{push_id}: +{after - before} 条（共 {after} 条）')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--push-id', required=True)
    args = parser.parse_args()
    record(args.push_id)
