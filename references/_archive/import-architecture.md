<!-- version: 2.8.0 | last-reviewed: 2026-05-26 -->

# 脚本导入架构：裸导入陷阱 + 修复模式 + 全量扫荡命令

## 问题

TrendRadar 脚本中曾广泛使用裸导入 `from settings import ...`、`from heat_tracker import ...` 等。
这在脚本直接运行时有效（`python scripts/xxx.py` — sys.path 自动加 scripts/ 目录），
但作为模块导入时（`python -c "import trendradar.scripts.xxx"`）会 `ModuleNotFoundError`。

## 修复：全限定导入

```python
# ❌ 裸导入
from settings import get_logger
from heat_tracker import make_fingerprint
from fetch_feeds import fetch_all
import heat_tracker as ht

# ✅ 全限定导入
from trendradar.scripts.settings import get_logger
from trendradar.scripts.heat_tracker import make_fingerprint
from trendradar.scripts.fetch_feeds import fetch_all
import trendradar.scripts.heat_tracker as ht
```

## 全量扫荡命令

```bash
# 检查残留裸导入
grep -rn "^from \(settings\|heat_tracker\|fetch_feeds\) \|^import \(heat_tracker\|fetch_feeds\)" \
  ~/.hermes/trendradar/scripts/*.py | grep -v "from trendradar" | grep -v __pycache__

# 验证所有模块可正常导入
cd ~/.hermes/trendradar
for mod in push_prepare batch_fetch ai_translate render_markdown fragment_push \
  curate_and_push track_events record_fingerprints heat_tracker fetch_feeds \
  push_slot_detect blog_watcher_bridge render_deep_analysis pipeline_orchestrator; do
  PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0 /usr/local/bin/python3.14t \
    -c "import trendradar.scripts.$mod" && echo "✅ $mod" || echo "❌ $mod"
done
```

## 修复历史

- 2026-05-24: 全量修复 15 个文件。14/14 导入测试通过。
- 涉及替换模式：`from settings import` × 12 文件、`from heat_tracker import` × 2、`from fetch_feeds import` × 1、`import heat_tracker as ht` × 3

## 预防

新脚本默认使用全限定导入。`pipeline_orchestrator.py` 全程使用 `from trendradar.scripts.xxx import` 作为参考实现。
