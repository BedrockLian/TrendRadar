#!/usr/bin/env python3
"""TrendRadar 每日维护：数据备份 + 缓存清理 + DB vacuum + 烟雾测试

Cron 每天 03:00 运行（推送空闲时段），no_agent=true。
- 备份 fingerprints.db / sources.json / source_health.json / push_log.json / config
- 清理 cache/ 旧文件（>48h）和 data/ 旧文件（>7d）
- DB vacuum 回收碎片空间
- 保留 30 天备份
- 烟雾测试（pytest）
"""
import shutil
import os
import sys
import time
import glob
from pathlib import Path
from datetime import datetime

TRENDRADAR_HOME = Path(os.environ.get(
    'TRENDRADAR_HOME',
    Path.home() / '.hermes' / 'trendradar'
))
BACKUPDIR = Path.home() / 'backups' / 'trendradar'
RETENTION_FILE_DAYS = 7
RETENTION_CACHE_HOURS = 48
RETENTION_BACKUP_DAYS = 30

STATS = {'backed_up': 0, 'cleaned_files': 0, 'cleaned_bytes': 0}


def backup():
    today = datetime.now().strftime('%Y%m%d')
    dest = BACKUPDIR / today
    dest.mkdir(parents=True, exist_ok=True)

    items = [
        (TRENDRADAR_HOME / 'data' / 'fingerprints.db', 'fingerprints.db'),
        (TRENDRADAR_HOME / 'data' / 'sources.json', 'sources.json'),
        (TRENDRADAR_HOME / 'data' / 'source_health.json', 'source_health.json'),
        (TRENDRADAR_HOME / 'data' / 'push_log.json', 'push_log.json'),
    ]
    errors = []
    for src, name in items:
        if src.exists():
            try:
                shutil.copy2(str(src), str(dest / name))
                STATS['backed_up'] += 1
            except OSError as e:
                errors.append(f'{name}: {e}')

    # 配置目录 — 除 __pycache__ 外整个复制
    cfg_src = TRENDRADAR_HOME / 'config'
    if cfg_src.exists():
        cfg_dst = dest / 'config'
        try:
            shutil.copytree(str(cfg_src), str(cfg_dst),
                            dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__'))
            for f in cfg_src.rglob('*'):
                if f.is_file() and '__pycache__' not in f.parts:
                    STATS['backed_up'] += 1
        except OSError as e:
            errors.append(f'config: {e}')

    # 最近一次的 curated JSON
    for push_id in ['morning', 'noon', 'evening']:
        latest = TRENDRADAR_HOME / 'data' / f'curated_{push_id}.json'
        if latest.exists():
            try:
                shutil.copy2(str(latest), str(dest / f'curated_{push_id}.json'))
                STATS['backed_up'] += 1
            except OSError as e:
                errors.append(f'curated_{push_id}: {e}')

    # 过期备份清理（保留 30 天）
    cutoff = time.time() - RETENTION_BACKUP_DAYS * 86400
    removed_backups = 0
    for d in glob.glob(str(BACKUPDIR / '*')):
        if os.path.isdir(d) and os.path.getmtime(d) < cutoff:
            try:
                shutil.rmtree(d)
                removed_backups += 1
            except OSError:
                pass

    if errors:
        print(f'[BACKUP ERROR] {" | ".join(errors)}')
        sys.exit(1)

    if removed_backups:
        STATS['cleaned_backups'] = removed_backups


def cleanup():
    cutoff = time.time() - RETENTION_FILE_DAYS * 86400
    cache_cutoff = time.time() - RETENTION_CACHE_HOURS * 3600

    # data/ — JSON + zst 压缩文件（>7d）
    data_patterns = [
        (TRENDRADAR_HOME / 'data', 'curated_*_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].json'),
        (TRENDRADAR_HOME / 'data', 'curated_*_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].json.zst'),
        (TRENDRADAR_HOME / 'data', 'raw_*.json'),
    ]

    # cache/ — 所有缓存文件（>48h，Trap 30）
    cache_patterns = [
        (TRENDRADAR_HOME / 'cache', '*.json'),
        (TRENDRADAR_HOME / 'cache', '*.json.zst'),
    ]

    errors = []

    for base_dir, pat in data_patterns:
        for f in base_dir.glob(pat):
            if 'test' in f.name.lower():
                continue
            try:
                if os.path.getmtime(str(f)) < cutoff:
                    sz = f.stat().st_size
                    f.unlink()
                    STATS['cleaned_files'] += 1
                    STATS['cleaned_bytes'] += sz
            except OSError as e:
                errors.append(f'{f.name}: {e}')

    for base_dir, pat in cache_patterns:
        for f in base_dir.glob(pat):
            try:
                if os.path.getmtime(str(f)) < cache_cutoff:
                    sz = f.stat().st_size
                    f.unlink()
                    STATS['cleaned_files'] += 1
                    STATS['cleaned_bytes'] += sz
            except OSError as e:
                errors.append(f'{f.name}: {e}')

    if errors:
        print(f'[CLEANUP ERROR] {" | ".join(errors)}')
        sys.exit(1)


def vacuum_db():
    """VACUUM fingerprints.db 回收碎片空间（Trap 30）。"""
    db_path = TRENDRADAR_HOME / 'data' / 'fingerprints.db'
    if not db_path.exists():
        return

    try:
        import sqlite3
        before = db_path.stat().st_size
        conn = sqlite3.connect(str(db_path))
        conn.execute("VACUUM")
        conn.close()
        after = db_path.stat().st_size
        freed = before - after
        if freed > 1024:  # >1KB
            STATS['vacuum_freed'] = freed
    except Exception as e:
        print(f'[VACUUM ERROR] {e}')


def runtests() -> bool:
    """运行 pytest 烟雾测试，返回是否全部通过。"""
    import subprocess
    pipeline_python = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')
    if not os.access(pipeline_python, os.X_OK):
        pipeline_python = sys.executable
    penv = os.environ.copy()
    penv['PYTHONPATH'] = str(TRENDRADAR_HOME.parent)
    penv.setdefault('PYTHON_GIL', '0')
    result = subprocess.run(
        [pipeline_python, '-m', 'pytest', 'tests/', '-q', '--tb=line',
         '-k', 'not slow and not ai_translate'],
        cwd=str(TRENDRADAR_HOME),
        capture_output=True, text=True, timeout=120, env=penv,
    )
    if result.returncode != 0:
        print(f'[TESTS FAILED] {result.stdout[-200:]}')
        return False
    return True


def summary():
    """打印本次维护摘要"""
    parts = []
    if STATS['backed_up']:
        parts.append(f'已备份 {STATS["backed_up"]} 文件')
    if STATS['cleaned_files']:
        freed = STATS['cleaned_bytes'] / 1024
        parts.append(f'已清理 {STATS["cleaned_files"]} 文件（释放 {freed:.0f}KB）')
    if STATS.get('vacuum_freed'):
        freed = STATS['vacuum_freed'] / 1024
        parts.append(f'DB vacuum 释放 {freed:.0f}KB')
    if STATS.get('cleaned_backups'):
        parts.append(f'已清理 {STATS["cleaned_backups"]} 个过期备份目录')
    line = ' | '.join(parts)
    print(f'[{datetime.now().strftime("%H:%M:%S")}] {line}' if line else '[OK] 维护完成，无需清理')


if __name__ == '__main__':
    backup()
    cleanup()
    vacuum_db()
    summary()
    if not runtests():
        print('[WARNING] 烟雾测试未通过，但备份和清理已完成')
        sys.exit(1)
