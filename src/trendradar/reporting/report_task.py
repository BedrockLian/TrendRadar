#!/usr/bin/env python3
"""Prepare weekly or monthly report evidence for a Codex report task."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime

from trendradar.runtime.output_protocol import append_run_record, configure_utf8_stdio, output_record


def main() -> int:
    configure_utf8_stdio()
    parser = argparse.ArgumentParser(description="Prepare TrendRadar report evidence")
    parser.add_argument("--period", choices=("weekly", "monthly"), required=True)
    args = parser.parse_args()
    started = time.monotonic()
    started_at = datetime.now().astimezone().isoformat()

    from trendradar.reporting.aggregate_monthly import list_recent_files

    days = 7 if args.period == "weekly" else 32
    files = list_recent_files(days)
    evidence = {
        "period": args.period,
        "days": days,
        "curated_files": files,
        "instruction": "Codex should synthesize a source-backed Markdown report from these files.",
    }
    result = output_record(
        status="ok" if files else "silent",
        task=f"{args.period}-report",
        started_at=started_at,
        elapsed=time.monotonic() - started,
        evidence=evidence,
    )
    append_run_record(result)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
