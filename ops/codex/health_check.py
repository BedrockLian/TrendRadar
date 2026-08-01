#!/usr/bin/env python3
"""Check the local TrendRadar runtime and recent task health."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from trendradar.runtime.output_protocol import append_run_record, configure_utf8_stdio, output_record, read_recent_records
from trendradar.runtime.paths import CONFIG_DIR, FINGERPRINTS_DB, LOCK_DIR, TRENDRADAR_HOME, ensure_data_dirs


def main() -> int:
    configure_utf8_stdio()
    started = time.monotonic()
    started_at = datetime.now().astimezone().isoformat()
    ensure_data_dirs()
    checks: dict[str, dict] = {}

    checks["python"] = {
        "ok": sys.version_info >= (3, 12),
        "version": sys.version.split()[0],
        "required": ">=3.12",
    }
    required = [
        PROJECT_ROOT / "src" / "trendradar" / "pipeline" / "pipeline_orchestrator.py",
        PROJECT_ROOT / "src" / "trendradar" / "reporting" / "render_markdown.py",
        PROJECT_ROOT / "src" / "trendradar" / "config" / "plan.json",
        CONFIG_DIR / "sources.json",
        CONFIG_DIR / "timeline.yaml",
    ]
    missing = [str(path) for path in required if not path.exists()]
    checks["files"] = {"ok": not missing, "missing": missing}

    try:
        plan = json.loads((PROJECT_ROOT / "src" / "trendradar" / "config" / "plan.json").read_text(encoding="utf-8"))
        jobs = plan.get("jobs", [])
        checks["plan"] = {"ok": len(jobs) == 6, "job_count": len(jobs), "timezone": plan.get("timezone")}
    except (OSError, json.JSONDecodeError) as exc:
        checks["plan"] = {"ok": False, "error": str(exc)}

    checks["database"] = {
        "ok": not FINGERPRINTS_DB.exists() or FINGERPRINTS_DB.stat().st_size > 0,
        "path": str(FINGERPRINTS_DB),
        "bytes": FINGERPRINTS_DB.stat().st_size if FINGERPRINTS_DB.exists() else 0,
    }
    recent = read_recent_records(limit=20)
    checks["recent_runs"] = {
        "ok": not recent or recent[-1].get("status") in {"ok", "silent", "partial"},
        "count": len(recent),
        "last": recent[-1] if recent else None,
    }
    active_locks = [path.name for path in LOCK_DIR.glob("*.lock") if path.is_dir()]
    checks["locks"] = {"ok": not active_locks, "active": active_locks}

    failed = [name for name, result in checks.items() if not result.get("ok", False)]
    status = "error" if failed else "ok"
    result = output_record(
        status=status,
        task="health-check",
        started_at=started_at,
        elapsed=time.monotonic() - started,
        runtime_home=str(TRENDRADAR_HOME),
        checks=checks,
        failed_checks=failed,
    )
    append_run_record(result)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
