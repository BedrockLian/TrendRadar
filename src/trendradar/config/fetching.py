"""TrendRadar 抓取配置 — 连接池、超时、重试。

v2 (2026-06-05)：TIMEOUT 8→5s, FETCH_RETRIES 1→0
- Batch 内只跑 1 次尝试（不再 backoff 重试），单源耗时上限 5s
- 失败走 _fetch_batch 末尾的"降级重试"通道（独立 15s 超时，独立尝试）
- 实测 41 源 23.9s → 预期 8-12s，南华早报等慢源拖整体时长被根治
"""
EXTERNAL_CONCURRENT = 60   # 动态：应 ≥ sources.json 源数（当前 46）；2026-06-10 改为 60
TIMEOUT_SEC = 6            # 单次尝试超时（含 DNS+TLS+首字节+body）
FETCH_RETRIES = 0          # batch 内不重试；失败走降级重试通道

API_CALL_TIMEOUT = 60
API_RETRIES = 3
API_RETRY_BACKOFF = 2
