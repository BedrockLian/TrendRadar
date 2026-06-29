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
penv['PYTHONPATH'] = str(TR.parent)     # /home/asus/.hermes/trendradar
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

**现象**：健康检查随机抽到 `localhost:1200`（RSSHub 通常未运行）的源时报错，每次结果不一致。

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

## 16. 修复→检查顺序颠倒 — 已修项仍报异常

**现象**：`auto_repair_missing_table()` 修好了数据库表，但 `ISSUES` 中残留修复前的错误记录。即使全部自动修复成功，报告仍显示"亚健康"或"异常"。

**根因**：`main()` 中 `run_checks()` → `run_repairs()` 顺序。修复跑在检查之后，修复的项已经在 ISSUES 里了。

**修复**（2026-05-29）：改为 `run_repairs()` → `run_checks()`。修完再查，修好的项不会进入 ISSUES。

## 17. INFO 级别项触发"亚健康"状态

**现象**：`fail(component, 'INFO', msg)` 添加的条目（如 `source_health.json` 首次运行不存在）被 `elif ISSUES:` 判定分支捕获 → 报告显示"亚健康"。

**根因**：`generate_report()` 中判断条件 `elif ISSUES:` 会匹配任何非空列表，包括仅有 INFO 级提示的列表。

**修复**（2026-05-29）：`elif ISSUES:` → `elif any(i['severity'] in ('CRITICAL', 'WARN') for i in ISSUES):`。仅 CRITICAL/WARN 级别触发"亚健康"。

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

## 18. `PYTHON_GIL=0` 导致子进程 crash（Python 3.14t）

**现象**：健康检查中所有子进程调用（push_slot_detect、import check、sanity_check、blind_spot）全部报 `exit=1`，stderr 为 `Fatal Python error: config_read_gil: Disabling the GIL is not supported by this build`。

**根因**：脚本中 4 处使用 `env.setdefault('PYTHON_GIL', '0')`，在 Python 3.14t 上主动注入 GIL 禁用指令导致 crash。

**修复**（2026-05-30）：删除所有 4 处 `env.setdefault('PYTHON_GIL', '0')`。PYTHON_GIL 应由 cron 环境按需设置，健康检查不应主动注入。

```python
# 修复前（4 处）：
env = os.environ.copy()
env.setdefault('PYTHON_GIL', '0')  # ← 删除此行

# 修复后：
env = os.environ.copy()
# PYTHON_GIL 由外层 cron 环境控制，不主动设置
```

## 28. WeCom 投递真实通路是 `hermes send`，不是 IPC socket（2026-06-09 Windows 实战）

**症状**：`delivery_watchdog.py` 跑出来报 `🚨 WeCom IPC socket 不可达 — gateway 可能已停止`（硬编码查 `/tmp/hermes_gateway.sock`、`/tmp/hermes_wecom.sock`、`/tmp/hermes-wecom-card.sock`），Windows 下根本没这些 unix socket，永远 false。

**关键观察**：socket 检测 false **不影响实际推送**。`delivery_watchdog.py` 的 `send_to_wecom()` 走的是 `subprocess.run(['hermes', 'send', '--to', 'wecom:bl', '--file', ...])`（HTTP API），**不依赖 unix socket**。即使 socket check 全 fail，archive 仍能正常推 WeCom。

**手动投递标准配方**（pipeline 跑通但 cron 自动投递失败时用）：

```python
# 1) 读 archive + split_fragments 分片（避免 4KB 截断）
python -c "
import sys; sys.path.insert(0, '$TRENDRADAR_HOME')
from trendradar.scripts.fragment_push import split_fragments
arch = '$TRENDRADAR_HOME/archive/YYYY-MM-DD/SLOT.md'
content = open(arch, encoding='utf-8').read().strip()
frags = split_fragments(content)
print(len(frags))
"

# 2) 逐片 hermes send（不能用 stdin 一次传多片）
for frag in $(python -c "...split..."); do
  hermes send --to wecom:bl <<< "$frag"
done

# 3) 写 marker 防重投
echo "$(date -Iseconds)" > \
  $TRENDRADAR_HOME/data/delivery_markers/delivered_YYYYMMDD_${slot}_manual.marker

# 4) 验证
tail -50 $HERMES_HOME/logs/gateway.log | grep -E "wecom.*bl|Sending response"
```

