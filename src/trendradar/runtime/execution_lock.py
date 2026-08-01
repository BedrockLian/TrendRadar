"""Process-safe lock for scheduled pipeline jobs."""

from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

from trendradar.runtime.paths import LOCK_DIR, ensure_data_dirs


class ExecutionLock:
    """Directory lock with stale-owner recovery for scheduled work."""

    def __init__(self, name: str, stale_after: int = 900):
        self.name = name
        self.stale_after = stale_after
        self.path = LOCK_DIR / f"{name}.lock"
        self.acquired = False

    def acquire(self) -> bool:
        ensure_data_dirs()
        try:
            self.path.mkdir(parents=False)
        except FileExistsError:
            if self._is_stale():
                self._remove_lock()
                try:
                    self.path.mkdir(parents=False)
                except FileExistsError:
                    return False
            else:
                return False
        (self.path / "owner.json").write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "name": self.name,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.acquired = True
        return True

    def _is_stale(self) -> bool:
        try:
            age = time.time() - self.path.stat().st_mtime
            return age > self.stale_after
        except OSError:
            return False

    def _remove_lock(self) -> None:
        if self.path.exists():
            shutil.rmtree(self.path)

    def release(self) -> None:
        if self.acquired:
            self._remove_lock()
            self.acquired = False

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError(f"execution already in progress: {self.name}")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
