#!/usr/bin/env python3
"""Perform bounded local maintenance for TrendRadar runtime data."""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from trendradar.runtime.output_protocol import append_run_record, configure_utf8_stdio, output_record
from trendradar.runtime.paths import ARCHIVE_DIR, CACHE_DIR, FINGERPRINTS_DB, TRENDRADAR_HOME, ensure_data_dirs


def _remove_old_files(root: Path, older_than: datetime) -> list[str]:
    removed = []
    if not root.exists():
        return removed
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        try:
            if datetime.fromtimestamp(path.stat().st_mtime) < older_than:
                path.unlink()
                removed.append(str(path))
        except OSError:
            continue
    return removed


def main() -> int:
    configure_utf8_stdio()
    started = time.monotonic()
    started_at = datetime.now().astimezone().isoformat()
    ensure_data_dirs()
    actions: dict[str, object] = {}
    actions["cache_removed"] = _remove_old_files(CACHE_DIR, datetime.now() - timedelta(days=3))
    actions["archive_removed"] = _remove_old_files(ARCHIVE_DIR, datetime.now() - timedelta(days=120))

    if FINGERPRINTS_DB.exists():
        try:
            with sqlite3.connect(FINGERPRINTS_DB, timeout=5) as connection:
                connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                connection.execute("VACUUM")
            actions["database"] = "vacuumed"
        except sqlite3.Error as exc:
            actions["database"] = f"skipped: {exc}"
    else:
        actions["database"] = "not_created"

    result = output_record(
        status="ok",
        task="maintenance",
        started_at=started_at,
        elapsed=time.monotonic() - started,
        runtime_home=str(TRENDRADAR_HOME),
        actions=actions,
    )
    append_run_record(result)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