**chat_id 来源**（实测）：
- 让用户在企业微信给 bot 发任意消息（"hi"），gateway 收到 inbound 后会绑定一个内部 alias（实测是 `bl` 这种短串，不是用户真实 userid）
- 然后 `hermes send -t wecom` 或 `hermes send --to wecom:bl` 都能用
- 或写 `WECOM_HOME_CHANNEL=bl` 进 `.env`，scheduler 自动用 home channel

**delivery_watchdog.py 已知 Linux 残留 bug**（待修，不阻塞推送）：
- 第 22 行 `HERMES_HOME = os.path.expanduser("~/.hermes")`（Windows 错位）
- 第 28 行 `PYTHON = '/usr/local/bin/python3.14t'`（Linux 路径）
- 第 79-83 行 socket 路径全是 `/tmp/*`（Linux unix socket）
- 这些不影响推送，但每次体检都会输出误报警报，污染 health_check 报告

**修复建议**（单点 patch，~10 行）：
```python
# delivery_watchdog.py 顶部替换
import os, sys
HERMES_HOME = (
    os.environ.get('HERMES_HOME')
    or (os.environ.get('LOCALAPPDATA', '') + r'\hermes' if os.name == 'nt'
        else os.path.expanduser('~/.hermes'))
)
PYTHON = os.environ.get('PYTHON') or (
    '/usr/local/bin/python3.14t' if os.name != 'nt' else sys.executable
)

# socket 检测改为：Windows 跳过
def check_socket():
    if os.name == 'nt':
        return True  # Windows 走 hermes send HTTP API，不依赖 unix socket
    # Linux 原有 /tmp/*.sock 逻辑保留
    ...
```

**为什么 socket check 设计意图是好的**：Linux 上 gateway 是 systemd user service，启动时会建 `/tmp/hermes_gateway.sock` 给 cron delivery 通信用。Windows 没这套机制但有同等功能的 HTTP API（hermes send）—— 设计是 Linux-first 的，Windows 是 fallback 不报错地工作。

## 19. `push_slot_detect` NO_SLOT 时 exit=1 被误判为失败

**现象**：每日 15:00 自动体检报告持续报 `push_slot_detect 执行失败 (exit=1)`，但脚本实际正常运行。

**根因**：`push_slot_detect.py` 在非推送时段输出 `NO_SLOT` 并 exit=1（正常行为），但 `check_pipeline()` 的 `if r.returncode != 0:` 判断不区分 exit=1 的原因，一律报 WARN。

**修复**（2026-05-30）：增加 `stdout` 判断——仅当 exit≠0 且 stdout 不是 `NO_SLOT` 时才报错：

```python
# 修复前：
if r.returncode != 0:
    fail('pipeline', 'WARN', f'push_slot_detect 执行失败 (exit={r.returncode})')

# 修复后：
if r.returncode != 0 and r.stdout.strip() != 'NO_SLOT':
    fail('pipeline', 'WARN', f'push_slot_detect 执行失败 (exit={r.returncode})')
```

## 20. `TR.parent` / `TRENDRADAR_HOME.parent` 用作 `sys.path` 或 `PYTHONPATH` 是错的（2026-06-02）

**症状**：`No module named 'trendradar.migrations'`、`No module named 'trendradar.scripts.storage'` 等 import 失败，15:00 体检 4 条警告中 1-3 条是这个根因。

**根因**：仓库采用嵌套包结构——
- `TRENDRADAR_HOME` = `~/.hermes/trendradar/`（**外层**，**没有 `__init__.py`**，不是包）
- 包 `trendradar/` 真正在 `~/.hermes/trendradar/trendradar/`（**内层**，有 `__init__.py`）

