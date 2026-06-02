"""TrendRadar 文件工具 — 路径工厂、原子写入、压缩 I/O。"""
import os
import sys
import tempfile
import json as _json
from pathlib import Path
import threading
from typing import Optional


TRENDRADAR_HOME: Path = Path(os.environ.get(
    'TRENDRADAR_HOME', Path.home() / '.hermes' / 'trendradar'
))


_DATA_DIR_LOCK = threading.Lock()
_DATA_DIR_VAL: Optional[Path] = None
_DATA_DIR_SENTINEL = object()

def get_data_dir() -> Path:
    global _DATA_DIR_VAL
    if _DATA_DIR_VAL is not None:
        return _DATA_DIR_VAL
    with _DATA_DIR_LOCK:
        if _DATA_DIR_VAL is not None:
            return _DATA_DIR_VAL
        d = TRENDRADAR_HOME / 'data'
        d.mkdir(parents=True, exist_ok=True)
        _DATA_DIR_VAL = d
        return d


_CACHE_DIR_LOCK = threading.Lock()
_CACHE_DIR_VAL: Optional[Path] = None
_CACHE_DIR_SENTINEL = object()

def get_cache_dir() -> Path:
    global _CACHE_DIR_VAL
    if _CACHE_DIR_VAL is not None:
        return _CACHE_DIR_VAL
    with _CACHE_DIR_LOCK:
        if _CACHE_DIR_VAL is not None:
            return _CACHE_DIR_VAL
        d = TRENDRADAR_HOME / 'cache'
        d.mkdir(parents=True, exist_ok=True)
        _CACHE_DIR_VAL = d
        return d

_CONFIG_DIR_LOCK = threading.Lock()
_CONFIG_DIR_VAL: Optional[Path] = None
_CONFIG_DIR_SENTINEL = object()

def get_config_dir() -> Path:
    """返回 config/ 目录（sources.json, ai_interests.yaml 等）。"""
    global _CONFIG_DIR_VAL
    if _CONFIG_DIR_VAL is not None:
        return _CONFIG_DIR_VAL
    with _CONFIG_DIR_LOCK:
        if _CONFIG_DIR_VAL is not None:
            return _CONFIG_DIR_VAL
        _CONFIG_DIR_VAL = TRENDRADAR_HOME / 'config'
        return _CONFIG_DIR_VAL


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
            _json.dump(data, f, ensure_ascii=False, **kwargs)
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
