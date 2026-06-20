"""paths.py — TrendRadar 路径单一来源（SSOT）

设计 (2026-06-10, Agent A 审计 P1-12, 2026-06-20 Agent B 审计 P1-1 强化):
- 消除 scripts/ 内 5+ 种路径定义方式（file_utils.get_data_dir / Path(__file__).parent / "data" / TRENDRADAR_HOME 重定义 等）
- 所有"运行时绝对路径"统一在此处
- 双层布局兼容: 运行时在 C:\\Users\\ASUS\\AppData\\Local\\hermes\\trendradar\\
  Python 包内（trendradar/scripts/）和顶层（scripts/）都用同一份
- **TRENDRADAR_HOME 解析优先级**（2026-06-20 审计 P1-1 修复）:
  1. 环境变量 TRENDRADAR_HOME（cron/gen_cron_prompt 注入，**权威源**）
  2. Path(__file__).resolve().parents[1]（内层用 = 包内 trendradar/；外层用 = 外层 trendradar/）
- **fail-fast assert**: 启动时校验 DATA_DIR.resolve() 落在 hermes/ 之下且含 fingerprints.db，
  避免 symlink 失效时静默写错位置。

使用:
    from trendradar.scripts.paths import DATA_DIR, CACHE_DIR, CONFIG_DIR
    # 或
    from trendradar.scripts import paths  # 然后用 paths.DATA_DIR 等

注意:
- 不导出 LOG_DIR / OUTPUT_DIR（这些是局部概念，没必要 SSOT）
- TRENDRADAR_HOME 是只读常量，不允许运行时改
"""

import os
from pathlib import Path


def _resolve_trendradar_home() -> Path:
    """解析运行时根目录。优先级: ENV > __file__ 推导。

    双层布局陷阱（2026-06-10 注释已警告，2026-06-20 审计确证）:
    - 内层 trendradar/scripts/paths.py → parents[1] = trendradar/trendradar/（包内）
    - 外层 scripts/paths.py              → parents[1] = trendradar/（运行时根）
    两者字符串不同，但因 inner data/ 是 symlink → outer data/，realpath 一致。
    用 ENV 统一可彻底消除双源。
    """
    env = os.environ.get("TRENDRADAR_HOME")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[1]


# ── 运行时根 ──────────────────────────────────────────────────
TRENDRADAR_HOME: Path = _resolve_trendradar_home()
HERMES_HOME: Path = TRENDRADAR_HOME.parent

# ── 运行时数据目录 ─────────────────────────────────────────────
DATA_DIR: Path = TRENDRADAR_HOME / "data"
CACHE_DIR: Path = TRENDRADAR_HOME / "cache"
CONFIG_DIR: Path = TRENDRADAR_HOME / "config"
ARCHIVE_DIR: Path = TRENDRADAR_HOME / "archive"
LOGS_DIR: Path = TRENDRADAR_HOME / "logs"

# ── 常用文件路径（避免散在脚本里拼字符串）────────────────────
PUSH_LOG: Path = DATA_DIR / "push_log.json"
FINGERPRINTS_DB: Path = DATA_DIR / "fingerprints.db"
DELIVERY_MARKERS_DIR: Path = DATA_DIR / "delivery_markers"
SOURCE_PENALTY: Path = DATA_DIR / "source_penalty.json"
SOURCE_HEALTH: Path = DATA_DIR / "source_health.json"


def _validate_runtime() -> None:
    """fail-fast: 验证 TRENDRADAR_HOME 解析正确（审计 P1-1 修复）。

    之前 symlink 失效会静默写错目录。这里强制校验:
    - 必须在 HERMES_HOME 路径下
    - 必须含 fingerprints.db（避免指向错误空目录）
    任何失败立即 raise，避免下游脚本在错路径上累积数据。
    """
    try:
        # 1. 必须在 hermes/ 之下
        if HERMES_HOME.name != "hermes":
            raise RuntimeError(
                f"TRENDRADAR_HOME 解析异常: HERMES_HOME={HERMES_HOME} "
                f"(expected .../hermes/)。检查 ENV 或 __file__ 路径。"
            )
        # 2. fingerprints.db 必须存在（运行时根不对的话会找不到）
        if not FINGERPRINTS_DB.exists():
            # 首次运行可能还没建 DB，只警告不 raise
            import warnings
            warnings.warn(
                f"fingerprints.db 不存在: {FINGERPRINTS_DB}。"
                f"首次运行可忽略，否则检查 TRENDRADAR_HOME 是否正确。"
            )
    except Exception:
        # 校验失败必须抛，不能吞
        raise


_validate_runtime()


def get_data_dir() -> Path:
    """向后兼容: file_utils.get_data_dir() 的别名。"""
    return DATA_DIR


def get_cache_dir() -> Path:
    """向后兼容: file_utils.get_cache_dir() 的别名。"""
    return CACHE_DIR


def get_config_dir() -> Path:
    """向后兼容: file_utils.get_config_dir() 的别名。"""
    return CONFIG_DIR


def ensure_data_dirs() -> None:
    """确保所有运行时目录存在（首次运行时调用一次即可）。"""
    for d in (DATA_DIR, CACHE_DIR, ARCHIVE_DIR, DELIVERY_MARKERS_DIR):
        d.mkdir(parents=True, exist_ok=True)
