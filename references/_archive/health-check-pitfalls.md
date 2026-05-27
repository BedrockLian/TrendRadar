# 健康检查脚本维护陷阱

> 修复于 2026-05-24。以下陷阱在技能重组/脚本重命名后容易出现。

## 1. SKILL_DIR 路径过时 [已修复 — 已从脚本中删除该变量]

技能目录从 `skills/productivity/trendradar-news-secretary` 迁移到 `skills/trendradar/news-secretary` 后，`trendradar_health_check.py` 中的 `SKILL_DIR` 默认值未同步更新。
**修复**: 脚本中从未使用该变量，2026-05-24 更新中已完全移除。无需再检查此项。

## 2. 导入检查使用旧式裸导入
健康检查的 `check_pipeline()` 用 `sys.path.insert(0, SCRIPTS); import mod_name` 做导入验证。导入架构改为全限定后（`from trendradar.scripts.xxx import`），旧式检查会误报。
**修复**: 改为 `python -c "import trendradar.scripts.{mod_name}"` + 设置 `PYTHONPATH`。
```python
env = os.environ.copy()
env['PYTHONPATH'] = str(TR.parent)
subprocess.run([sys.executable, '-c', f'import trendradar.scripts.{mod_name}'], env=env)
```

## 3. 新增脚本未加入检查列表
`check_scripts()` 和 `check_pipeline()` 的脚本列表需与新 pipeline 同步。添加新脚本后（如 `pipeline_orchestrator.py`），必须更新两处列表。
**检查**: 对比两个列表与实际文件：
```bash
grep "required = \[" ~/.hermes/scripts/trendradar_health_check.py -A10
grep "pipeline_steps = \[" ~/.hermes/scripts/trendradar_health_check.py -A5
ls ~/.hermes/trendradar/scripts/*.py | xargs -n1 basename | sort
```

## 4. 未导入模块致静默 NameError
`check_gateway()` 在异常路径用 `logging.debug()` 但未 `import logging`。错误路径极少触发，导致 NameError 被静默吞掉。
**预防**: 全局 grep 脚本中所有 `logging.` 调用，确认顶部已导入。
```bash
grep -n "logging\." ~/.hermes/scripts/trendradar_health_check.py
head -5 ~/.hermes/scripts/trendradar_health_check.py | grep "import logging"
```

## 5. 子进程调用解释器不匹配 — 导入检查误报 feedparser/ModuleNotFoundError

健康检查用 `sys.executable`（系统 python3）跑子进程导入检查 → `feedparser`/`zstandard` 只装在 python3.14t 上 → 导入测试一直报错。
同样的 `push_slot_detect` 也可能因缺少 PYTHONPATH 导致 exit=1（与 timeline.yaml 缺失症状相同，难以区分）。

**修复**: 健康检查脚本中用管线 Python 跑所有子进程：

```python
pipeline_python = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')
if not os.access(pipeline_python, os.X_OK):
    pipeline_python = sys.executable  # fallback
penv = os.environ.copy()
penv['PYTHONPATH'] = str(TR.parent)     # /home/asus/.hermes
penv.setdefault('PYTHON_GIL', '0')
subprocess.run([pipeline_python, ...], env=penv)
```

所有子进程调用（push_slot_detect、import check 等）必须统一使用该逻辑。

**验证**: 健康检查全量跑一遍，确认 `pipeline` 相关的 WARN 消失：
```bash
cd ~/.hermes && python3 scripts/trendradar_health_check.py | grep -c pipeline
# 期望输出 0
```

## 6. keywords.py 检查阈值不匹配 frozenset 结构

`check_config()` 用 `':' in l` 统计关键词定义行 → `frozenset(...)` / `GAME_KW = {...}` / `KEYWORDS = dict(...)` 等 Python 集合结构不包含冒号，计数严重偏小（182行文件只检出10行）。

**修复**: 改用文件大小阈值（>1000B）+ 检查 `has_keyword_match_ci` 函数存在 + 确认至少有2个集合定义（`= frozenset` 或 `= {`）。

## 7. Cron job ID 硬编码 — 重装后失步

`check_cron()` 在脚本中硬编码 7 个 job ID。重装 cron 后 ID 全部变更，但脚本不会自动更新。

**修复**: 重装 cron 后必须同步更新 `CRON_JOBS` 字典中的 ID。

```bash
# 获取新 ID
hermes cron list
# 然后编辑 ~/.hermes/scripts/trendradar_health_check.py 中的 CRON_JOBS
```

## 8. 维护脚本 `runtests()` 解释器不匹配 + 缺乏 PYTHONPATH + 失败不 exit(1)

`trendradar_maintenance.py` 的 `runtests()` 长期使用系统 `python3`（而非管线 python3.14t），且未设置 `PYTHONPATH`。虽因 cwd 下存在 `__init__.py` 使当前导入结构能工作，但：
  - 与健康检查约定不一致（健康检查所有子进程统一走 `$PYTHON` / python3.14t）
  - 若将来 `TRENDRADAR_HOME` 不再作为包根目录（如改用 `pip install -e`），测试会静默失败

**另外两个问题**：
  - 烟雾测试失败仅 `print(stderr)` → no_agent 模式不检查 stderr，报警被吞
  - 备份列表中有 `push_log.json` 和 `preferences.json` 两个已不存在的文件（仅靠 `src.exists()` 静默跳过，为死代码）

**修复（2026-05-24 完成）**:

```python
# runtests() 改用管线 Python + PYTHONPATH
pipeline_python = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')
if not os.access(pipeline_python, os.X_OK):
    pipeline_python = sys.executable
penv = os.environ.copy()
penv['PYTHONPATH'] = str(TRENDRADAR_HOME.parent)
result = subprocess.run(
    [pipeline_python, '-m', 'pytest', 'tests/', ...],
    cwd=str(TRENDRADAR_HOME), env=penv,
)

# 失败时 exit(1) 确保 no_agent 推送
if not runtests():
    print('[WARNING] 烟雾测试未通过，但备份和清理已完成')
    sys.exit(1)
```

**教训**: 修复一类脚本的解释器问题时，必须平行检查同项目的所有 C 级脚本（所有 no_agent cron 脚本）。2026-05-24 之前只有健康检查修复了解释器，maintenance 脚本遗漏了。

**验证**:
```bash
# 维护脚本全量跑一次
python3 ~/.hermes/scripts/trendradar_maintenance.py
# 预期输出摘要行 + 烟雾测试通过（无 WARNING）
```
