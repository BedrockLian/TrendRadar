"""TrendRadar 统一配置 — 向后兼容 re-export 中心。

所有常量定义已迁移到子模块：
  config/domains.py  — 领域常量
  config/scoring.py  — 评分参数
  config/api.py      — API Key/端点/模型
  config/translation.py — 翻译配置
  config/fetching.py — 抓取配置
  config/proxy.py    — 代理配置
  config/heat_tracking.py — 热度追踪/指纹参数
  scripts/file_utils.py   — 路径工厂/压缩 I/O
  scripts/logging_config.py — Logger 工厂

此文件为向后兼容层——所有现有 `from settings import X` 无需改动。
"""
from pathlib import Path
import os

TRENDRADAR_HOME = Path(os.environ.get('TRENDRADAR_HOME', Path.home() / '.hermes' / 'trendradar'))

# ── 领域常量 ─────────────────────────────────────────────
from trendradar.config.domains import (
    DOMAINS, DOMAIN_LABELS, MAX_PER_DOMAIN, DOMAIN_EMOJI,
    SLOT_NAMES, DAILY_LIMIT, BRIEFING_RATIO,
    HIGH_AUTHORITY_THRESHOLD, TIER_DIVERSITY_MIN,
)

# ── 评分参数 ─────────────────────────────────────────────
from trendradar.config.scoring import (
    MIN_SCORE, MAX_SAME_SOURCE, DIVERSITY_PENALTY_FACTOR, MAX_SOURCE_PCT,
    SCORE_HEAT_WORDS, HEAT_WORDS, SEARCH_RATIO,
    TITLE_CLARITY_LOW, TITLE_CLARITY_HIGH,
    RECENCY_HOURS_HIGH, RECENCY_HOURS_MID, RECENCY_HOURS_LOW,
)

# ── API 配置 ─────────────────────────────────────────────
from trendradar.config.api import (
    API_KEY_ENV, API_ENDPOINT_ENV, MODEL_ENV,
    DEFAULT_ENDPOINT, DEFAULT_MODEL,
    get_api_key, get_api_endpoint, get_model,
)

# ── 翻译配置 ─────────────────────────────────────────────
from trendradar.config.translation import (
    TRANSLATE_BATCH_SIZE, TRANSLATE_BATCH_MAX_CONCURRENT,
)

# ── 抓取配置 ─────────────────────────────────────────────
from trendradar.config.fetching import (
    EXTERNAL_CONCURRENT, TIMEOUT_SEC, FETCH_RETRIES,
    API_CALL_TIMEOUT, API_RETRIES, API_RETRY_BACKOFF,
)

# ── 代理配置 ─────────────────────────────────────────────
from trendradar.config.proxy import (
    PROXY_URL, DOMESTIC_PROXY_PATTERNS, needs_proxy, check_proxy_alive,
)

# ── 热度追踪 ─────────────────────────────────────────────
from trendradar.config.heat_tracking import (
    HEAT_SLEEP_HOURS, HEAT_DEEP_CYCLES, HEAT_DEEP_SPAN,
    HEAT_SUSTAINED_CYCLES, HEAT_SUSTAINED_SPAN,
    FINGERPRINT_MD5_LEN, FINGERPRINT_URL_SEGMENTS, FINGERPRINT_TITLE_TRUNCATE,
)

# ── 文件工具 ─────────────────────────────────────────────
from trendradar.scripts.file_utils import (
    get_data_dir, get_cache_dir, get_config_dir,
    raw_path, curated_path, batch_path,
    atomic_write_json, write_compressed, read_compressed,
)

# ── 日志工厂 ─────────────────────────────────────────────
from trendradar.scripts.logging_config import get_logger  # noqa: E402, F401

# ── 存储单例 ─────────────────────────────────────────────
import threading as _threading

_STORAGE_LOCK = _threading.Lock()
_STORAGE_VAL = None
_STORAGE_SENTINEL = object()

def get_storage():
    """返回全局 Storage 单例（共享连接池 + WAL checkpoint）。"""
    global _STORAGE_VAL
    if _STORAGE_VAL is not None:
        return _STORAGE_VAL
    with _STORAGE_LOCK:
        if _STORAGE_VAL is not None:
            return _STORAGE_VAL
        from trendradar.scripts.storage import Storage
        _STORAGE_VAL = Storage(get_data_dir())
        return _STORAGE_VAL


def ensure_db_migrated(db_path=None):
    """确保数据库 schema 为最新版本。"""
    from trendradar.migrations.runner import migrate
    if db_path is None:
        db_path = get_data_dir() / 'fingerprints.db'
    return migrate(db_path)


# ── GIL 检查（保留原逻辑）─────────────────────────────────
import sys as _sys


def _check_gil():
    global _GIL_OK
    _GIL_OK = True
    if hasattr(_sys, '_is_gil_enabled') and not _sys._is_gil_enabled():
        return
    if '3.14' in _sys.version and 'free-threading' not in _sys.version.lower():
        gil = os.environ.get('PYTHON_GIL', '')
        if gil != '0':
            import warnings
            warnings.warn(
                f"PYTHON_GIL={gil or '(unset)'} — 3.14t 建议 export PYTHON_GIL=0",
                RuntimeWarning,
            )


_GIL_OK = None
_GIL_LOCK = _threading.Lock()


def _ensure_gil_ok():
    global _GIL_OK
    if _GIL_OK is not None:
        return _GIL_OK
    with _GIL_LOCK:
        if _GIL_OK is not None:
            return _GIL_OK
        _check_gil()
        return _GIL_OK
