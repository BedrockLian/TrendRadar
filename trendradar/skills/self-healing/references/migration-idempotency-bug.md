# 迁移幂等性漏洞 (2026-05-24 评估发现)

## 问题

`migrations/runner.py` 的 `migrate()` 只执行 `ver > current` 的迁移。
当 `_migrations` 表记录 v1 已应用，但 `fingerprints` 表被外部删除（手动 DROP、并发异常），
迁移引擎跳过重建 → `auto_repair_missing_table()` 静默失败。

## 修复

新增 `repair_missing_tables()` 函数，绕过版本检查：
1. 从迁移 SQL 文件提取 `CREATE TABLE IF NOT EXISTS` 语句
2. 对缺失的表执行重建
3. 不影响已存在的表

```python
def repair_missing_tables(db_path: Path | str) -> bool:
    """重建被意外删除的表，绕过 _migrations 版本检查。"""
    conn = sqlite3.connect(str(db_path))
    existing = set(r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall())
    expected = {'fingerprints', 'heat_tracker', '_migrations'}
    missing = expected - existing
    if not missing:
        return False
    for ver, name, sql in _available_migrations():
        for stmt in _extract_create_tables(sql):
            conn.execute(stmt)
    return True
```

`trendradar_health_check.py` 的 `auto_repair_missing_table()` 已更新为先调用 `repair_missing_tables()` 再 `migrate()`。

## 检测

体检脚本 `check_db()` 检测到表缺失 → CRITICAL → `auto_repair_missing_table()` 自动修复。
