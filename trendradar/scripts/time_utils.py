"""time_utils.py — 时区与时间工具 (Sprint 2 P1-14)

从 common.py 拆出。
"""
from datetime import datetime, timezone, timedelta

# 中国标准时间 (CST, UTC+8)
CST = timezone(timedelta(hours=8))


def now_cst() -> datetime:
    """返回当前 CST 时区时间。"""
    return datetime.now(CST)


def parse_iso_cst(iso_str: str) -> datetime:
    """解析 ISO 8601 字符串到 CST-aware datetime。

    兼容带/不带时区的格式:
    - '2026-06-10T12:00:00+08:00' → CST-aware
    - '2026-06-10T04:00:00' → 视为 UTC, 转换到 CST
    """
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(CST)
