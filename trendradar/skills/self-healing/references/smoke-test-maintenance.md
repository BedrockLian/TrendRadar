# 烟雾测试维护

`~/.hermes/scripts/trendradar_maintenance.py` 每日 03:00 运行 `pytest tests/`（`no_agent=true`）。注意：仓库中 hermes-scripts/ 也有同名副本，两个位置需要同步。

## 运行命令

### 开发环境（仓库副本）
```bash
cd ~/TrendRadar/trendradar && PYTHONPATH=~/TrendRadar python -m pytest tests/ -v --tb=short
```

### 生产环境（Hermes 运行时）
```bash
cd ~/.hermes/trendradar && PYTHONPATH=~/.hermes/trendradar python -m pytest trendradar/tests/ -v --tb=short
```

注意：生产环境的测试文件在 `trendradar/trendradar/tests/`（嵌套包结构），而非 `trendradar/tests/`。

**PYTHONPATH 陷阱**：`~/.hermes/` 包含 `trendradar/__init__.py`，设 `PYTHONPATH=~/.hermes/` 会让 Python 在顶层就能找到 `trendradar` 包，与 conftest 的 sys.path 冲突导致 import 死锁（见 #8）。始终设到 `~/.hermes/trendradar/` 层级。

共 ~103 个测试（排除 `test_push_prepare` 和 `TestRecordFingerprints` 后 ~90 余通过）。

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

### 8. 测试套件完全挂起（import 死锁，零输出，超时）

**症状**: `pytest tests/` 从无输出，120s 后脚本超时。零行测试输出，只有 cron 报 "Script timed out after 120s"。

**根因**: 特定测试文件（`test_push_prepare.py`）在 import 阶段死锁。`push_prepare.py` 使用 `from trendradar.scripts.settings import ...` 导入，当 `PYTHONPATH` 包含 `/home/asus/.hermes/` 时：

1. Python 发现 `trendradar` 顶层级包（因为 `~/.hermes/trendradar/__init__.py` 存在）
2. 触发 `settings.py` → `common.py` → `storage.py` 等模块的模块级初始化
3. 与 conftest.py 的 `sys.path.insert(0, ...)` 形成 import 链死锁
4. pytest 进程无限阻塞，零输出

**排查方法**:
```bash
# 1. 检查何时开始死锁——逐测试文件运行
for tf in tests/test_*.py; do
  timeout 15 python -m pytest "$tf" -q --tb=line || echo "HANG: $tf"
done

# 2. 孤立隔离——用最小 timeout 跑疑似文件
timeout 10 python -m pytest tests/test_push_prepare.py -v

# 3. 确认是 import 级死锁（不是某个测试函数挂起）
timeout 10 python -c "from push_prepare import count_new_items"  # import 就挂
```

**修复**:
- **短期（维护脚本）**: 在 `pytest -k` 过滤器中排除该文件或类：`not push_prepare and not TestRecordFingerprints`
- **长期（根因）**: 设置子进程 `PYTHONPATH` 时指向项目目录本身（`~/.hermes/trendradar/`）而非父目录（`~/.hermes/`），避免 Python 在顶层包解析时发生冲突
- **嵌套包结构**: 若代码在 `trendradar/trendradar/` 深层结构下，`cwd` 和 `tests/` 路径都要指向内层包目录，同时 `PYTHONPATH` 设为外层 `~/.hermes/trendradar/`。维护脚本已自适应检测：
  ```python
  TR_PKG = TRENDRADAR_HOME / 'trendradar'
  cwd=str(TR_PKG if TR_PKG.exists() else TRENDRADAR_HOME)
  penv['PYTHONPATH'] = str(TRENDRADAR_HOME)
  ```

**预防**: 任何新增测试文件若从 `trendradar.scripts.*` 导入模块，需确保测试运行时不依赖 `~/.hermes/` 在 PYTHONPATH 中。conftest.py 应优先通过 `sys.path.insert` 而非 `PYTHONPATH` 环境变量来控制包解析。

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

### 9. 兴趣排除词滑窗误触 — 测试数据含通用词被 stopwords 遗漏

**症状**: `test_diversity_penalty_same_source` 失败，断言 `Expected at least 2 penalized items from same source, got 0`。
同一故障可导致 `test_respects_max_per_domain` 返回空结果（0 items）。

**根因**: `_load_interests()` 对 YAML 中的排除短语（如"游戏评测（除非是行业重大新闻）"）用滑窗提取所有 2-3 字中文子串。当 stopwords 未覆盖「新闻」「游戏」「体育」「行业」「重大」等通用词时，它们进入排除集 → 测试标题含「新闻」直接被 `score=0` 过滤 → 所有 items 被移除 → 多样性惩罚逻辑永远执行不到。

```
排除短语: "游戏评测（除非是行业重大新闻）"
    ↓ 滑窗提取 2-3 字子串
排除词: {'游戏', '评测', '除非', '非是', ... '新闻', '行业', '重大', ...}
    ↓ 测试标题含"新闻"
score=0, pass=False → items 被过滤 → diversity_penalty 无从触发
```

**修复**: 在 `_load_interests()` 的 stopwords 集合中添加 `'新闻', '游戏', '体育', '行业', '重大', '娱乐', '明星'` 等高频通用词。

**预防**: `config/ai_interests.yaml` 的 `negative` 列表每新增一条中文短语，需评估滑窗会抽出哪些通用词，确认已加入 stopwords。手动验证：
```python
from trendradar.scripts.curate_and_push import _load_interests
pos, neg = _load_interests()
# 检查 '新闻'、'游戏'等是否意外进入排除集
assert '新闻' not in neg, f'新闻意外在排除集中! {sorted(neg)[:30]}'
```

**副本同步陷阱**: `~/TrendRadar/trendradar/scripts/curate_and_push.py`（工作副本）和 `~/.hermes/trendradar/trendradar/scripts/curate_and_push.py`（运行时副本）是两份独立文件。只修工作副本推 GitHub ≠ cron 下次运行修复。必须同步到运行时副本。

## 工具限制（在 TrendRadar 仓库调试时）

- **`read_file`**: 可能返回空内容（0 total_lines），改用 `execute_code` + `subprocess.run(["head"...])`
- **`terminal`**: 可能返回空 stdout/stderr，改用 `execute_code` + `subprocess`
- **`execute_code` 沙箱**: 无法直接访问 `/home/asus/TrendRadar`，需用 `subprocess.run(..., cwd="/home/asus/TrendRadar/trendradar")`
- **`patch` 工具**: `old_string` 可能匹配失败，改用 `sed -i.bak`
