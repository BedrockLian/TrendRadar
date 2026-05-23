"""TrendRadar 上下文跟踪 — contextvars RUN_ID 自动传播（v5.2.0）。

在 free-threaded（禁用 GIL）模式下，子线程自动继承 contextvars。
push_prepare.py 中使用 set_run_id() 设置后，所有子线程无需手动传参。
"""

import contextvars

current_run_id: contextvars.ContextVar[str] = contextvars.ContextVar('run_id', default='')


def set_run_id(run_id: str):
    current_run_id.set(run_id)


def get_run_id() -> str:
    return current_run_id.get()
