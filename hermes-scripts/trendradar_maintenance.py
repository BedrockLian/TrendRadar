#!/usr/bin/env python3
"""TrendRadar 每日维护：数据备份 + 缓存清理 + 烟雾测试

Cron 每天 03:00 运行（推送空闲时段），no_agent=true。
- 备份 fingerprints.db / 配置 / preferences 到 ~/backups/trendradar/YYYYMMDD/
- 清理 cache/ 和 data/ 中的旧文件（>7 天）
- 清理旧压缩文件（.json.zst）
- 保留 30 天备份
- 输出摘要（无错误时也打印进度）
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
RETENTION_BACKUP_DAYS = 30

STATS = {'backed_up': 0, 'cleaned_files': 0, 'cleaned_bytes': 0}


def backup():
    today = datetime.now().strftime('%Y%m%d')
    dest = BACKUPDIR / today
    dest.mkdir(parents=True, exist_ok=True)

    items = [
        (TRENDRADAR_HOME / 'data' / 'fingerprints.db', 'fingerprints.db'),
        (TRENDRADAR_HOME / 'data' / 'preferences.json', 'preferences.json'),
        (TRENDRADAR_HOME / 'data' / 'push_log.json', 'push_log.json'),
        (TRENDRADAR_HOME / 'data' / 'sources.json', 'sources.json'),
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
            # 排除 __pycache__
            shutil.copytree(str(cfg_src), str(cfg_dst),
                            dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns('__pycache__'))
            # 统计备份的文件数
            for f in cfg_src.rglob('*'):
                if f.is_file() and '__pycache__' not in f.parts:
                    STATS['backed_up'] += 1
        except OSError as e:
            errors.append(f'config: {e}')

    # 额外备份关键源数据文件（最近一次的 curated JSON）
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

    # 清理 patterns：JSON + zst 压缩文件 + raw/blog 缓存
    patterns = [
        # cache — json 和 zst 都清
        (TRENDRADAR_HOME / 'cache', '*.json'),
        (TRENDRADAR_HOME / 'cache', '*.json.zst'),
        # data — 仅清理日期版 curated（保留无日期的"最新"文件）
        (TRENDRADAR_HOME / 'data', 'curated_*_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].json'),
        (TRENDRADAR_HOME / 'data', 'curated_*_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].json.zst'),
        # data — 仅清理旧的 raw 文件
        (TRENDRADAR_HOME / 'data', 'raw_*.json'),
    ]

    errors = []
    for base_dir, pat in patterns:
        for f in base_dir.glob(pat):
            # 排除 test 文件（人工测试保留）
            if 'test' in f.name.lower():
                continue
            try:
                mtime = os.path.getmtime(str(f))
                if mtime < cutoff:
                    sz = f.stat().st_size
                    f.unlink()
                    STATS['cleaned_files'] += 1
                    STATS['cleaned_bytes'] += sz
            except OSError as e:
                errors.append(f'{f.name}: {e}')

    if errors:
        print(f'[CLEANUP ERROR] {" | ".join(errors)}')
        sys.exit(1)


def runtests() -> bool:
    """运行 pytest 烟雾测试，返回是否全部通过。"""
    import subprocess
    result = subprocess.run(
        ['python3', '-m', 'pytest', 'tests/', '-q', '--tb=line', '-m', 'not slow'],
        cwd=str(TRENDRADAR_HOME),
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        print(f'[TESTS FAILED] {result.stdout[-200:]}', file=sys.stderr)
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
    if STATS.get('cleaned_backups'):
        parts.append(f'已清理 {STATS["cleaned_backups"]} 个过期备份目录')
    line = ' | '.join(parts)
    print(f'[{datetime.now().strftime("%H:%M:%S")}] {line}' if line else '[OK] 维护完成，无需清理')


if __name__ == '__main__':
    backup()
    cleanup()
    summary()
    if not runtests():
        print('[WARNING] 烟雾测试未通过，但备份和清理已完成', file=sys.stderr)
