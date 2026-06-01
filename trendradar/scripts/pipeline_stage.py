"""
Pipeline Stage Protocol — 统一 pipeline 阶段返回值契约。

所有管道阶段应返回符合 PipelineStageResult 协议的 dict：
  {'ok': bool, 'result': any, 'elapsed': float | None, 'error': str | None}
"""
from typing import Protocol, runtime_checkable, Any, Optional


@runtime_checkable
class PipelineStageResult(Protocol):
    """pipeline 阶段返回值协议。"""
    ok: bool
    result: Any
    elapsed: Optional[float]
    error: Optional[str]
