"""paths.py — TrendRadar 路径单一来源（SSOT）

设计 (2026-06-10, Agent A 审计 P1-12):
- 消除 scripts/ 内 5+ 种路径定义方式（file_utils.get_data_dir / Path(__file__).parent / "data" / TRENDRADAR_HOME 重定义 等）
- 所有"运行时绝对路径"统一在此处
- 双层布局兼容: 运行时在 C:\\Users\\ASUS\\AppData\\Local\\hermes\\trendradar\\
  Python 包内（trendradar/scripts/）和顶层（scripts/）都用同一份

使用:
    from trendradar.scripts.paths import DATA_DIR, CACHE_DIR, CONFIG_DIR
    # 或
    from trendradar.scripts import paths  # 然后用 paths.DATA_DIR 等

注意:
- 不导出 LOG_DIR / OUTPUT_DIR（这些是局部概念，没必要 SSOT）
- TRENDRADAR_HOME 是只读常量，不允许运行时改
"""

from pathlib import Path

# ── 运行时根 ──────────────────────────────────────────────────
# 当前文件: trendradar/scripts/paths.py
# parents[0] = trendradar/scripts/
# parents[1] = trendradar/         ← 这是 TRENDRADAR_HOME（运行时根, 即包内 trendradar/）
# parents[2] = hermes/             ← HERMES_HOME
#
# 注意: TRENDRADAR_HOME = parents[1] = 包内 trendradar/ 目录。
# 内层 data/cache 已 Junction 到外层（参见 P0-4 + skill trendradar-runtime-maintenance §3），
# 所以读 paths.DATA_DIR 实际看到的是外层 data。但 WRITE 也会落到外层（junction 透明）。
#
# 关键: 如果某些 caller 用 SCRIPTS_DIR.parent.parent（如 pipeline_orchestrator.py:39），
# 那是外层 trendradar/ 目录（因为 __file__ 在外层 scripts/ 时 parents[1] = 外层 trendradar/），
# **与本文件解析的路径不同**！所以本文件只能从 trendradar.scripts.* 上下文用。
# 顶层 scripts/ 的脚本应该用 file_utils.get_data_dir()（其内部走另一套解析）。
TRENDRADAR_HOME: Path = Path(__file__).resolve().parents[1]
HERMES_HOME: Path = Path(__file__).resolve().parents[2]

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
