# 烟雾测试维护

`~/TrendRadar/hermes-scripts/trendradar_maintenance.py` 每日 03:00 运行 `pytest tests/`（`no_agent=true`）。

## 运行命令

```bash
cd ~/TrendRadar/trendradar && python -m pytest tests/ -v --tb=short
```

共 103 个测试（2026-05-26）。

## 常见失败模式

### 1. 代码重构后测试未同步更新

**症状**: `ImportError: cannot import name 'X' from 'Y'`

**根因**: 重构时删除了函数/类/变量，但测试仍引用旧 API。

**修复**: 重写测试覆盖当前实际存在的函数。常见重构方向：
- CJK 启发式 → `sources.json` language 字段（`_is_cjk`/`cjk_ratio`/`needs_translation` → `get_source_lang`/`get_system_prompt`）
- `DB_PATH` 模块变量 → `Storage` 类（monkeypatch 目标从 `rf.DB_PATH` 改为 `rf._store`）
- 返回值类型变更（tuple → dict，需改断言方式）

### 2. 模块缺少 import

**症状**: `NameError: name 'sqlite3' is not defined`

**根因**: 用了 `except sqlite3.OperationalError` 但未 `import sqlite3`。Python 在异常处理时才检查该名字。

**修复**: 文件顶部补上 `import sqlite3`。

### 3. 测试 mock 模式变更

当模块从简单变量切换到内部类实例时：
```python
# 旧模式（DB_PATH 是模块级变量）
monkeypatch.setattr(rf, 'DB_PATH', db_path)

# 新模式（_store 是 Storage 实例，需 mock .db() 方法）
from unittest.mock import MagicMock
mock_store = MagicMock()
mock_store.db.return_value = conn
monkeypatch.setattr(rf, '_store', mock_store)
```

### 4. 运行时路径 ≠ 仓库路径

**症状**: `_load_source_languages()` 返回空 frozenset，实际 `sources.json` 存在。

**根因**: 代码用 `Path(__file__).resolve().parent.parent / 'data'` 指向仓库路径，但运行时数据在 `~/.hermes/trendradar/data/`。始终用 `get_data_dir()` 获取运行时数据路径。

**修复**: `_SOURCES_PATH = DATA_DIR / 'sources.json'` 而非 `Path(__file__).resolve().parent.parent / 'data' / 'sources.json'`

### 5. ALTER TABLE 的 try/except 懒迁移反模式

**症状**: 每次 `record()` 都执行 `ALTER TABLE ADD COLUMN`，靠 `except sqlite3.OperationalError: pass` 吞掉"列已存在"错误。

**问题**:
- `OperationalError` 也匹配 DB 损坏/锁冲突/磁盘满等真错误，全部静默吞掉
- 每次推送都多一次无意义的 schema 变更尝试 + 异常捕获

**修复**: 用 `PRAGMA table_info` 先检查 schema，只在需要时才 ALTER：
```python
# Before — 盲试盲吞
try:
    conn.execute("ALTER TABLE fingerprints ADD COLUMN run_id TEXT DEFAULT ''")
except sqlite3.OperationalError:
    pass

# After — 先查后建
cols = {row[1] for row in conn.execute("PRAGMA table_info(fingerprints)")}
if 'run_id' not in cols:
    conn.execute("ALTER TABLE fingerprints ADD COLUMN run_id TEXT DEFAULT ''")
```

### 6. sanity_check 编排器前言剥离

`sanity_check.py` v3.x 新增 `strip_orchestrator_preamble()`：在禁语/格式检查前自动剥离编排器输出的状态行（push_id/deep_analysis/迁移错误等），避免编排器正常输出误触 `BANNED_PHRASES`。

匹配模式见 `ORCHESTRATOR_PREAMBLE_PATTERNS` 列表，按行正则匹配。

### 7. 翻译管线：标题未翻译但摘要已翻译

**症状**: 简报中外媒标题保持原文（English/Japanese），但摘要已正确翻译为中文。curated JSON 中 `title_cn == title`（原文复制），`summary_cn` 正确。

**根因**: DeepSeek API 在单 batch 超过 ~5 条时，模型会翻译摘要但标题输出原文不变。batch 越小成功率越高（5→100%，12→0%）。

**验证方法**: 查看 curated JSON 中 `title_cn` 是否等于 `title`（假翻译）还是真正的中文翻译。
```bash
cd ~/TrendRadar/trendradar && python3 -c "
import json, sys; sys.path.insert(0,'/home/asus/TrendRadar')
from trendradar.scripts.settings import get_data_dir
d=get_data_dir(); data=json.loads((d/'curated_morning_20260526.json').read_text())
for domain,items in data.items():
    if not isinstance(items,list): continue
    for item in items:
        tc=item.get('title_cn',''); t=item.get('title','')
        if tc and tc==t: print(f'FAKE: [{item.get(\"source_platform\",\"\")}] {t[:60]}')
"
```

**修复**: `ai_translate.py` `BATCH_SIZE = 5`（原值 20）。若换模型需重新验证最佳 batch 大小。

**注意**: 假翻译的 `title_cn` 会让后续 `ai_translate` 跳过（`has_title_cn and has_summary_cn → continue`）。需先清理假翻译字段再重跑：
```python
if item.get('title_cn') == item.get('title'):
    item.pop('title_cn', None)
```

## 工具限制（在 TrendRadar 仓库调试时）

- **`read_file`**: 可能返回空内容（0 total_lines），改用 `execute_code` + `subprocess.run(["head"...])`
- **`terminal`**: 可能返回空 stdout/stderr，改用 `execute_code` + `subprocess`
- **`execute_code` 沙箱**: 无法直接访问 `/home/asus/TrendRadar`，需用 `subprocess.run(..., cwd="/home/asus/TrendRadar/trendradar")`
- **`patch` 工具**: `old_string` 可能匹配失败，改用 `sed -i.bak`
