#!/usr/bin/env python3
"""Verify that one scheduled briefing produced a timely local artifact."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from trendradar.runtime.output_protocol import append_run_record, configure_utf8_stdio, output_record, read_recent_records


SLOT_BY_HOUR = {9: "morning", 12: "noon", 21: "evening"}


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Check a scheduled TrendRadar briefing output")
    parser.add_argument("--slot", choices=tuple(SLOT_BY_HOUR.values()))
    parser.add_argument("--date", help="YYYY-MM-DD; defaults to today")
    args = parser.parse_args()

    started = time.monotonic()
    started_at = datetime.now().astimezone().isoformat()
    today = args.date or datetime.now().astimezone().strftime("%Y-%m-%d")
    slot = args.slot or SLOT_BY_HOUR.get(datetime.now().astimezone().hour)
    records = read_recent_records(limit=200)
    candidates = [
        record for record in records
        if record.get("task") == "daily-briefing"
        and record.get("push_id") == slot
        and str(record.get("started_at", "")).startswith(today)
    ]
    current = candidates[-1] if candidates else None
    artifact = (current or {}).get("artifacts", {}).get("briefing_path", "")
    if not artifact and current:
        artifact = current.get("artifact_path", "")
    artifact_exists = bool(artifact) and Path(artifact).exists()
    ok = bool(slot and current and current.get("status") in {"ok", "partial", "silent"}) and (
        artifact_exists or current.get("status") == "silent"
    )
    result = output_record(
        status="ok" if ok else "error",
        task="output-watchdog",
        started_at=started_at,
        elapsed=time.monotonic() - started,
        date=today,
        slot=slot,
        artifact_path=artifact,
        artifact_exists=artifact_exists,
        observed=current,
        reason="ok" if ok else "missing or invalid scheduled output",
    )
    append_run_record(result)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
