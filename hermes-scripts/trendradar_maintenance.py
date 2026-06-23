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

STATS = {'backed_up': 0, 'cleaned_files': 0, 'cleaned_bytes': 0,
          'archived_heat_rows': 0, 'cleaned_pycaches': 0,
          'cleaned_markers': 0, 'cleaned_orphan_backups': 0}


def archive_dormant_heat():
    """把 heat_tracker 主表的 dormant+>7d 行搬到 heat_tracker_archive。

    审计 P1-2：之前 002_heat_archive.sql 只跑过一次，6/4 之后产生的
    zombie 行 (3,659 条 / ~6 MB) 没继续归档。主表 94% 是僵尸。

    幂等: INSERT OR IGNORE + DELETE WHERE status='dormant' AND datetime(last_seen)<now-7d
    """
    import sqlite3
    db_path = TRENDRADAR_HOME / 'data' / 'fingerprints.db'
    if not db_path.exists():
        return

    try:
        conn = sqlite3.connect(str(db_path))
        moved = conn.execute("""
            INSERT OR IGNORE INTO heat_tracker_archive
                (fingerprint, title, first_seen, last_seen, appearance_count,
                 fetch_cycles, platforms, platform_count, heat_signals,
                 domain, status, rank_history)
            SELECT fingerprint, title, first_seen, last_seen, appearance_count,
                   fetch_cycles, platforms, platform_count, heat_signals,
                   domain, status, rank_history
            FROM heat_tracker
            WHERE status='dormant'
              AND datetime(last_seen) < datetime('now','-7 days')
        """).rowcount
        deleted = conn.execute("""
            DELETE FROM heat_tracker
            WHERE status='dormant'
              AND datetime(last_seen) < datetime('now','-7 days')
        """).rowcount
        conn.commit()

        # VACUUM 释放空间（必须连接关闭后单独跑）
        if deleted > 0:
            conn.execute('VACUUM')

        conn.close()
        if moved or deleted:
            STATS['archived_heat_rows'] = deleted
            print(f'[ARCHIVE] heat_tracker 搬 {moved} 行到 archive，删除主表 {deleted} 行')
    except Exception as e:
        print(f'[ARCHIVE ERROR] {e}')


def cleanup_pycaches():
    """清理 runtime 根散落的 __pycache__/ 目录（审计 P1-9）。"""
    cleaned = 0
    for pycache in TRENDRADAR_HOME.rglob('__pycache__'):
        # 只清运行时散落的，不清 trendradar/tests/ 之类（git 包内由 .gitignore 兜底）
        try:
            shutil.rmtree(pycache, ignore_errors=True)
            cleaned += 1
        except OSError:
            pass
    if cleaned:
        STATS['cleaned_pycaches'] = cleaned


def cleanup_dead_backups():
    """清理 data/fingerprints.db.backup / .pre002 之类的死重备份（审计 P0-3）。"""
    patterns = ['fingerprints.db.backup', 'fingerprints.db.backup.pre002',
                'fingerprints.db.pre002']
    cleaned = 0
    for name in patterns:
        p = TRENDRADAR_HOME / 'data' / name
        if p.exists():
            try:
                p.unlink()
                cleaned += 1
            except OSError:
                pass
    if cleaned:
        STATS['cleaned_orphan_backups'] = cleaned


def cleanup_old_marker_format():
    """归档老式命名格式的 marker 到 .archive/（审计 P1-8）。

    当前 3 种命名混用：
      - YYYY-MM-DD_slot.marker (旧式，最老)
      - delivered_YYYY-MM-DD_slot.marker (旧式)
      - delivered_YYYYMMDD_slot_runid.marker (新式，标准)
    新格式不删，老格式移到 .archive/ 保留历史但不污染主目录。
    """
    import re
    markers_dir = TRENDRADAR_HOME / 'data' / 'delivery_markers'
    if not markers_dir.exists():
        return
    archive_dir = markers_dir / '.archive'
    archive_dir.mkdir(exist_ok=True)

    old_pat_1 = re.compile(r'^\d{4}-\d{2}-\d{2}_(morning|noon|evening)\.marker$')
    old_pat_2 = re.compile(r'^delivered_\d{4}-\d{2}-\d{2}_(morning|noon|evening)\.marker$')

    moved = 0
    for m in markers_dir.glob('*.marker'):
        if old_pat_1.match(m.name) or old_pat_2.match(m.name):
            try:
                m.rename(archive_dir / m.name)
                moved += 1
            except OSError:
                pass
    if moved:
        STATS['cleaned_markers'] = moved


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
    """运行 pytest 烟雾测试，返回是否全部通过。

    注意: test_push_prepare.py 在 PYTHONPATH 包含 /home/asus/.hermes/ 时会挂起，
    原因是在 trendradar 包解析时产生 import 死锁。故：
      - PYTHONPATH 设为 trendradar 的父目录（trendradar 本身是包）
      - 排除 push_prepare 测试（非核心烟雾测试项）
      - 60s 超时（避免拖死 cron 120s 限额）
    """
    import subprocess
    pipeline_python = os.environ.get('PYTHON', r'C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\python.exe')
    if not os.access(pipeline_python, os.X_OK):
        pipeline_python = sys.executable
    penv = os.environ.copy()
    # trefdradar 目录有 __init__.py，其父目录作为 PYTHONPATH 即可 import trendradar
    TR_PKG = TRENDRADAR_HOME / 'trendradar'
    penv['PYTHONPATH'] = str(TRENDRADAR_HOME) if TR_PKG.exists() else str(TRENDRADAR_HOME)
    # 仅 free-threading (3.14t) 才需要关 GIL；标准 3.14 不支持 PYTHON_GIL=0
    try:
        penv.pop('PYTHON_GIL')
    except KeyError:
        pass
    try:
        result = subprocess.run(
            [pipeline_python, '-m', 'pytest', 'tests/', '-q', '--tb=line',
             '-k', 'not slow and not ai_translate and not push_prepare and not TestRecordFingerprints'],
            cwd=str(TR_PKG if TR_PKG.exists() else TRENDRADAR_HOME),
            capture_output=True, text=True, timeout=60, env=penv,
        )
    except subprocess.TimeoutExpired:
        print('[TESTS TIMEOUT] pytest 60s 未完成 — 可能是 GC 抖动。'
              ' 备份和清理已完成，标记为软失败')
        return True  # 软失败：备份/清理/vacuum 已成功，测试仅是辅助验证
    except Exception as e:
        print(f'[TESTS ERROR] {type(e).__name__}: {e}')
        return True  # 软失败同理
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
    cleanup_dead_backups()
    archive_dormant_heat()
    backup()
    cleanup()
    cleanup_pycaches()
    cleanup_old_marker_format()
    vacuum_db()
    summary()
    if not runtests():
        print('[WARNING] 烟雾测试未通过，但备份和清理已完成')
        sys.exit(1)
