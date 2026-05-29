#!/usr/bin/env python3
"""TrendRadar 公共工具 — 追溯号生成 + 解析 + 标记 + RUN_ID contextvar。"""

import uuid, re
import contextvars
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))

# Python 3.14 contextvars: 子线程自动继承（thread_inherit_context 默认开启）
current_run_id: contextvars.ContextVar[str] = contextvars.ContextVar('run_id', default='')
def gen_run_id(slot: str = "") -> str:
    """生成可读追溯号: YYYYMMDD_slot_短UUID（CST 时区）。"""
    date = datetime.now(CST).strftime("%Y%m%d")
    short = uuid.uuid4().hex[:8]
    return f"{date}_{slot}_{short}" if slot else f"{date}_{short}"


def parse_run_id(run_id: str) -> dict:
    """解析追溯号"""
    parts = run_id.split("_")
    if len(parts) < 2:
        return {"date": parts[0], "slot": "", "uid": ""}
    return {"date": parts[0], "slot": parts[1] if len(parts) > 2 else "", "uid": parts[-1]}


def run_id_marker(run_id: str) -> str:
    """WeCom 不可见追溯标记 — 放在消息末尾"""
    return f"\n\u200b[rid:{run_id}]"  # 零宽空格开头，用户不可见


def set_run_id_ctx(run_id: str):
    """设置 contextvar，子线程自动继承（Python 3.14 thread_inherit_context）。"""
    current_run_id.set(run_id)


def get_run_id_ctx() -> str:
    """获取当前 contextvar 中的 RUN_ID。"""
    return current_run_id.get()

# ── Public API aliases (was trace.py, merged into common) ──────────────

def set_run_id(run_id: str):
    """Set current RUN_ID (public interface)."""
    current_run_id.set(run_id)

def get_run_id() -> str:
    """Get current RUN_ID (public interface)."""
    return current_run_id.get()

__all__ = ['CST', 'current_run_id', 'gen_run_id', 'parse_run_id',
           'run_id_marker', 'set_run_id', 'get_run_id',
           'set_run_id_ctx', 'get_run_id_ctx']
