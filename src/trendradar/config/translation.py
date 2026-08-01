"""TrendRadar 翻译配置。"""
import os

TRANSLATE_BATCH_SIZE = int(os.environ.get('TRENDRADAR_TRANSLATE_BATCH_SIZE', 10))
TRANSLATE_BATCH_MAX_CONCURRENT = int(os.environ.get('TRENDRADAR_TRANSLATE_CONCURRENT', 4))
# Sprint 3: 6→4，因为翻译+扩写并发时 2×4=8 仍安全；单跑 4 也够快

# ── Exponential Backoff 熔断配置 ────────────────────────────────────────────
# 针对 Trap 28: DeepSeek openresty 流中断 (RemoteProtocolError)
RETRY_BASE_DELAY = 2.0        # 初始等待秒数
RETRY_MAX_DELAY = 30.0        # 上限秒数
RETRY_JITTER = 0.5            # ±50% 随机抖动
RETRY_MAX_ATTEMPTS = 4        # 最多 5 次尝试 (初始 + 4 次重试)
CIRCUIT_BREAKER_THRESHOLD = 5  # 连续 5 个 batch 失败 → 熔断（瞬态429不应触发）
