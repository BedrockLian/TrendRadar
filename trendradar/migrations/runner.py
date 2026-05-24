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
        # 提取完整的 CREATE TABLE 语句（处理多行）
        import re as _re
        for name in table_names:
            pattern = _re.compile(
                rf'CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+{name}\s*\(.*?\);',
                _re.DOTALL | _re.IGNORECASE
            )
            m = pattern.search(sql)
            if m:
                stmts.append(m.group(0))
    return stmts
