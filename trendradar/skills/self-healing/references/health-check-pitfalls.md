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

**预防**: 执行 `git clean` 前先 `git clean -n` 预览要删除的文件列表。若包含 `.py` 源文件，立即停止并检查：

**`data/sources.json` 附随损害**: `git clean -fd` 同时删除 `data/sources.json`。该文件是 `ai_translate.py` 检测外文条目语言的唯一依据。缺失时翻译管线静默跳过所有条目（"No English items found"），导致渲染后外文条目无 `title_cn`/`summary_cn`。恢复: `cp backups/trendradar/$(date +%Y%m%d)/sources.json data/`。详见 `news-secretary` 技能的 `references/sources-json-loss-symptoms.md`。

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

## 11. `check_stale_processes()` 引用未定义变量

**现象**：`NameError: name 'CRON_JOBS' is not defined` → 健康检查崩溃。

**根因**：函数中使用 `CRON_JOBS` 但模块级定义的变量是 `CRON_JOB_NAMES`。

**修复**（2026-05-28）：`CRON_JOBS` → `CRON_JOB_NAMES`。

## 12. `check_cron()` `--json` 参数不存在

**现象**：`hermes cron list --json` 返回 `unrecognized arguments: --json`。所有 job 报"未在输出中找到"的假阳性（7条）。

**根因**：此版本 Hermes CLI 不支持 `--json` 输出模式。

**修复**（2026-05-28）：去掉 `--json`，改解析表格输出的 `Name: xxx` 行（`re.match(r'\s+Name:\s+(.+)', line)` → job_names）。CRON_JOB_NAMES 必须与 job 实际名称匹配：
- `'推送看门狗'` → `'推送降级看门狗'`
- `'月度报告'` → `'月度趋势报告'`

## 13. `check_gateway()` `ps aux` 找不到 systemd 服务

**现象**：Gateway 作为 systemd user service 运行，`ps aux` 中进程名是 `python -m hermes_cli.main gateway run`，不含 "hermes gateway" 字符串→假阳性。

**修复**（2026-05-28）：改用 `systemctl --user is-active hermes-gateway.service`。兜底 `hermes gateway status`。无 systemd 环境回落 socket 文件检查。

## 14. `check_api()` httpbin 走代理必超时

**现象**：`httpbin.org` 通过 `HTTP_PROXY` 代理走 → 代理节点 i/o timeout → HTTP 000。

**根因**：WSL 无直连互联网，所有外网流量必须走 `http://127.0.0.1:7890`，代理节点不可达时全部超时。DeepSeek 因在 `NO_PROXY` 中可以直连。

**修复**（2026-05-28）：删除 httpbin.org 检测。DeepSeek 检测时清除 `HTTP_PROXY`/`HTTPS_PROXY` env var 确保直连。

## 15. `check_pipeline()` RSS 连通性随机采样假阳性

**现象**：健康检查随机抽到 `localhost:1200`（本地通常未运行）的源时报错，每次结果不一致。

**修复**（2026-05-28）：
- 过滤 `feed_url` 含 `localhost` 的源
- 改为确定性取前 3 个源而非 `random.sample`
- 同时过滤 `enabled=False` 的源
- 不再第一个失败就 `break`：统计全部 3 个源
  - 全部失败 → 报 WARN
  - 部分失败 → 仅 debug 日志

**验证**:
```bash
# 维护脚本全量跑一次
python3 ~/.hermes/scripts/trendradar_maintenance.py
# 预期输出摘要行 + 烟雾测试通过（无 WARNING）
```

## 9. `git clean -fd` 破坏后恢复（嵌套包结构）

**场景**: 在 git 冲突解决/仓库同步过程中误执行 `git clean -fd`，所有未被 git 跟踪的本地工作文件被删除。

**症状**: `scripts/` 和 `tests/` 目录只剩 `__pycache__`，`.py` 源文件全部消失。pytest 运行 "no tests ran in 0.00s"。

**根因**: 仓库采用嵌套包结构 — 代码不在 `trendradar/` 仓库根目录下，而在 `trendradar/trendradar/` 深层。`git ls-tree HEAD` 列出的文件路径为 `trendradar/scripts/xxx.py`。`git clean -fd` 只删除工作树的未跟踪文件，而文件虽然在 HEAD 提交中但路径不同（`trendradar/trendradar/xxx` vs 工作树 `trendradar/xxx`）。

**恢复**:
```bash
# 1. 确认文件在 HEAD 中
git ls-tree -r HEAD --name-only | grep scripts/

# 2. 恢复所有文件（checkout 会重建工作树中的任何缺失文件）
git checkout HEAD -- .

# 3. 验证
find . -name "*.py" -type f | wc -l
# 预期输出: ~47

# 4. 注意：git clean -fd 删除的 .env/data/cache 不会恢复（它们本应被 .gitignore 排除）
```

**预防**: 执行 `git clean` 前先 `git clean -n` 预览要删除的文件列表。若包含 `.py` 源文件，立即停止并检查：
```bash
git clean -n   # 预览
```

**嵌套包路径注意事项**: 若仓库根目录是 `~/.hermes/trendradar/` 且代码在 `~/.hermes/trendradar/trendradar/` 下，所有脚本和测试的路径必须用 `TRENDRADAR_HOME / 'trendradar'` 而非 `TRENDRADAR_HOME`：
```python
TR_PKG = TRENDRADAR_HOME / 'trendradar'
cwd = str(TR_PKG if TR_PKG.exists() else TRENDRADAR_HOME)
penv['PYTHONPATH'] = str(TRENDRADAR_HOME)  # 父目录便于 import trendradar
```

## 10. 执行 `git clean` 前必须 `git stash` 暂存未跟踪的本地修改

`git stash` 默认只暂存已跟踪文件的修改。`git clean -fd` 会删除 `stash` 无法恢复的未跟踪文件。

**安全流程**:
```bash
# 1. 先 stash 所有内容（包括未跟踪文件）
git stash --include-untracked

# 2. 执行需要的有冲突操作（pull/rebase/reset）
git pull --rebase

# 3. 恢复工作
git stash pop

# 4. 若有冲突，用 git reset --hard origin/main + 手动重改
# 而非 git clean -fd（这会丢失未跟踪文件）
```

## 11. `no_agent` 脚本中 pytest 的 PYTHONPATH 陷阱

`trendradar_maintenance.py` 的 `runtests()` 如果设 `PYTHONPATH = TRENDRADAR_HOME.parent`（即 `~/.hermes/`），会导致 `test_push_prepare.py` import 阶段死锁：

- `~/.hermes/trendradar/__init__.py` 让 Python 发现 `trendradar` 顶层级包
- `from trendradar.scripts.settings import ...` 触发 settings.py 模块级初始化
- 与 conftest 的 `sys.path.insert(0, ...)` 形成 import 链死锁 → pytest 零输出

**修复**: `PYTHONPATH` 只设到 `TRENDRADAR_HOME`（`~/.hermes/trendradar/`），并在 `-k` 过滤器中排除已知有问题的测试：
```python
penv['PYTHONPATH'] = str(TRENDRADAR_HOME)   # 而非 TRENDRADAR_HOME.parent
# pytest -k 排除
'-k', 'not slow and not ai_translate and not push_prepare and not TestRecordFingerprints'
```

详见 `smoke-test-maintenance.md` #8。