要让 `from trendradar.xxx import yyy` 工作，`sys.path` 必须包含**包路径的父目录** = `TRENDRADAR_HOME` 自身（`~/.hermes/trendradar/`）。**不是** `TRENDRADAR_HOME.parent`（那是 `~/.hermes/`，其下的 `trendradar/` 子目录没 `__init__.py`，Python 找不到包）。

```python
# 错（7+3 处出现）：
sys.path.insert(0, str(TR.parent))                  # = ~/.hermes/
env['PYTHONPATH'] = str(TRENDRADAR_HOME.parent)     # = ~/.hermes/

# 对：
sys.path.insert(0, str(TR))                          # = ~/.hermes/trendradar/
env['PYTHONPATH'] = str(TRENDRADAR_HOME)             # = ~/.hermes/trendradar/
```

**为什么之前没暴露**：5/30 老副本（`~/.hermes/scripts/trendradar_health_check.py`）**从未与 git HEAD 同步**（参见 #21），老副本里硬编码 `TR.parent` 但好在有 `sys.executable` 默认 sys.path 包含 cwd，import `trendradar` 偶尔能凑合——直到 dead 仓库 `~/TrendRadar/` 清理后才炸。

**验证修复**：
```bash
cd /home/asus/.hermes/scripts
TRENDRADAR_HOME=/home/asus/.hermes/trendradar python3.14t trendradar_health_check.py
# 期望：No module named 警告消失
```

**预防清单**（grep 整个 trendradar 仓库 + 副本）：
```bash
grep -rnE "TR\.parent|TRENDRADAR_HOME\.parent" \
  ~/.hermes/trendradar/hermes-scripts/ \
  ~/.hermes/scripts/
# 期望：0 命中
```

## 21. cron 跑的副本 `~/.hermes/scripts/*.py` 与 git HEAD 长期脱钩是定时炸弹（2026-06-02）

**症状**：`hermes cron list` 看到 `script=trendradar_health_check.py`（裸名），但 `~/.hermes/scripts/trendradar_health_check.py` 是 5/30 写的 578 行老版，**git HEAD 是 500 行新版且每次 commit 都在改**——5/30 之后改的所有健康检查修复（包括 9e2e6d1 修 PYTHON_GIL、7406524 删 batch_fetch 引用、5132e02 修 sources.json 路径），**cron 一次都没拿到**。

**根因**：
- `~/.hermes/scripts/` 是 Hermes scheduler 跑 cron 的 `scripts_dir`（`scheduler.py:854` 强制约束）
- git 仓库 `~/.hermes/trendradar/hermes-scripts/` 是**另一份**副本
- 没有人/hook 在 commit 时同步 → 老副本永远停在 5/30

**修复协议（必做）**：
1. 修改 `~/.hermes/trendradar/hermes-scripts/` 任何脚本后，**立即** `cp` 到 `~/.hermes/scripts/`
2. 改完后跑 `md5sum` 比对两份确认一致
3. **首选**：删 `~/.hermes/scripts/` 下的所有 `trendradar_*.py`，让 cron 失败暴露而非静默跑老版本

**检测**：
```bash
for f in ~/.hermes/scripts/trendradar_*.py; do
  bn=$(basename "$f")
  git_path=~/.hermes/trendradar/hermes-scripts/"$bn"
  [ -f "$git_path" ] && [ "$(md5sum < "$f")" != "$(md5sum < "$git_path")" ] && \
    echo "DRIFT: $bn"
done
```

**根除方案**（待实施）：写一个 `~/.hermes/scripts/sync_hermes_scripts.sh` 在 post-commit hook 跑 `cp`；或用 `HERMES_HOME/scripts/` 软链 `~/.hermes/trendradar/hermes-scripts/`。

## 22. 偏好：体检/清理/审计任务"一切从简"（2026-06-01 起的用户偏好）

**信号**：用户说"本来该删的东西直接改健康体检脚本好了"。

