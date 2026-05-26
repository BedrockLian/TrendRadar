"""TrendRadar 统一配置模块 — 替代各脚本中的硬编码路径和 API Key 加载。"""
from pathlib import Path
import os
import sys
import tempfile
import json as _json
from functools import lru_cache

TRENDRADAR_HOME = Path(os.environ.get('TRENDRADAR_HOME', Path.home() / '.hermes' / 'trendradar'))

# ── 环境锁：Python 3.14t 必须禁用 GIL ────────────────────────────
def _check_gil():
    """检查是否在 free-threaded Python (3.14t) 下正确运行。
    
    若检测到 3.14t 但 PYTHON_GIL != 0，输出警告到 stderr。
    不阻止运行——仅作为诊断提示（部分 C 扩展未声明 GIL 豁免时需要）。
    """
    if hasattr(sys, '_is_gil_enabled') and not sys._is_gil_enabled():
        return  # GIL 已禁用，正常
    if '3.14' in sys.version and 'free-threading' not in sys.version.lower():
        gil = os.environ.get('PYTHON_GIL', '')
        if gil != '0':
            import warnings
            warnings.warn(
                f"PYTHON_GIL={gil or '(unset)'} — 3.14t 建议 export PYTHON_GIL=0 "
                "以启用 free-threading 并发性能。",
                RuntimeWarning,
            )

_check_gil()


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


# ── 领域常量（C1 解耦） ─────────────────────────────────────────────
DOMAINS = ['top_headlines', 'foreign_china', 'tech', 'economy', 'gaming']

DOMAIN_LABELS = {
    'top_headlines': '📰 头条',
    'foreign_china': '🌏 外媒看华',
    'tech': '💻 科技',
    'economy': '📊 经济民生',
    'gaming': '🎮 游戏',
}

MAX_PER_DOMAIN: dict[str, int] = {
    'top_headlines': 6,
    'tech': 7,
    'economy': 6,
    'gaming': 6,
    'foreign_china': 5,
}

DOMAIN_EMOJI = {
    'top_headlines': '📰', 'foreign_china': '🌏',
    'tech': '💻', 'economy': '📊', 'gaming': '🎮',
}

SLOT_NAMES = {'morning': '早报', 'noon': '午间速递', 'evening': '今日回顾'}

DAILY_LIMIT = 80
BRIEFING_RATIO = {'morning': 30, 'noon': 30, 'evening': 20}

# ── 文件命名模板（C3 解耦） ────────────────────────────────────────
def raw_path(date_str: str) -> Path:
    return get_cache_dir() / f'raw_{date_str}.json'

def curated_path(push_id: str, date_str: str | None = None) -> Path:
    p = f'curated_{push_id}'
    if date_str:
        p += f'_{date_str}'
    return get_data_dir() / f'{p}.json'

def batch_path(push_id: str) -> Path:
    return get_cache_dir() / f'batch_{push_id}.json'


# ── 评分参数（C4 解耦） ──────────────────────────────────────────────
## 精选门槛
MIN_SCORE = 6

## 标题清晰度分档（字符数）
TITLE_CLARITY_LOW = 10
TITLE_CLARITY_HIGH = 40

## 时效分档（小时）
RECENCY_HOURS_HIGH = 1
RECENCY_HOURS_MID = 6
RECENCY_HOURS_LOW = 24

## 热度信号词（评分用）
SCORE_HEAT_WORDS = frozenset({'突发', '重磅', '紧急', '首次', '正式', '官宣', '定档', '上线', '新政', '突破'})

## 热度信号词（指纹/追踪用）
HEAT_WORDS = frozenset({'突发', '重磅', '紧急', '首次', '首发', '正式', '官宣', '确认', '定档', '上线', '发布', '新政', '突破', '里程碑', '重大', '最新', '首款', '警告', '战', '大跌', '暴涨', '全球'})

## 搜索标记比例
SEARCH_RATIO = 0.6

## 连接池
RSSHUB_CONCURRENT = 12
EXTERNAL_CONCURRENT = 20
TIMEOUT_SEC = 6
FETCH_RETRIES = 3

## 代理配置（米霍姆）
PROXY_URL = os.environ.get('TRENDRADAR_PROXY', 'http://127.0.0.1:7890')

# 不需要代理的源 URL 前缀/模式（国内中转）
DOMESTIC_PROXY_PATTERNS = (
    'plink.anyfeeder.com',  # 国内 RSS 中转
    '.cn',                   # 国内域名
    '.com.cn',
    'bbc.co.uk',             # BBC 直连可达，代理节点屏蔽 BBC
    'bbci.co.uk',            # BBC RSS feed 域名
)

def needs_proxy(feed_url: str) -> bool:
    """判断 RSS 源是否需要走代理。外媒直连源/RSSHub 走代理，国内中转直连。"""
    url_lower = feed_url.lower()
    # localhost:1200 是 RSSHub，本身不能直达外媒，需代理
    if 'localhost:1200' in url_lower:
        return True
    # 国内中转/国内域名 → 直连
    for pattern in DOMESTIC_PROXY_PATTERNS:
        if pattern in url_lower:
            return False
    # 其余外网域名 → 走代理
    return True

