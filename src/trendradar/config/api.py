"""TrendRadar API 配置 — Key 加载、端点、模型。"""
import os
from pathlib import Path
from trendradar.runtime.paths import TRENDRADAR_HOME

API_KEY_ENV = os.environ.get('TRENDRADAR_API_KEY_ENV', 'DEEPSEEK_API_KEY')
API_ENDPOINT_ENV = os.environ.get('TRENDRADAR_API_ENDPOINT_ENV', 'DEEPSEEK_API_ENDPOINT')
MODEL_ENV = os.environ.get('TRENDRADAR_MODEL_ENV', 'DEEPSEEK_MODEL')
DEFAULT_ENDPOINT = os.environ.get('TRENDRADAR_DEFAULT_ENDPOINT', 'https://api.deepseek.com/v1/chat/completions')
DEFAULT_MODEL = os.environ.get('TRENDRADAR_DEFAULT_MODEL', 'deepseek-chat')


def _read_env_file(env_path: Path, key_name: str) -> str | None:
    """Read a key from .env file. Returns value or None."""
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith('#') or '=' not in line:
            continue
        name, _, val = line.partition('=')
        if name.strip() == key_name:
            return val.strip().strip('"').strip("'")
    return None


def get_api_key(key_name: str | None = None) -> str | None:
    """Get API key from the process environment or runtime-local .env."""
    key = os.environ.get(key_name or API_KEY_ENV)
    if key:
        return key
    lookup = key_name or API_KEY_ENV
    # Runtime-local .env is optional and never required for import.
    env_path = Path(os.environ.get('TRENDRADAR_ENV', TRENDRADAR_HOME / '.env'))
    if env_path.exists():
        val = _read_env_file(env_path, lookup)
        if val:
            return val
    return None


def get_api_endpoint() -> str:
    return os.environ.get(API_ENDPOINT_ENV, DEFAULT_ENDPOINT)


def get_model() -> str:
    return os.environ.get(MODEL_ENV, DEFAULT_MODEL)