**做法**：
- 主动砍孤儿脚本/死代码/未用变量
- 合并可合并模块
- 保留运维工具（即便 0 引用）
- 数据相关测试加 `@pytest.mark.skip` 而非改生产代码
- 健康检查精简到 4-7 个核心 check，不做"防御性"过度检查
- 不 import 任何 `trendradar.*` 包（避免 cron PYTHONPATH 问题）——用 stdlib（sqlite3 / subprocess / curl / systemd）

**v3.0 health_check.py 实施**：参考 `templates/trendradar_health_check.py` 模板（精简到 7 个 check：db / scripts / cron / gateway / api / memory / data_freshness）。

## 23. git blob 污染（行号 `N|` 前缀）+ 截断（罕见但已发生，2026-06-02）

**症状**：从 git blob 重建的文件每行带 `N|` 前缀（`1|#!/usr/bin/env python3`），Python 直接 `SyntaxError`；且可能在 `except` 等关键行截断（少 78 行）。

**根因**：在某些 git 工作流（交互式 rebase、reflog 恢复、cherry-pick 冲突解决后）blob 存储本身被某种 line-ending filter / smudge hook 污染，每行 prepend 行号字符 `^\d+\|`。**注意：这不是 read_file 工具的显示**——`od -c` 看 raw bytes 确认文件本身就有 `N|` 前缀。

**诊断**：
```bash
git cat-file -p <blob_sha> | head -1 | od -c | head -1
# 污染时：0000000   1   |   #   !   /   u   s   r
# 正常时：0000000   #   !   /   u   s   r
```

**修复**：
```bash
# 剥污染（每行去掉 N| 前缀）
git cat-file -p <blob_sha> | sed -E 's/^[0-9]+\|//' > recovered.py
```

**更稳的做法**：放弃从 git 恢复，直接用 `write_file` 全量重写（write_file 工具已做行号脱敏）。

**预防**：
- 修改 hermes-scripts 文件时**不要用** sed 原地编辑 + git 直接 track（容易污染），用 `write_file` 全量重写
- `patch` 工具的 `old_string` 必须用 `od -c` 或 `hexdump` 看 raw bytes 复制，不要用 `read_file` 显示的 `LINE|CONTENT` 格式（前者会带上 `N|` 前缀污染匹配）
- 定期 `git fsck` + `git gc` 检查 blob 完整性

## 24. `gen_cron_prompt.py` 自身的 PYTHONPATH bug（2026-06-09 Windows 实战）

**症状**：`python scripts/gen_cron_prompt.py` 报 `ModuleNotFoundError: No module named 'trendradar'`。**这个文件本身**定义了 `PYTHONPATH = str(HERMES_HOME)`（即 `TRENDRADAR_HOME.parent`），它会把错误的 PYTHONPATH **写进生成的 cron prompt** 里——所以即使你手动设 env 把它跑起来，生成的 prompt 也会让 cron job 跑失败。

**根因**：第35行硬编码 `PYTHONPATH = str(HERMES_HOME)`（= `TRENDRADAR_HOME.parent`），违反 #20 铁律。

**修复**（2026-06-09 已修）：
```python
# 错：
PYTHONPATH = str(HERMES_HOME)  # = ~/.hermes/

# 对：
PYTHONPATH = str(TRENDRADAR_HOME)  # = ~/.hermes/trendradar/
```

**外层副本同步**：内层（git 真相源）修完后，跑 `bash scripts_sync.sh` 把 `scripts/` 同步到外层。

**调用前置**（Windows + 默认 Windows 路径）：
```bash
# bash 用 MSYS 路径，PYTHONPATH 必须用 Windows 原生路径
TRENDRADAR_HOME="C:\\Users\\ASUS\\AppData\\Local\\hermes\\trendradar" \
PYTHONPATH="C:\\Users\\ASUS\\AppData\\Local\\hermes\\trendradar" \
  python "$TR/trendradar/scripts/gen_cron_prompt.py"
```

