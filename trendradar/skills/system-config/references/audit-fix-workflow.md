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
   for mod in push_prepare ai_translate ...; do
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
