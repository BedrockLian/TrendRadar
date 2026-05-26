# 轻量级 SQLite 迁移回滚约定

## 问题

`migrations/runner.py` 原有 `migrate()` 只支持向前（up），不支持回滚（down）。
一旦迁移出错导致表结构损坏，唯一的恢复方式是手动 DROP 表 + 重新 migrate，丢失数据。

## 解决方案：`-- down:` 行内回滚注释

在 `.sql` 迁移文件末尾加一行 `-- down:` 注释，附带回滚 DDL：

```sql
-- 001_initial.sql
CREATE TABLE IF NOT EXISTS fingerprints (...);
CREATE TABLE IF NOT EXISTS heat_tracker (...);

-- down: DROP TABLE IF EXISTS heat_tracker; DROP TABLE IF EXISTS fingerprints;
```

### 约定

- **位置**：迁移文件最后一行（或倒数几行）
- **格式**：`-- down: <SQL语句>`
- **SQL 允许多语句**：分号分隔，由 `executescript()` 逐条执行
- **幂等**：使用 `IF EXISTS` / `IF NOT EXISTS`（与 up 迁移一致）

### runner.py 实现

```python
def _extract_down_sql(migration_sql: str) -> str | None:
    match = re.search(r'--\s*down:\s*(.+?)(?:\n--|$)', migration_sql, re.DOTALL)
    return match.group(1).strip() if match else None

def down(db_path, target_version=0) -> int:
    for ver, name, sql in reversed(_available_migrations()):
        if ver <= target_version:
            continue
        down_sql = _extract_down_sql(sql)
        if not down_sql:
            raise ValueError(f"迁移 {name} 缺少 -- down: 回滚 SQL")
        conn.executescript(down_sql)
        conn.execute("DELETE FROM _migrations WHERE version = ?", (ver,))
```

### 安全保证

- **缺注释 → 拒绝执行**：`ValueError` 而非静默跳过
- **逆序回滚**：从最新版本开始逐个向下
- **版本精准**：`target_version` 含 — 回滚到此版本（含）停止
- **非破坏性**：`_migrations` 表本身不被 down SQL 删除

## 添加新迁移

1. 创建 `migrations/NNN_description.sql`
2. 编写 CREATE/ALTER 等向上迁移 SQL
3. 在文件末尾添加 `-- down: <回滚SQL>`
4. 回滚 SQL 应撤销本迁移的所有结构变更

## 测试

`tests/test_pipeline_e2e.py::TestMigrationRollback` — 3 项：
- 完整 up → down 回滚循环
- 回滚到当前版本 = noop
- 缺 `-- down:` 注释的迁移拒绝回滚
