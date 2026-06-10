"""run_id.py — RUN_ID 生成/解析/上下文管理 (Sprint 2 P1-14)

从 common.py 拆出。
"""
import contextvars
import uuid
from .time_utils import CST, now_cst

# Python 3.14 contextvars: 子线程自动继承 (thread_inherit_context 默认开启)
current_run_id: contextvars.ContextVar[str] = contextvars.ContextVar('run_id', default='')


def gen_run_id(slot: str = "") -> str:
    """生成可读追溯号: YYYYMMDD_slot_短UUID (CST 时区)。

    Examples:
        gen_run_id("morning") → "20260610_morning_a1b2c3d4"
        gen_run_id()          → "20260610_a1b2c3d4"
    """
    date = now_cst().strftime("%Y%m%d")
    short = uuid.uuid4().hex[:8]
    return f"{date}_{slot}_{short}" if slot else f"{date}_{short}"


def parse_run_id(run_id: str) -> dict:
    """解析追溯号 — 反向工程 gen_run_id() 输出。

    Returns:
        {date, slot, uid} dict; missing fields default to ''.
    """
    parts = run_id.split("_")
    return {
        "date": parts[0] if parts else "",
        "slot": parts[1] if len(parts) > 2 else "",
        "uid": parts[-1] if len(parts) > 1 else "",
    }


def run_id_marker(run_id: str) -> str:
    """WeCom 不可见追溯标记 — 放在消息末尾。

    用零宽空格开头, 用户不可见。
    """
    return f"\n\u200b[rid:{run_id}]"


def set_run_id_ctx(run_id: str):
    """设置 contextvar, 子线程自动继承 (Python 3.14 thread_inherit_context)。"""
    current_run_id.set(run_id)


def get_run_id_ctx() -> str:
    """获取当前 contextvar 中的 RUN_ID。"""
    return current_run_id.get()
