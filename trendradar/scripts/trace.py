"""TrendRadar 上下文跟踪 — contextvars RUN_ID 自动传播（v5.2.0）。

在 free-threaded（禁用 GIL）模式下，子线程自动继承 contextvars。
push_prepare.py 中使用 set_run_id() 设置后，所有子线程无需手动传参。

注意：此模块是 common.py 的兼容层，实际 ContextVar 定义在 common.py 中。
"""

from trendradar.scripts.common import current_run_id, set_run_id_ctx, get_run_id_ctx


def set_run_id(run_id: str):
    set_run_id_ctx(run_id)


def get_run_id() -> str:
    return get_run_id_ctx()
