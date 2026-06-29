# TrendRadar 审计修复工作流

## 场景
拿到审计报告（AUDIT-REPORT.md 或其他审计产出的 Top N 行动项），用户说"全修"。

## 工作流

1. **读审计报告** — 提取 Top N 行动项，逐条确认文件路径和改动
2. **读源码** — read_file 每个要改的文件，理解上下文再做 patch
3. **改代码** — 按优先级从高到低，每条改动独立核实
4. **验证 import** — 所有改完后再验证模块可导入
   ```bash
   cd ~/.hermes/trendradar
   export PYTHON=/usr/local/bin/python3.14t PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0
   for mod in push_prepare batch_fetch ...; do
     $PYTHON -c "import trendradar.scripts.$mod" && echo "✅ $mod" || echo "❌ $mod"
   done
   ```
5. **跑测试** — 跑相关 pytest 确认没 break
6. **同步双副本** — 工作副本 `~/TrendRadar/` → cron 运行时 `~/.hermes/trendradar/`
   ```bash
   cp trendradar/scripts/xxx.py ~/.hermes/trendradar/trendradar/scripts/xxx.py
   ```
7. **提交并推送 GitHub**

## 常见修复类型

| 类型 | 模式 | 例子 |
|------|------|------|
| 裸 import | `import xxx` → `from trendradar.scripts import xxx` | `pipeline_orchestrator.py:289` |
| 硬编码路径 | `/home/asus/...` → 环境变量或 `__file__` 推导 | `diag_pipeline.sh`、测试文件 |
| 异常吞噬 | `except: pass` → 加 `log.warning` 或缩小异常范围 | 12 处一次性修复 |
| 缺超时 | 无 `ClientTimeout` → 加 `timeout=ClientTimeout(total=30)` | `fetch_feeds.py` Session |
| 循环导入 | A↔B 互相 import → 第三方模块解耦 | `storage↔settings` → `file_utils` |

## 第二轮审计（Reference 专项）

大修完成后应跑一次 reference 专项审计（如 `SKILL-REFERENCES-AUDIT.md`），它会发现第一轮遗漏的：

- 仍存在于 skill references 中的内容副本（已被顶层 references 覆盖）
- 已删除文件留下的死链引用（如 `pipeline.md`/`render-format.md` 被删后 skills 仍引用）
- 过时的合并来源声明（`合并自: ...` 注释行、HTML 注释的 `Consolidated from ...`）
- 旧版本号残留

**执行模式**：读审计报告 → 4 阶段执行（新增 TRAPS 条目 → 删冗余文件 → 修死链 → 清旧声明），每阶段完成后同步工作树 ↔ cron 副本。

## 修复后验证清单

1. `PYTHONPATH=$PWD python3 -c "import trendradar.scripts; print('import OK')"` — 包导入正常
2. `python3 -m pytest tests/ -x -q` — 测试全绿
3. `TRENDRADAR_HOME=... python3 ~/.hermes/scripts/trendradar_health_check.py` — 无假阳性
4. `git status --short` — 确认工作树改动与预期一致
5. `diff <(ls ~/.hermes/skills/trendradar/) <(ls trendradar/skills/)` — 技能两端一致

## 用户偏好：代码精简原则（" 一切从简"）

用户原话：**"把不需要用的脚本或者脚本内不需要的遗留删了，或者你看看有没有可以合并的，一切从简。"**

执行清理/审计/重构类任务时，主动应用以下原则：

1. **孤儿脚本** — 0 外部引用的脚本（无代码/cron prompt/测试/skill 引用）**直接删除**。但要区分：
   - **删**：`validate_output.py`（154 行）、`pipeline_stage.py`（16 行） — 完全无引用
   - **保留**：`cleanup_fake_translations.py`（45 行）、`interest_cli.py`（109 行）— 0 引用但是**手动运维工具**（前者用于清 `[扩写失败]` 数据，后者 SKILL.md 文档化过），保留
   - **保留**：`blog_watcher_bridge.py`、`render_deep_analysis.py` — 被 `push_prepare.py` / `gen_cron_prompt.py` 引用，grep 漏查（`grep -rln "blog_watcher_bridge" trendradar/` 单独跑才能找到）

2. **脚本内遗留** — `__all__` 里列了但 0 引用的 export、`PipelineItem` 之类空 TypedDict、注释掉的功能、未使用的环境变量常量、赋了值但未读过的变量、声明了从未在 final response 输出的"未来会用的"占位逻辑

3. **不要重构中的副作用** — 删除模块时**先 grep 0 引用**（不能只看 `grep -l`），同时检查 cron prompt、tests、references 目录。`validate_output.py` 被 grep 显示 0 引用但实际只在 `~/.hermes/cron/output/...md` 历史归档里出现名字——那种是死链无关项。

4. **可合并模块** — 16 行的 `pipeline_stage.py` 只定义了一个 Protocol，0 导入 → 与 `pipeline_orchestrator.py` 的 `run_stage()` 函数重复 → **删**。但**短 ≠ 该删**（如 9 行的 `config/delivery.py` 常量模块是 SSOT，保留）。

5. **测试 vs 数据的边界** — 测试失败若**纯数据相关**（如 `get_source_lang('NHK')` 因 sources.json 里没 NHK 而失败），加 `pytest.skip` 条件，**不要**改生产代码。

6. **测试 mock 层必须跟随重构** — LLM provider 解耦时 7 个老测试挂了，因为它们 mock `session.post`（旧 HTTP 层）但新代码走 `LLMProvider.chat`（新抽象层）。新测试改 mock `ai_translate._make_request` 或 `llm_providers.LLMProvider.chat`。

7. **量化指标** — 一次"一切从简"清理：scripts/ 35 文件，~7046 行；git diff 净减 194 行（删除 2 个死模块 + 移除 1 个空 Protocol + 移除未使用变量 + 简化 `parse_run_id` + 整理 import 顺序）；测试 0 regression。

## Python 陷阱：import 在 shebang 之前

**问题模式** — 部分 TrendRadar 脚本历史遗留 bug：
```python
from trendradar.scripts.common import CST
#!/usr/bin/env python3
"""docstring"""
```

**症状**：
- Python 解析器**容错**（运行不报 SyntaxError），但语义混乱
- 阅读时 import 像是"神秘的预处理器"
- LSP/编辑器（Pyright）会报 import could not be resolved（因为它把第一行视为脚本体之外的不可解析内容）
- 部分 lint 工具会报"未在文档开头"

**修复**（已在 `pipeline_orchestrator.py`、`heat_tracker.py` 等多处执行）：
```python
#!/usr/bin/env python3
"""docstring"""
import ...

from trendradar.scripts.common import CST  # ← import 跟在所有模块级代码之后
```

**审计命令**：
```bash
for f in ~/.hermes/trendradar/trendradar/scripts/*.py; do
  if head -1 "$f" | grep -q '^from\|^import'; then
    head -1 "$f" | head -c 60
    echo "  ← import before shebang: $f"
  fi
done
```

任何匹配都应 patch 成 shebang → docstring → import 顺序。
