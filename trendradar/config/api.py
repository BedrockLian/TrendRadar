"""TrendRadar API 配置 — Key 加载、端点、模型。"""
import os
from pathlib import Path

TRENDRADAR_HOME = Path(os.environ.get('TRENDRADAR_HOME', Path.home() / '.hermes' / 'trendradar'))

API_KEY_ENV = os.environ.get('TRENDRADAR_API_KEY_ENV', 'DEEPSEEK_API_KEY')
API_ENDPOINT_ENV = os.environ.get('TRENDRADAR_API_ENDPOINT_ENV', 'DEEPSEEK_API_ENDPOINT')
MODEL_ENV = os.environ.get('TRENDRADAR_MODEL_ENV', 'DEEPSEEK_MODEL')
DEFAULT_ENDPOINT = os.environ.get('TRENDRADAR_DEFAULT_ENDPOINT', 'https://api.deepseek.com/v1/chat/completions')
DEFAULT_MODEL = os.environ.get('TRENDRADAR_DEFAULT_MODEL', 'deepseek-chat')


def get_api_key(key_name: str | None = None) -> str | None:
    """Get API key from env var first, fallback to .env file."""
    key = os.environ.get(key_name or API_KEY_ENV)
    if key:
        return key
    env_path = Path(os.environ.get('TRENDRADAR_ENV', TRENDRADAR_HOME / '.env'))
    if (TRENDRADAR_HOME not in env_path.resolve().parents
            and env_path.resolve() != TRENDRADAR_HOME.resolve()):
        import warnings
        warnings.warn(f"TRENDRADAR_ENV 路径 {env_path} 不在 TRENDRADAR_HOME 内，已忽略")
        return None
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith('#') or '=' not in line:
                continue
            name, _, val = line.partition('=')
            if name.strip() == (key_name or API_KEY_ENV):
                return val.strip().strip('"').strip("'")
    return None


def get_api_endpoint() -> str:
    return os.environ.get(API_ENDPOINT_ENV, DEFAULT_ENDPOINT)


def get_model() -> str:
    return os.environ.get(MODEL_ENV, DEFAULT_MODEL)
