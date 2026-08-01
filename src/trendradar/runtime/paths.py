"""Runtime paths shared by every TrendRadar entry point.

The repository is executable in-place. In that mode code/configuration stays
under ``trendradar/`` while mutable state is isolated in ``.runtime/``. A
deployment can override the state root with ``TRENDRADAR_HOME``.
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = PACKAGE_ROOT.parents[1]


def _resolve_trendradar_home() -> Path:
    configured = os.environ.get("TRENDRADAR_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    if (PROJECT_ROOT / ".git").exists():
        return (PROJECT_ROOT / ".runtime").resolve()
    return PACKAGE_ROOT.resolve()


TRENDRADAR_HOME: Path = _resolve_trendradar_home()

# Mutable runtime state.
DATA_DIR = TRENDRADAR_HOME / "data"
CACHE_DIR = TRENDRADAR_HOME / "cache"
ARCHIVE_DIR = TRENDRADAR_HOME / "archive"
LOGS_DIR = TRENDRADAR_HOME / "logs"
OUTPUT_DIR = TRENDRADAR_HOME / "outputs"
LOCK_DIR = TRENDRADAR_HOME / "locks"

# Configuration is code-owned for an in-place checkout. A deployment may
# provide a copied config directory below its explicit runtime root.
_runtime_config = TRENDRADAR_HOME / "config"
CONFIG_DIR = _runtime_config if _runtime_config.exists() else PACKAGE_ROOT / "config"

PUSH_LOG = DATA_DIR / "push_log.json"
RUN_LOG = DATA_DIR / "run_log.jsonl"
FINGERPRINTS_DB = DATA_DIR / "fingerprints.db"
SOURCE_PENALTY = DATA_DIR / "source_penalty.json"
SOURCE_HEALTH = DATA_DIR / "source_health.json"


def ensure_data_dirs() -> None:
    """Create all mutable directories needed by a first run."""
    for directory in (
        TRENDRADAR_HOME,
        DATA_DIR,
        CACHE_DIR,
        ARCHIVE_DIR,
        LOGS_DIR,
        OUTPUT_DIR,
        LOCK_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def get_data_dir() -> Path:
    return DATA_DIR


def get_cache_dir() -> Path:
    return CACHE_DIR


def get_config_dir() -> Path:
    return CONFIG_DIR
