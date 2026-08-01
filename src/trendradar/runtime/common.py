"""common.py — 公共工具聚合模块 (Sprint 2 P1-14 重构)

历史:
- v1 (2026 早期): 7KB 包含 CST + gen_run_id
- v2 (2026-05): 14KB 加入 Lazy / curated_paths / _parse_line_pairs / STOP_WORDS
- v3 (2026-06-10, Sprint 2 P1-14): 拆分为独立模块, 本文件只做 re-export

新模块:
- time_utils     — CST 时区
- lazy           — Lazy 线程安全惰性初始化
- run_id         — RUN_ID 生成/解析/上下文
- exit_codes     — 进程退出码
- curated_paths  — curated JSON 文件查找/列表
- text           — 文本处理 (STOP_WORDS, _parse_line_pairs)

公共符号在此集中导出，减少管线模块之间的重复导入。
"""
# ── 内部 re-export ───────────────────────────────────────
try:
    from .time_utils import CST  # noqa: F401
    from .lazy import Lazy  # noqa: F401
    from .run_id import (  # noqa: F401
        current_run_id, gen_run_id, parse_run_id, run_id_marker,
        set_run_id_ctx, get_run_id_ctx,
    )
    from .exit_codes import (  # noqa: F401
        EXIT_SUCCESS, EXIT_NO_CONTENT, EXIT_PARTIAL,
        EXIT_CONFIG_ERROR, EXIT_API_ERROR, EXIT_DB_ERROR, EXIT_FATAL,
    )
    from .curated_paths import (  # noqa: F401
        find_curated_file, list_curated_files, get_data_dir_for_common,
    )
    from .text import STOP_WORDS, _parse_line_pairs  # noqa: F401
except ImportError as exc:
    raise RuntimeError("trendradar.runtime.common must be imported as a package") from exc

__all__ = [
    'CST', 'Lazy',
    'current_run_id', 'gen_run_id', 'parse_run_id', 'run_id_marker',
    'set_run_id_ctx', 'get_run_id_ctx',
    'EXIT_SUCCESS', 'EXIT_NO_CONTENT', 'EXIT_PARTIAL',
    'EXIT_CONFIG_ERROR', 'EXIT_API_ERROR', 'EXIT_DB_ERROR', 'EXIT_FATAL',
    'STOP_WORDS', 'list_curated_files', 'find_curated_file',
    'get_data_dir_for_common',
]
