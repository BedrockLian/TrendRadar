"""curated_paths.py — curated JSON 文件查找/列表 (Sprint 2 P1-14)

从 common.py 拆出。
"""
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .time_utils import CST
from .lazy import Lazy

# ── Data dir 解析 (lazy, 避免循环依赖) ─────────────────────
_data_dir_cache: Optional[Path] = None
_data_dir_lock = threading.Lock()


def get_data_dir_for_common() -> Path:
    """Return DATA_DIR, caching the first call.

    Avoids import-time side effects (the underlying get_data_dir may load
    settings which does I/O).  Multiple callers get the same cached value.

    注意: Sprint 2 P1-12 之后应该用 trendradar.scripts.paths.DATA_DIR,
    但保持此函数作为向后兼容 shim（caller 还在用）。
    """
    global _data_dir_cache
    if _data_dir_cache is not None:
        return _data_dir_cache
    with _data_dir_lock:
        if _data_dir_cache is not None:
            return _data_dir_cache
        from trendradar.scripts.file_utils import get_data_dir
        _data_dir_cache = get_data_dir()
        return _data_dir_cache


# ── 列表/查找 ────────────────────────────────────────────
def list_curated_files(days: int) -> list[str]:
    """List curated JSON files within the last N days.

    Returns sorted list of absolute file paths.
    """
    data_dir = get_data_dir_for_common()
    cutoff = datetime.now(CST) - timedelta(days=days)
    files = []
    for f in os.listdir(str(data_dir)):
        if not f.startswith('curated_') or not f.endswith('.json'):
            continue
        fpath = os.path.join(str(data_dir), f)
        mtime = datetime.fromtimestamp(os.path.getmtime(fpath), tz=CST)
        if mtime >= cutoff:
            files.append(fpath)
    return sorted(files)


def find_curated_file(date: str, slot: str) -> Optional[Path]:
    """Find a curated JSON file with 3-level fallback.

    Level 1: exact dated file     curated_{slot}_{date}.json
    Level 2: latest dated file    curated_{slot}_*YYYYMMDD*.json
    Level 3: generic file         curated_{slot}.json

    Args:
        date: YYYYMMDD date string.
        slot: push slot name (e.g. 'morning', 'noon', 'evening').

    Returns:
        Path if found, None otherwise.
    """
    data_dir = get_data_dir_for_common()

    # Level 1: exact dated file
    curated_path = data_dir / f'curated_{slot}_{date}.json'
    if curated_path.exists():
        return curated_path

    # Level 2: latest dated version
    dated_files = sorted(
        data_dir.glob(f'curated_{slot}_[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9].json'),
        reverse=True,
    )
    if dated_files:
        return dated_files[0]

    # Level 3: generic version
    curated_path = data_dir / f'curated_{slot}.json'
    if curated_path.exists():
        return curated_path

    return None
