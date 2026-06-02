"""SQLite migration runner.

Executes `001_initial.sql` (and future `NNN_*.sql` files) against
`fingerprints.db` in versioned order. Used by `cron_maintenance.py`
and the auto-repair path in `cron_health_check.py`.

Public API:
- `migrate(db_path) -> int`   apply all pending migrations, return new version
- `down(db_path, target) -> int`  roll back to target version
- `repair_missing_tables(db_path) -> bool`  add missing core tables without bumping version
"""
