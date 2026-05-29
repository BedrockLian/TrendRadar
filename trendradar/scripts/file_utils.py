"""TrendRadar 文件工具 — 路径工厂、原子写入、压缩 I/O。"""
import os
import sys
import tempfile
import json as _json
from pathlib import Path
from functools import lru_cache
from typing import Optional


TRENDRADAR_HOME: Path = Path(os.environ.get(
    'TRENDRADAR_HOME', Path.home() / '.hermes' / 'trendradar'
))


@lru_cache()
def get_data_dir() -> Path:
    d = TRENDRADAR_HOME / 'data'
    d.mkdir(parents=True, exist_ok=True)
    return d


@lru_cache()
def get_cache_dir() -> Path:
    d = TRENDRADAR_HOME / 'cache'
    d.mkdir(parents=True, exist_ok=True)
    return d


def raw_path(date_str: str) -> Path:
    return get_cache_dir() / f'raw_{date_str}.json'


def curated_path(push_id: str, date_str: str | None = None) -> Path:
    p = f'curated_{push_id}'
    if date_str:
        p += f'_{date_str}'
    return get_data_dir() / f'{p}.json'


def batch_path(push_id: str) -> Path:
    return get_cache_dir() / f'batch_{push_id}.json'


def atomic_write_json(path: Path, data, **kwargs):
    """原子写入 JSON：先写临时文件，再 os.replace（原子 rename）。"""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.tmp_', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            _json.dump(data, f, ensure_ascii=False, indent=2, **kwargs)
        os.replace(tmp, path)
    except Exception:
        os.unlink(tmp)
        raise


def _get_zstd():
    try:
        from compression import zstd
        return zstd, 'stdlib'
    except (ImportError, ModuleNotFoundError):
        pass
    try:
        import zstandard as zstd
        return zstd, 'zstandard'
    except ImportError:
        return None


def write_compressed(path: Path, data: dict):
    zstd_impl = _get_zstd()
    if zstd_impl:
        zstd, name = zstd_impl
        raw = _json.dumps(data, ensure_ascii=False, indent=2).encode()
        path.with_suffix('.json.zst').write_bytes(zstd.compress(raw, level=3))
    else:
        atomic_write_json(path, data)


def read_compressed(path: Path) -> dict:
    zst_path = path.with_suffix('.json.zst')
    if not zst_path.exists():
        return _json.loads(path.read_text())
    zstd_impl = _get_zstd()
    if zstd_impl:
        zstd, name = zstd_impl
        return _json.loads(zstd.decompress(zst_path.read_bytes()))
    return _json.loads(path.read_text())