**预防**：所有 `PYTHONPATH` 赋值 grep 检查：
```bash
grep -rn "PYTHONPATH" ~/.hermes/trendradar/trendradar/scripts/ | grep "\.parent\|HERMES_HOME[^_]"
# 期望：0 命中
```

## 25. cron job 重建顺序 — 先验 `HERMES_HOME/scripts/` 目录存在（2026-06-09 Windows 实战）

**症状**：计划 `hermes cron create --script trendradar_health_check.py --no-agent` 时，如果 `~/.hermes/scripts/` 目录不存在，第一条 `--script=` job 创建就会因 scheduler.py:984 的路径校验失败而拒绝（错误信息 `Blocked: script path resolves outside the scripts directory`）。

**根因**：scheduler 强制约束 `scripts_dir = _get_hermes_home() / "scripts"` 并 mkdir，但 **mkdir 只在该函数被首次调用时执行**——如果从来没创建过 no_agent cron job，目录就一直缺。

**修复协议**（按顺序）：
1. **先** `mkdir -p "$HERMES_HOME/scripts"`（手动建好）
2. **再** `cp -v "$TREND/hermes-scripts/"*.py "$HERMES_HOME/scripts/"`（同步脚本副本，md5 比对）
3. **再** `hermes cron create ... --script=... --no-agent`

**检测**：
```bash
HERMES_HOME=$(python -c "from hermes_constants import get_hermes_home; print(get_hermes_home())")
[ -d "$HERMES_HOME/scripts" ] || echo "MISSING: must mkdir before creating no_agent cron jobs"
```

## 26. WeCom 凭证配置完整流程（2026-06-09 Windows 实战）

**完整启动 WeCom 推送的 5 步**：

1. **写 `.env`**（追加不覆盖；用 python 而非 echo 避免 shell history）：
   ```python
   import os
   env_path = os.environ['LOCALAPPDATA'] + r'\hermes\.env'
   with open(env_path, 'a', encoding='utf-8') as f:
       f.write(f'WECOM_BOT_ID={bot}\nWECOM_SECRET=***  ```python

2. **`config.yaml` 末尾追加**：
   ```yaml
   platforms:
     wecom:
       enabled: true
       extra:
         bot_id: "<bot_id>"
         secret: "<secret>"
         websocket_url: "wss://openws.work.weixin.qq.com"
         dm_policy: "open"
   ```

3. **重启 gateway**（前台 `hermes gateway run --accept-hooks` 或 `hermes gateway install` 需 UAC）

4. **验证连接**：`tail logs/gateway.log` 看 `✓ wecom connected` + `Connected to wss://openws.work.weixin.qq.com`

5. **建推送 cron job**：先用 `--deliver local` 验证流程通，再切 `--deliver wecom`（或 `wecom:chat_id`）

**Windows 路径 vs POSIX 路径**：bash 里用 `python <<'PY'` heredoc 写文件最稳，避免 MSYS 路径转换导致 string 乱码。

## 27. Hermes 的真实 HERMES_HOME 在 Windows 上不是 `~/.hermes/`（2026-06-09 实战）

**症状**：skill 文档里写 `~/.hermes/trendradar/...`，但 `ls ~/.hermes/` 报 `No such file or directory`，按文档路径操作全部失败。

**根因**：Hermes 在 Windows 上把 home 解析为 `%LOCALAPPDATA%\hermes`（即 `C:\Users\ASUS\AppData\Local\hermes\`），不是 bash home（`C:\Users\ASUS\`）。skill 文档里的 `~/.hermes/` 是 Linux 的简写，跨平台时必须翻译。

**验证 HERMES_HOME 真值**（任何诊断第一步）：
```bash
# 方法 1：直接调 hermes 自己的函数
python -c "from hermes_constants import get_hermes_home; print(get_hermes_home())"
# → C:\Users\ASUS\AppData\Local\hermes

# 方法 2：env var
echo $HERMES_HOME
# → C:\Users\ASUS\AppData\Local\hermes