## API 调用
API_CALL_TIMEOUT = 60
API_RETRIES = 3
API_RETRY_BACKOFF = 2

## 热度追踪
HEAT_SLEEP_HOURS = 24
HEAT_DEEP_CYCLES = 3
HEAT_DEEP_SPAN = 12
HEAT_SUSTAINED_CYCLES = 2
HEAT_SUSTAINED_SPAN = 6

## 指纹参数
FINGERPRINT_MD5_LEN = 16
FINGERPRINT_URL_SEGMENTS = 3
FINGERPRINT_TITLE_TRUNCATE = 40

API_KEY_ENV = os.environ.get('TRENDRADAR_API_KEY_ENV', 'DEEPSEEK_API_KEY')
API_ENDPOINT_ENV = os.environ.get('TRENDRADAR_API_ENDPOINT_ENV', 'DEEPSEEK_API_ENDPOINT')
MODEL_ENV = os.environ.get('TRENDRADAR_MODEL_ENV', 'DEEPSEEK_MODEL')
DEFAULT_ENDPOINT = os.environ.get('TRENDRADAR_DEFAULT_ENDPOINT', 'https://api.deepseek.com/v1/chat/completions')
DEFAULT_MODEL = os.environ.get('TRENDRADAR_DEFAULT_MODEL', 'deepseek-chat')


def get_api_key(key_name: str | None = None) -> str | None:
    key = os.environ.get(key_name or API_KEY_ENV)
    if key:
        return key
    env_path = Path(os.environ.get('TRENDRADAR_ENV', TRENDRADAR_HOME / '.env'))
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith('#') or '=' not in line:
                continue
            name, _, val = line.partition('=')
            if name.strip() == (key_name or API_KEY_ENV):
                return val.strip().strip('"').strip("'")
    return None


@lru_cache()
def get_api_endpoint() -> str:
    return os.environ.get(API_ENDPOINT_ENV, DEFAULT_ENDPOINT)


@lru_cache()
def get_model() -> str:
    return os.environ.get(MODEL_ENV, DEFAULT_MODEL)


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
    """获取可用的 zstd 实现。返回 (module, name) 或 None。"""
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
    """zstd 压缩写入 JSON，磁盘占用 ~1/6。fallback: compression.zstd → zstandard → 普通 JSON。"""
    zstd_impl = _get_zstd()
    if zstd_impl:
        zstd, name = zstd_impl
        raw = _json.dumps(data, ensure_ascii=False, indent=2).encode()
        path.with_suffix('.json.zst').write_bytes(zstd.compress(raw, level=3))
    else:
        atomic_write_json(path, data)


def read_compressed(path: Path) -> dict:
    """zstd 解压读取 JSON。fallback: compression.zstd → zstandard → 普通 JSON。"""
    zst_path = path.with_suffix('.json.zst')
    if not zst_path.exists():
        return _json.loads(path.read_text())
    zstd_impl = _get_zstd()
    if zstd_impl:
        zstd, name = zstd_impl
        return _json.loads(zstd.decompress(zst_path.read_bytes()))
    return _json.loads(path.read_text())


# ── 日志工厂 ─────────────────────────────────────────────────────────
import logging as _logging

_LOGGERS: dict[str, _logging.Logger] = {}

def get_logger(name: str = 'trendradar') -> _logging.Logger:
    """获取结构化 logger，按模块名复用。环境变量 TRENDRADAR_LOG_LEVEL 控制级别。
    
    自动注入 RUN_ID（如果 common.current_run_id 已设置）。
    """
    if name in _LOGGERS:
        return _LOGGERS[name]
    logger = _logging.getLogger(f'trendradar.{name}')
    if not logger.handlers:
        handler = _logging.StreamHandler(sys.stderr)
        handler.setFormatter(_RunIdFormatter(
            '[%(asctime)s] [%(levelname)-5s] [%(name)s] %(message)s',
            datefmt='%Y-%m-%dT%H:%M:%S'
        ))
        logger.addHandler(handler)
        level = os.environ.get('TRENDRADAR_LOG_LEVEL', 'INFO')
        logger.setLevel(getattr(_logging, level, _logging.INFO))
    _LOGGERS[name] = logger
    return logger


class _RunIdFormatter(_logging.Formatter):
    """自动在日志中注入 RUN_ID（如果存在）。"""
    def format(self, record):
        try:
            from trendradar.scripts.common import get_run_id_ctx
            run_id = get_run_id_ctx()
            if run_id:
                record.msg = f"[{run_id}] {record.msg}"
        except Exception:
            pass
        return super().format(record)


def ensure_db_migrated(db_path: Path | None = None) -> int:
    """确保数据库 schema 为最新版本。返回当前版本号。"""
    from trendradar.migrations.runner import migrate
    if db_path is None:
        db_path = get_data_dir() / 'fingerprints.db'
    return migrate(db_path)
