"""TrendRadar 投递配置 — WeCom 分片常量等。"""

# WeCom 硬限制 4096 bytes。3800 留出 JSON wrapper + metadata 空间。
WECOM_MAX_BYTES = 4096
WECOM_FRAGMENT_SAFE_BYTES = 3800

# 硬切分片的续接标记
WECOM_CONT_MARKER = "\n...(续)"
WECOM_PREV_MARKER = "(接上)...\n"