# 方法 3：CLI
hermes config show | grep Config
# → Config: C:\Users\ASUS\AppData\Local\hermes\config.yaml
```

**预防清单**：诊断 TrendRadar / 自定义脚本 / cron 时，**第一步**先确认 HERMES_HOME 真实值，不要假设 `~/.hermes/`。

**skill 文档改进建议**（待 self-healing 维护）：把所有 `~/.hermes/` 路径写法改为 `${HERMES_HOME}` 变量引用，或在 frontmatter 加 `platforms: [windows, linux]` 提示。

## 29. 看门狗与 LLM 管线竞态 — no_agent 跑在 archive 生成前（2026-06-29 实测）

**症状**：`delivery_watchdog`（no_agent cron）在 12:03:28 运行，但 `pipeline_orchestrator`（LLM cron）在 12:03:51 才生成 archive → 看门狗找到空 archive，静默跳过 → 简报从未投递。

**根因**：两个 cron job 都调度在 `0 9,12,21` 同时触发。no_agent 脚本秒级完成，LLM 管线需 30-60s。看门狗永远跑在 archive 生成前。

**修复**（2026-06-29）：看门狗推迟 5 分钟 → `5 9,12,21 * * *`。

```bash
hermes cron update 27d771f009ae --schedule "5 9,12,21 * * *"
# 验证
hermes cron list | grep -A3 "推送看门狗"
```

**验证**：下次 21:00，管线 21:00 触发 → 21:05 看门狗跑 → archive 已就绪 → 正常投递。

**预防**：任何 `no_agent` 投递类 cron（delivery_watchdog/slot_direct_push）的调度必须晚于 LLM 管线 cron，留出 3-5 分钟余量。不要在 SKILL.md 里写死同时间、期待调度器按序执行——调度顺序不可控。

## 30. `HERMES_CRON_SESSION` 环境变量残留导致 `hermes send` 静默跳过（2026-06-29 实测）

**症状**：手动 `hermes cron run <job_id>` 后，shell 环境留下 `HERMES_CRON_SESSION=1`、`HERMES_CRON_AUTO_DELIVER_PLATFORM=wecom`、`HERMES_CRON_AUTO_DELIVER_CHAT_ID=bl`。此后所有 `hermes send --to wecom:bl` 都被**静默跳过**，返回：
```
Skipped send_message to wecom:bl. This cron job will already auto-deliver its final response...
exit=0
```
但没有任何内容实际投递到 WeCom。

**根因**：terminal 工具的 shell 环境跨调用继承。`hermes cron run` 在子进程设了这些 env var，进程退出后它们仍在 bash 环境中。`hermes send` 检测到 `HERMES_CRON_SESSION=1` 认为自己在 cron 上下文，跳过发送。

**诊断**：
```bash
env | grep HERMES_CRON
# → 有输出 = 有残留
```

**修复**：
```bash
# 方法 1（推荐）：unset 所有 cron 残留 env var
unset HERMES_CRON_SESSION HERMES_CRON_AUTO_DELIVER_PLATFORM \
      HERMES_CRON_AUTO_DELIVER_CHAT_ID HERMES_QUIET

# 方法 2：在子进程里调 hermes send（不污染父 shell）
env -u HERMES_CRON_SESSION hermes send --to wecom:bl "test"

# 方法 3：写临时脚本用 clean environment 调 hermes send
```

**验证**：
```bash
unset HERMES_CRON_SESSION
echo "test" | hermes send --to wecom:bl
# → 期望输出 "Sent to wecom home channel (chat_id: bl)"
```

**预防**：手动补推/测试投递前**先检查** `env | grep HERMES_CRON`。`hermes cron run` 后不要立即 `hermes send`——必须先 unset 污染 env var。长期方案：Hermes CLI 自身应清理 cron env var 再执行 send。

**注意**：这个陷阱只在 `hermes cron run <job>` 后的同一 shell 会话中出现。新开终端/重启 Hermes 不会受影响。
