"""TrendRadar 文件工具 — 路径工厂、原子写入、压缩 I/O。"""
import os
import sys
import tempfile
import json as _json
from pathlib import Path
import threading
from typing import Optional

from trendradar.scripts.lazy import Lazy  # Sprint 2 P1-15


TRENDRADAR_HOME: Path = Path(os.environ.get(
    'TRENDRADAR_HOME', Path.home() / '.hermes' / 'trendradar'
))


def _load_data_dir() -> Path:
    """内部: data 目录加载逻辑 (Sprint 2 P1-15)。"""
    d = TRENDRADAR_HOME / 'data'
    d.mkdir(parents=True, exist_ok=True)
    return d

_DATA_DIR = Lazy(_load_data_dir)

def get_data_dir() -> Path:
    return _DATA_DIR.get()


def _load_cache_dir() -> Path:
    """内部: cache 目录加载逻辑 (Sprint 2 P1-15)。"""
    d = TRENDRADAR_HOME / 'cache'
    d.mkdir(parents=True, exist_ok=True)
    return d

_CACHE_DIR = Lazy(_load_cache_dir)

def get_cache_dir() -> Path:
    return _CACHE_DIR.get()


def _load_config_dir() -> Path:
    """内部: config 目录加载逻辑 (Sprint 2 P1-15)。"""
    return TRENDRADAR_HOME / 'config'

_CONFIG_DIR = Lazy(_load_config_dir)

def get_config_dir() -> Path:
    """返回 config/ 目录（sources.json, ai_interests.yaml 等）。"""
    return _CONFIG_DIR.get()


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
    """双写策略: 总是写可读 .json, 顺手写压缩 .zst（如 zstd 可用）。

    修复 2026-06-10 (Agent B audit): 之前只写 .zst 时被 push_prepare.atomic_write_json 覆盖,
    导致 2.8MB raw cache 全部未压缩。现统一为同时写两份，read_compressed 优先读 .zst。

    重要约定: path 应为"无后缀"基础名, 如 `cache/test_data`。
    实际写入: <base>.json + <base>.json.zst。
    """
    json_path = path.with_suffix('.json')
    # 1) 总是写 .json (向后兼容 + 人工可读)
    atomic_write_json(json_path, data)
    # 2) 顺手写 .zst (zstd 可用时)
    zstd_impl = _get_zstd()
    if zstd_impl:
        zstd, _ = zstd_impl
        raw = json_path.read_bytes()
        zst_path = path.with_suffix('.json.zst')
        zst_path.write_bytes(zstd.compress(raw, level=3))


def read_compressed(path: Path) -> dict:
    """优先读 .zst（解压），fallback 到 .json。

    约定: path 应为"无后缀"基础名, 跟 write_compressed 对称。
    """
    zst_path = path.with_suffix('.json.zst')
    if zst_path.exists():
        zstd_impl = _get_zstd()
        if zstd_impl:
            zstd, _ = zstd_impl
            try:
                return _json.loads(zstd.decompress(zst_path.read_bytes()))
            except Exception:
                pass  # zst 损坏, 降级读 .json
    # 降级: 读 .json (write_compressed 双写保证)
    json_path = path.with_suffix('.json')
    return _json.loads(json_path.read_text())
