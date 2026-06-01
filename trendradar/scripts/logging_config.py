"""TrendRadar 日志工厂 — 结构化 Logger + RUN_ID 自动注入。"""
import os
import sys
import logging as _logging
import threading

_LOGGERS: dict[str, _logging.Logger] = {}
_LOGGERS_LOCK = threading.Lock()

def get_logger(name: str = 'trendradar') -> _logging.Logger:
    """获取结构化 logger，按模块名复用。TRENDRADAR_LOG_LEVEL 控制级别。"""
    if name in _LOGGERS:
        return _LOGGERS[name]
    with _LOGGERS_LOCK:
        if name in _LOGGERS:
            return _LOGGERS[name]
        logger = _logging.getLogger(f'trendradar.{name}')
        if not logger.handlers:
            handler = _logging.StreamHandler(sys.stderr)
            handler.setFormatter(_RunIdFormatter(
                '[%(asctime)s] [%(levelname)-5s] [%(name)s] %(message)s',
                datefmt='%Y-%m-%dT%H:%M:%S'
            ))
            logger.addHandler(handler)
            level = os.environ.get('TRENDRADAR_LOG_LEVEL', 'INFO')
            logger.setLevel(getattr(_logging, level, _logging.INFO))
        _LOGGERS[name] = logger
        return logger


class _RunIdFormatter(_logging.Formatter):
    """自动在日志中注入 RUN_ID（如果存在）。"""
    def format(self, record):
        try:
            from trendradar.scripts.common import get_run_id_ctx
            run_id = get_run_id_ctx()
            if run_id:
                record.msg = f"[{run_id}] {record.msg}"
        except (ImportError, AttributeError, LookupError):
            pass
        return super().format(record)
