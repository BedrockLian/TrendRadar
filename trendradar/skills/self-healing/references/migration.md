# 数据库迁移机制

## 架构

`trendradar/migrations/` 目录管理 SQLite schema 版本：

```
migrations/
├── __init__.py
├── runner.py        # 迁移引擎（~50 行 SQLite 引擎）
└── 001_initial.sql  # fingerprints + heat_tracker + 5 索引
```

## 替换的代码

迁移引擎统一替代了 2 处散落的 CREATE TABLE：

| 原位置 | 替代方式 |
|--------|---------|
| `heat_tracker.py:init_db()` | 改为调用 `settings.ensure_db_migrated(DB_PATH)` |
| `health_check.py:auto_repair_missing_table()` | 改为调用 `migrations.runner.migrate(db)` |

## 工作原理

1. `_migrations` 表记录已应用版本
2. 启动时遍历 `migrations/*.sql`，按文件名前缀版本号排序
3. 仅应用版本号 > 当前版本的 SQL 文件
4. 幂等：已应用的迁移不重复执行

## 新增迁移

新建 `migrations/002_xxx.sql`，内容为新字段/索引的 DDL：

```sql
-- 002_add_emotion.sql
ALTER TABLE heat_tracker ADD COLUMN emotion_score REAL DEFAULT 0.0;
ALTER TABLE heat_tracker ADD COLUMN emotion_label TEXT DEFAULT '';
```

自动被 runner 检测并执行，无需修改业务代码。

## 验证

```bash
cd ~/.hermes/trendradar
PYTHONPATH=/home/asus/.hermes python3 -c "
from scripts.settings import ensure_db_migrated
ver = ensure_db_migrated()
print(f'Schema version: v{ver}')
"
```

## 轻量级 SQLite 迁移回滚约定

### 问题

`migrations/runner.py` 原有 `migrate()` 只支持向前（up），不支持回滚（down）。
一旦迁移出错导致表结构损坏，唯一的恢复方式是手动 DROP 表 + 重新 migrate，丢失数据。

### 解决方案：`-- down:` 行内回滚注释

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

### 添加新迁移

1. 创建 `migrations/NNN_description.sql`
2. 编写 CREATE/ALTER 等向上迁移 SQL
3. 在文件末尾添加 `-- down: <回滚SQL>`
4. 回滚 SQL 应撤销本迁移的所有结构变更

### 测试

`tests/test_pipeline_e2e.py::TestMigrationRollback` — 3 项：
- 完整 up → down 回滚循环
- 回滚到当前版本 = noop
- 缺 `-- down:` 注释的迁移拒绝回滚

## 迁移幂等性漏洞 (2026-05-24 评估发现)

### 问题

`migrations/runner.py` 的 `migrate()` 只执行 `ver > current` 的迁移。
当 `_migrations` 表记录 v1 已应用，但 `fingerprints` 表被外部删除（手动 DROP、并发异常），
迁移引擎跳过重建 → `auto_repair_missing_table()` 静默失败。

### 修复

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

### 检测

体检脚本 `check_db()` 检测到表缺失 → CRITICAL → `auto_repair_missing_table()` 自动修复。
