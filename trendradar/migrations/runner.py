"""轻量 SQLite 迁移引擎。支持 up (向前) 和 down (回滚) 迁移。无需 Alembic。"""

import re
import sqlite3
import sys
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


def _extract_down_sql(migration_sql: str) -> str | None:
    """从迁移 SQL 中提取 -- down: 标记后的回滚 SQL。"""
    match = re.search(r'--\s*down:\s*(.+?)(?:\n--|$)', migration_sql, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def migrate(db_path: Path | str, force: bool = False) -> int:
    """执行所有未应用的迁移，返回新版本号。
    
    若 force=True，即使 _migrations 已记录也会重新执行迁移 SQL
    （用于修复表被意外删除但迁移记录仍存在的场景）。
    """
    conn = sqlite3.connect(str(db_path))
    try:
        current = _current_version(conn)
        applied = 0
        for ver, name, sql in _available_migrations():
            if force or ver > current:
                conn.executescript(sql)
                if ver > current:
                    conn.execute(
                        "INSERT INTO _migrations (version, applied_at) "
                        "VALUES (?, datetime('now'))",
                        (ver,),
                    )
                applied += 1
                print(
                    f"[MIGRATE] {'[force] ' if force and ver <= current else ''}"
                    f"已应用 {name} (v{ver})",
                    file=sys.stderr,
                )
        conn.commit()
        return _current_version(conn)
    finally:
        conn.close()


def down(db_path: Path | str, target_version: int = 0) -> int:
    """回滚迁移到目标版本（默认 0 = 清空全部迁移）。

    从当前版本开始，按逆序执行每条迁移的 -- down: 回滚 SQL，
    并从 _migrations 表中删除已回滚的记录。

    Args:
        db_path: 数据库路径
        target_version: 回滚目标版本号（含）。小于此版本的迁移不会被回滚。

    Returns:
        回滚后的当前版本号。

    Raises:
        ValueError: 若某条迁移缺少 -- down: 回滚 SQL。
    """
    conn = sqlite3.connect(str(db_path))
    try:
        current = _current_version(conn)

        if current <= target_version:
            print(
                f"[MIGRATE] 当前版本 v{current} <= 目标 v{target_version}，无需回滚",
                file=sys.stderr,
            )
            return current

        migrations = _available_migrations()

        # 逆序回滚：从当前版本向下到 target_version+1
        rolled_back = 0
        for ver, name, sql in reversed(migrations):
            if ver <= target_version:
                continue
            if ver > current:
                # 迁移从未执行过，跳过
                continue

            down_sql = _extract_down_sql(sql)
            if not down_sql:
                raise ValueError(
                    f"迁移 {name} (v{ver}) 缺少 -- down: 回滚 SQL。"
                    f"无法安全回滚。请在 {name} 末尾添加 `-- down: <SQL>` 注释。"
                )

            print(
                f"[MIGRATE] ⬇ 回滚 {name} (v{ver}): {down_sql[:80]}...",
                file=sys.stderr,
            )
            conn.executescript(down_sql)
            conn.execute(
                "DELETE FROM _migrations WHERE version = ?", (ver,)
            )
            rolled_back += 1

        if rolled_back == 0:
            print(
                f"[MIGRATE] 无可回滚的迁移（当前 v{current}，目标 v{target_version}）",
                file=sys.stderr,
            )

        conn.commit()
        new_version = _current_version(conn)
        print(
            f"[MIGRATE] 回滚完成: v{current} → v{new_version}（已回滚 {rolled_back} 条迁移）",
            file=sys.stderr,
        )
        return new_version
    finally:
        conn.close()


def repair_missing_tables(db_path: Path | str) -> bool:
    """检测并修复丢失的表。
    
    当 _migrations 已记录版本但对应表被意外删除时，
    migrate() 会因版本检查跳过重新创建。
    此函数从迁移 SQL 中提取 CREATE TABLE 语句并仅重建缺失的表。
    
    返回 True 表示执行了修复操作。
    """
    conn = sqlite3.connect(str(db_path))
    try:
        existing = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        conn.close()
    
    # 核心业务表清单（与 001_initial.sql 保持一致）
    required = {'fingerprints', 'heat_tracker'}
    missing = required - existing
    
    if not missing:
        return False
    
    # 从迁移文件中提取 CREATE TABLE 语句
    create_stmts = _extract_create_tables(missing)
    
    if not create_stmts:
        print(
            f"[REPAIR] 检测到缺失表 {missing} 但迁移文件中未找到对应 DDL",
            file=sys.stderr,
        )
        return False
    
    conn = sqlite3.connect(str(db_path))
    try:
        for stmt in create_stmts:
            conn.execute(stmt)
            print(
                f"[REPAIR] 已重建表: {stmt[:60]}...",
                file=sys.stderr,
            )
        conn.commit()
    finally:
        conn.close()
    
    print(
        f"[REPAIR] 检测到缺失表: {missing}，已从迁移 SQL 重建",
        file=sys.stderr,
    )
    return True


def _extract_create_tables(table_names: set[str]) -> list[str]:
    """从迁移文件中提取指定表的 CREATE TABLE 语句。"""
    stmts = []
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = f.read_text()
        for name in table_names:
            pattern = re.compile(
                rf'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{name}\s*\(.*?\);',
                re.DOTALL | re.IGNORECASE
            )
            m = pattern.search(sql)
            if m:
                stmts.append(m.group(0))
    return stmts
