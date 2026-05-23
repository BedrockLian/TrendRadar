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
