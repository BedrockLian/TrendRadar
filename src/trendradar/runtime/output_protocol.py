"""Small, stable JSON protocol consumed by Codex scheduled tasks.

Scripts produce data and diagnostics only. The Codex task decides how the
briefing is presented to the user.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from trendradar.runtime.paths import RUN_LOG, ensure_data_dirs

DEFAULT_BUDGET_SECONDS = 180


def configure_utf8_stdio() -> None:
    """Keep JSON/Markdown output lossless on Windows consoles and pipes."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="strict")


def performance_budget_seconds() -> float:
    value = os.environ.get("TRENDRADAR_BUDGET_SECONDS", str(DEFAULT_BUDGET_SECONDS))
    try:
        return max(1.0, float(value))
    except ValueError:
        return float(DEFAULT_BUDGET_SECONDS)


def budget_snapshot(elapsed: float, budget: float | None = None) -> dict[str, Any]:
    limit = performance_budget_seconds() if budget is None else float(budget)
    elapsed = round(max(0.0, elapsed), 3)
    return {
        "budget_seconds": limit,
        "elapsed_seconds": elapsed,
        "remaining_seconds": round(limit - elapsed, 3),
        "within_budget": elapsed <= limit,
    }


def output_record(
    *,
    status: str,
    task: str,
    started_at: str,
    elapsed: float,
    **fields: Any,
) -> dict[str, Any]:
    """Build the common result envelope used by all scheduled entry points."""
    record: dict[str, Any] = {
        "protocol_version": 1,
        "status": status,
        "task": task,
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(),
        "timing": budget_snapshot(elapsed),
    }
    record.update(fields)
    return record


def append_run_record(record: dict[str, Any], path: Path = RUN_LOG) -> None:
    """Append one JSON record, keeping stdout free for the task result."""
    ensure_data_dirs()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


def read_recent_records(path: Path = RUN_LOG, limit: int = 100) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records
