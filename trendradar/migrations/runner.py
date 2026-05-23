"""轻量 SQLite 迁移引擎。无需 Alembic，约 80 行。"""
import sqlite3
import sys
import re
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).parent


def _current_version(conn: sqlite3.Connection) -> int:
    """读取当前 schema 版本。"""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS _migrations "
        "(version INTEGER PRIMARY KEY, applied_at TEXT)"
    )
    row = conn.execute("SELECT COALESCE(MAX(version), 0) FROM _migrations").fetchone()
    return row[0] if row else 0


def _available_migrations() -> list[tuple[int, str, str]]:
    """扫描 migrations/ 目录，返回 (版本号, 文件名, SQL) 列表。"""
    migrations = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        m = re.match(r"(\d+)_(\w+)\.sql", f.name)
        if m:
            migrations.append((int(m.group(1)), f.name, f.read_text()))
    return migrations


def migrate(db_path: Path | str) -> int:
    """执行所有未应用的迁移，返回新版本号。"""
    conn = sqlite3.connect(str(db_path))
    try:
        current = _current_version(conn)
        for ver, name, sql in _available_migrations():
            if ver > current:
                conn.executescript(sql)
                conn.execute(
                    "INSERT INTO _migrations (version, applied_at) "
                    "VALUES (?, datetime('now'))",
                    (ver,),
                )
                print(
                    f"[MIGRATE] 已应用 {name} (v{ver})",
                    file=sys.stderr,
                )
        conn.commit()
        return _current_version(conn)
    finally:
        conn.close()
