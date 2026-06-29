---
name: system-config
slug: system-config
version: 2.23.0
description: TrendRadar 项目路径、Python 环境、Cron 任务、代理配置速查。
author: Hermes Agent
metadata:
  hermes:
    tags: [trendradar, config, setup]
---

## 触发

Agent 需要 TrendRadar 路径/Python 环境/Cron/代理/同步信息时自动加载。

> **⚠️ 2026-06-29 仓库重构**：TrendRadar 已从「双层重复结构」（根 config/scripts + 内层 trendradar/config/scripts）简化为「单 Python 包」结构。详见 `references/2026-06-29-repo-restructure.md`。以下章节中所有「双层设计」「scripts_sync.sh」「三副本同步」「双 scripts 阴影陷阱」均为**历史内容**，保留供参考但不再适用。

## 项目结构（2026-06-29 重构后）

TrendRadar 采用**嵌套双层结构**（外层 =运行时根 + git 主视角；内层 = Python 包镜像），这是历史设计，**不要尝试合并**：

| 层 |路径 |角色 |
|---|------|------|
| **外层** | `~/.hermes/trendradar/`（git toplevel = 这层） | `TRENDRADAR_HOME` — cron Workdir / Python PYTHONPATH入口 / git HEAD |
| **内层** | `~/.hermes/trendradar/trendradar/` | Python 包 `trendradar.*`（有 `__init__.py`），用于 `from trendradar.scripts.xxx import yyy` |

- **简报存档**: `~/.hermes/trendradar/archive/YYYY-MM-DD/{slot}.md`（render_markdown 自动写入，补发用）
- **Git 发布仓**: `~/TrendRadar/`
- **从零搭建**: `~/TrendRadar/trendradar/../../references/SETUP.md`
- **一条龙部署**: `~/TrendRadar/one-key-setup.sh`

> **2026-05-30**: Pipeline v2.9.0 — subprocess架构替换为直接函数调用。`pipeline_orchestrator.run_stage()`签名为 `(name: str, func, *args)`。详见 `references/pipeline-v2.9.md`。

### ⚠️ 为什么是双层（**历史 — 2026-06-29 已重构为单包结构**）

commit `5c21d19`（2026-06-02）显式记录了设计决策：

1. **GitHub Web UI 不展开 symlink**：5/30之前外层 `config/` `scripts/` 是 symlink → `trendradar/config/` `trendradar/scripts/`。GitHub Web UI 只显示 symlink那一行 `config -> trendradar/config`，用户看到以为是空目录。
2. **修法（已实施）**：外层 `config/` `scripts/`改为**真目录**（13+33 个文件 =46 个），git跟踪真目录，GitHub 显示真目录。
3. **内层保留**：内层 `trendradar/config/` `trendradar/scripts/`仍 tracked，Python `import trendradar.scripts.settings` 通过 `PYTHONPATH=TRENDRADAR_HOME`找到内层包。
4. **`scripts_sync.sh`双向同步**：内层 ⇄ 外层，内容必须一致。改一边后必须 `bash scripts_sync.sh`（默认内→外）或 `--reverse`（外→内）。

### ⚠️ "根级目录删了又会变"的早期警告已过时

5/29短期把 root 级 `config/` `scripts/`删了想合并，结果 cron静默失败（`sources.json not found`），最后通过 `5c21d19`改回**双层真目录**结构。**现在**外层 `config/` `scripts/` `hermes-scripts/` `prompts/` `references/` 都是真目录+git tracked，**不要再尝试合并或删除它们**。

### ⚠️ 重构前必读 git log（2026-06-10 实测教训）

任何"看着别扭"的结构，**重构前**先 `git log --oneline -10`找最近的 fix commit，再 `git show <sha> --stat` 看 commit message里的设计意图。2026-06-10 一开始假设"git仓库应该在内层 trendradar/"是错的，差点 `mv .git`破坏188 个 tracked 文件；读了 `5c21d19` 的 message 才意识到双层是有意为之。重构前的5 分钟 `git log` 能避免后续1小时的灾难恢复。

**铁律**：
-看到嵌套双层目录、symlink、git 多视角等"奇怪"结构 → **先 git log** 再判断
- `git log --oneline --grep=fix`找最近的修复 commit 通常能直接读到设计决策说明
-任何 `mv .git`、`rm -rf <dir>`、`git reset --hard` 等不可逆操作前**必须** bundle备份：`git bundle create $HOME/repo-<date>.bundle --all`

### ⚠️ Windows 大小写不敏感陷阱——"两个 trendradar"实际是同一个目录（2026-06-10惨痛教训）

用户最初报"工作区有两个TrendRadar嵌套"。我**误读**了：以为 `C:\Users\ASUS\AppData\Local\hermes\trendradar\` 和 `.../TrendRadar\` 是两个独立目录，给出3 条分离路线 + 执行了 `mv .git` 操作——**全是基于错误前提**。

**真相**：Windows NTFS **case-insensitive but case-preserving**。`trendradar/` 和 `TrendRadar/` **是同一个目录**（同一 inode）。MSYS bash 在 `cd TrendRadar` 时把 case折叠到 `trendradar`（同一目录）后访问，但**显示层保留了用户输入的 case**，让我误以为有两个目录。

**证据**：
```bash
$ stat -c '%i' "$HERMES_HOME/trendradar" "$HERMES_HOME/TrendRadar"
55732045388994822 trendradar ←同一 inode
55732045388994822 TrendRadar ←同一 inode

$ cmd //c "dir /X | findstr /I trendradar"
TRENDR~1 trendradar ←同一目录的8.3短名
```

**铁律**（任何"分离两个看似嵌套目录"的操作前必跑）：
```bash
#唯一可靠的"是不是两个目录"判断
stat -c '%i %n' path1 path2 | awk '{print $1}' | sort -u | wc -l
# →1 =同一个目录（不要做任何分离！）
# →2 =真正两个目录（可以分离）
```

**正确叙事**（TrendRadar 的真实结构，**只有一个目录**）：
- `C:\Users\ASUS\AppData\Local\hermes\trendradar\` ← **唯一一个目录**
 - 外层 `config/` `scripts/` `hermes-scripts/` `prompts/` `scripts_sync.sh` —— git 主视角，cron Workdir
 - 内层 `trendradar/` —— Python 包镜像（`__init__.py`），用于 `from trendradar.scripts.xxx import yyy`
 - **嵌套双层是设计**（commit5c21d19），不要尝试合并或分离

**用户最初的"嵌套"抱怨实际是什么**：用户看到的"嵌套" =目录里有一个 `trendradar/trendradar/` 子目录。这是 Python 包布局，**不可消除**（消除后 `from trendradar.scripts.xxx`全部 `ModuleNotFoundError`）。告诉用户"这是设计，不要碰"。

**反例（我犯的错，下次别再犯）**：
- ❌看到 `TrendRadar/` 和 `trendradar/` 两份路径 →假设是两个独立目录 → 设计分离方案
- ✅第一步永远是 `stat -c '%i'`验证
- ❌基于"两个目录"前提给3 条路线 + 执行 `mv .git` →188 个 `D` 文件
- ✅先 bundle备份（`git bundle create $HOME/repo-<date>.bundle --all`）+ git log5c21d19 + stat inode 三件套全做完再动任何文件

### ⚠️ `mv .git`前必做4件事（强化版，2026-06-10教训）

### ⚠️全新本地仓库 `git clone`后**本地可能落后远程**（2026-06-10 实测）

**症状**：`git clone https://github.com/BedrockLian/TrendRadar.git /new/path` 后，`cd /new/path && git log --oneline -1` 显示本地 HEAD = `00e7abe`(5/2旧)，但 `git log --oneline origin/main -1` 显示 remote HEAD = `36f89b9`(新er)。**本地比远程落后 N 个 commit**。

**根因**：上游仓库在 clone 之间有别人 push 过 commits（自己手动、其他 contributor、CI auto-commit）。`git clone` 只拉 origin/HEAD，不会自动 rebase 到本地。

**陷阱**：push 时 `sync_repo.sh` 检测 `behind >0` 会**拒绝 push**(保护设计)，但用户不知道该怎么办。

**修复**（首次 sync 前必做）：

```bash
cd "$HERMES_HOME/repo trendradar"
#1) 看本地 vs remote差距
git fetch origin
git log --oneline HEAD..origin/main | wc -l # remote ahead
git log --oneline origin/main..HEAD | wc -l # local ahead (应=0,刚clone)

#2)决策: fast-forward merge(无冲突的话最安全)
git merge --ff-only origin/main
# → 'Already up to date' =完美
# → 'Fast-forward' = OK
# → 'Not possible to fast-forward' = 有分叉,需要 rebase 或手动

#3) 不要 force-push(会污染别人的 commit)
# 不要 git push -f
```

**铁律**：本地新仓库**首次** sync 前必做 `git fetch origin && git merge --ff-only origin/main`。否则 push 会因为本地落后被拒绝（这是 sync_repo.sh 的设计保护，**不要绕过**）。

### ⚠️ `.git`搬位置 ≠ git 工作树变更（2026-06-10 实测）

**症状**：`mv .git <other>/.git` 后 `git status -s`报188 个 `D`(deleted) —— index里的 tracked路径跟新 working tree 的目录布局对不上。

**根因**：git index 是**相对 git toplevel** 的路径列表。`mv .git`改 .git目录物理位置，但** working tree仍是 mv后的 cwd**。如果新 cwd 的目录布局跟旧 working tree 不一致（即使文件名一样、目录层级不同），所有 tracked路径全部失效。

**实例**（2026-06-10 我犯的）：
-旧 working tree：`trendradar/`(外层) = git 主视角，有 `scripts/` `config/` `hermes-scripts/` `prompts/`
- 新 working tree：`trendradar/trendradar/`(内层) = Python 包视角，有 `trendradar/scripts/` `trendradar/config/`
- index 里 tracked = `scripts/...` `config/...` `hermes-scripts/...` `prompts/...` —— **全是旧视角**
- 新 working tree 里这些路径不存在 →188 个 `D`

**修复**（任何 `.git`迁移操作前必做）：

```bash
#1) 先看 index 里有哪些路径
cd <new_toplevel> && git ls-files | head -10
# → 如果输出路径全是 'scripts/' 'config/' 而不是 'trendradar/scripts/' 'trendradar/config/' =视图不匹配

#2)决策 A:改 working tree 让它跟 index 一致 (git mv 或手动调整目录)
#决策 B: 重写 index适应新 working tree (git read-tree +重新 add all)
#决策 C:撤销 mv, .git放回原位 (推荐,如果只是想 .git 在不同位置)
```

**铁律**：**任何 `mv .git` / `cp -r .git <new>` 操作之前**，先 `git rev-parse --show-toplevel`确认旧 toplevel，再用 `git ls-files | head`确认 tracked路径布局。**新 cwd 必须跟旧 toplevel 的目录结构等价**，否则 git status 会爆。**不确定就撤销**——`.git`搬位置无法 rollback after first status check。

### ⚠️全新本地仓库创建后**首次 sync + push 必须走 `git push --dry-run`**（2026-06-10 实测）

**症状**：第一次 sync_repo.sh跑完 commit 后直接 push 到 origin main。万一你 commit message写得不对、staged 了不该推的文件（比如没排除 .env），会**直接污染 GitHub main**。

**修复**（首次 sync必走流程）：

```bash
cd "$HERMES_HOME/repo trendradar"

#1) sync_repo.sh --dry-run 看 diff (不真 commit/push)
bash sync_repo.sh --dry-run | head -60
# → 看 [commit --dry-run] msg + diff stat: 文件数 /改动大小合理?

#2)单独 commit --dry-run 看 staged 内容
bash sync_repo.sh --commit --dry-run
# → 看 git diff --cached --stat:哪些文件 staged?有没有不该推的?

#3)单独 push --dry-run 看远端接收
bash sync_repo.sh --push --dry-run
# → 输出 'Everything up-to-date' 或 'To https://github.com/...'预览

#4)上面3步都 OK 后才真跑
bash sync_repo.sh
```

**铁律**：**新仓库 + 新 pipeline 的首次全流程 sync必走4步 dry-run验证**。日常 sync (代码改动后立即跑) 可以跳过 dry-run，因为单次改动小。**只有首次 +重大 schema变更**需要 dry-run。

### ⚠️ `mv .git`前必做4件事（强化版，2026-06-10教训）

`scripts/repo-restructuring-playbook.md`已经有 git log + bundle备份协议，但2026-06-10 我**明知有 playbook 还执行了 `mv .git` 操作**——说明 playbook **不够醒目**。这里把"重构前必做"提升到 SKILL.md 正文层级：

**任何 `mv .git` / `rm -rf <dir>` / `git reset --hard` 等不可逆操作前，4步必做**：

1. **inode验证**（避免 Windows case-insensitive误判）：
 ```bash
 stat -c '%i' . "$TARGET" #同一 inode =同一目录，不要分离
 ```

2. **bundle备份**：
 ```bash
 git bundle create $HOME/repo-$(date +%Y%m%d-%H%M).bundle --all
 ls -la $HOME/repo-*.bundle # 必须存在且 >1MB
 ```

3. **git log找最近的 fix commit**（找设计意图）：
 ```bash
 git log --oneline -10
 git log --oneline --grep=fix #找 fix关键词的 commit
 git show '5c21d19' --stat # 看 commit message解释
 ```

4. **dry-run评估影响**：
 ```bash
 # 如果动 .git，看 status 会变成什么
 mv .git .git.bak && git status -s | wc -l && mv .git.bak .git
 # 如果 status数字 >0 →移动会影响大量 tracked 文件，重新考虑
 ```

**只有4步全过且没异常**，才执行 `mv .git`。否则继续诊断。

> **⚠️ Windows 部署陷阱集（2026-06-09 实战发现）** —— 整个 TrendRadar 仓库是 Linux 起家，几乎所有 Python 脚本里都有 Linux-only 的硬编码。Windows 上跑前必须审计这些：
>
> 1. **`HERMES_HOME` 不是 `~/.hermes`** —— 在 Windows 上 `Path.home() / '.hermes'` 解析为 `C:\Users\<user>\.hermes`（不存在）。真实位置是 `%LOCALAPPDATA%\hermes\`。脚本里写 `HERMES_HOME = os.path.expanduser("~/.hermes")` 的全部是 bug。
>    **修复模式**：用 `hermes_constants.get_hermes_home()`（hermes-agent 自带 API），或 `os.environ['LOCALAPPDATA'] + '/hermes'`，或读 `HERMES_HOME` 环境变量 fallback 到 `Path.home() / '.hermes'`（仅 Linux 兜底）。delivery_watchdog.py 的 `_resolve_hermes_home()` 是参考实现。
>
> 2. **`PYTHONPATH = TRENDRADAR_HOME.parent` 是 Linux-only 假设** —— `~/.hermes/trendradar/<pkg>` 在 Linux 可见，但 Windows 上 `parent = %LOCALAPPDATA%\hermes\`，里面**没有** `trendradar/` 包。`gen_cron_prompt.py` 里这行直接报错 `ModuleNotFoundError: No module named 'trendradar'`。
>    **修复**：PYTHONPATH 必须是 `TRENDRADAR_HOME` 本身（包所在），不是 `.parent`。详见 `references/wsl-disk-space-management.md` 同类陷阱段。
>
> 3. **`/tmp/hermes_*.sock` Unix-domain socket 永远不可达** —— WeCom gateway 在 Windows 用 named pipe 或 TCP localhost，不暴露 `/tmp/`。`check_socket()` 必须加 Windows HTTP fallback（探测 `127.0.0.1:{8765,8000,8888,7777}/health`）。
>
> 4. **`/usr/local/bin/python3.14t` 在 Windows 不存在** —— 脚本里 `PYTHON = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')` 会让 `subprocess.run([PYTHON, ...])` 直接失败。
>    **修复**：探测顺序 `HERMES_HOME/hermes-agent/venv/Scripts/python.exe` (Win) → `.../venv/bin/python` (Linux) → `sys.executable` 兜底。
>
> 5. **`subprocess.run(env={**os.environ, "HERMES_HOME": HERMES_HOME, ...})` 会在 Windows 报 `TypeError: environment can only contain strings`** —— 当 `HERMES_HOME` 是 `Path` 对象时，Python 在 POSIX 静默接受，但 Windows CreateProcess 要求全部 str。
>    **修复**：`env = {k: (str(v) if not isinstance(v, str) else v) for k, v in os.environ.items()}; env["HERMES_HOME"] = str(HERMES_HOME)`。这是 `delivery_watchdog.get_cron_jobs()` 修复的具体代码。
>
> 6. **hermes gateway 在 Windows 不会自动加 systemd override** —— Linux 上靠 systemd 注入 `HTTP_PROXY` / `NO_PROXY`；Windows 没有 systemd。LLM 类 cron 走直连，timeout 时需要在 `gateway.yaml` 或 Scheduled Task 环境里手动注入代理。
>    详见 `references/proxy-config.md` Gateway 级别代理章节。

> **⚠️ scheduler `scripts_dir` 不存在会让所有 no_agent cron 静默失败（2026-06-09）** —— scheduler 源码 `cron/scheduler.py:984` 硬约束 `scripts_dir = _get_hermes_home() / "scripts"`，且做 `path.relative_to(scripts_dir_resolved)` 安全检查（`Block: script path resolves outside the scripts directory`）。在 Windows 下 `HERMES_HOME/scripts/` 默认**不存在**。
> **诊断**：`hermes cron list` 显示 `No active jobs` 或 job 状态 active 但永远不跑 → `~/.hermes/logs/gateway.log` 看不到该 job 的 stdout。
> **修复**：把 `hermes-scripts/*.py` **拷贝**（不是 symlink）到 `%HERMES_HOME%\scripts\`：`mkdir -p $HERMES_HOME/scripts && cp $TR/hermes-scripts/*.py $HERMES_HOME/scripts/ && md5sum` 比对。注意用 `cp` 而**不是** `ln -s`：scheduler 的 `relative_to()` 路径检查在 Windows 上对 symlink 行为不一致。
> 这是 pitfall #21 的实际触发场景。

> **⚠️ `enabled_toolsets: null` 不等于 default toolset（2026-06-09）** —— `hermes cron create` 不暴露 `--toolset` 选项，`cron edit` 也没有。LLM job 默认 `enabled_toolsets=null` 时行为不稳定（实际跑下来不一定带 `delegation` toolset）。
> **诊断**：LLM 跑出来 final response 没用 `delegate_task`，或 prompt 里明确要求启 sub-agent 但 agent 说"工具不可用"。
> **修复**：直接编辑 `~/.hermes/cron/jobs.json`，把对应 job 的 `enabled_toolsets` 从 `null` 改为 `["default", "delegation"]`。改完**必须** `hermes gateway restart`（Windows 上 `hermes gateway stop && hermes gateway run --accept-hooks`）让 scheduler 重读。
>
> 适用场景：任何用 `delegate_task` 的 LLM cron job —— news-secretary evening deep analysis（3 flash sub-agent）、report-generator 月报深度搜索（六步协议）、任何 spawn sub-agent 的场景。

> **⚠️ Hermes skill loader 看不到没有 SKILL.md 的目录（2026-06-09）** —— `skills_list` 只列叶子级 skill。如果在 `~/.hermes/skills/<name>/` 下放了子目录和 reference 文件，但**没有**该 `<name>/SKILL.md`，整个目录会被跳过（连同子目录里的 skill 一起看不到）。
> **诊断**：`ls ~/.hermes/skills/<name>/` 看到内容，但 `skills_list` 不出现 `<name>`，子目录里的 `SKILL.md` 也没被加载。
> **修复**：(a) 创建 `<name>/SKILL.md` 充当 umbrella 索引（每个子 skill 一行 + 触发条件），或 (b) 把子 skill 直接平铺到 `~/.hermes/skills/`。TrendRadar 当前采用 (a) 模式但缺 umbrella SKILL.md，所以 `trendradar` 这个类目名不会出现在 `skills_list` 输出（即使4 个子 skill `news-secretary/report-generator/self-healing/system-config` 都能加载）。

> **⚠️ 双 data 目录分裂陷阱（2026-06-02 发现）**: 仓库内有两份 `data/` 目录：
> - `~/.hermes/trendradar/data/` — TRENDRADAR_HOME 默认 `data_dir`，**ai_translate / render_markdown / pipeline_orchestrator 实际读这里**（cron 运行时写）
> - `~/.hermes/trendradar/trendradar/data/` — git 跟踪的副本（仓库子目录）
>
> 两者**完全独立**，互不自动同步。常见错误：
> 1. 手动改 git 副本（`trendradar/data/curated_*.json`）→ ai_translate 不读它 → 看起来"改了无效"
> 2. ai_translate 翻译写回外层 `data/curated_evening_20260602.json` → git 副本不同步 → `git status` 不报（git 不跟踪外层）→ 推送后 GitHub 仍是旧版
>
> **铁律**：
> - **生产测试**（手动跑 ai_translate/render）→ 改外层 `~/.hermes/trendradar/data/`（`find_curated_file` 找这里）
> - **修改持久化** → 改完外层后**手动 cp** 到 git 副本：`cp ~/.hermes/trendradar/data/curated_*.json ~/.hermes/trendradar/trendradar/data/`
> - **还原生产数据** → md5 校验比对原始 snapshot（如 `/tmp/curated_<date>.bak.json`）
> - 排查时第一件事：`ls -la ~/.hermes/trendradar/data/curated_*.json` 看 mtime，确认 ai_translate 实际读的是哪份

## Hermes 关键路径

| 组件 | 路径 |
|------|------|
| 主配置 | `~/.hermes/config.yaml` |
| Cron 配置 | `~/.hermes/cron/jobs.json` |
| 技能目录 | `~/.hermes/skills/trendradar/` |
| 运行日志 | `~/.hermes/logs/agent.log` / `errors.log` |

## 健康诊断 Playbook

TrendRadar 链路异常（用户说"今天没收到日报"/"推送断了"等）时，按 `references/health-diagnosis-playbook.md` 的 7 步顺序排查 ~10 分钟能定位 ~90% 问题。该 playbook 是 2026-06-09 全量诊断的实战总结，包含已知坑速查表。

### ⚠️ 跨平台路径陷阱：POSIX `~/.hermes/` ≠ Windows 用户根 `.hermes/`（2026-06-09 诊断踩坑）

SKILL.md 中所有 `~/.hermes/...` 在 Windows host 上由 `hermes_constants.get_hermes_home()` 解析为：

| OS | `~/.hermes/` 实际位置 |
|----|------------------------|
| Linux/macOS | `$HOME/.hermes/`（即 `/home/<user>/.hermes/`）|
| **Windows** | `%LOCALAPPDATA%\hermes\`（即 `C:\Users\<user>\AppData\Local\hermes\`）——**不是** `C:\Users\<user>\.hermes\` |

**症状**（2026-06-09 实测）：
```bash
# 在 Windows git-bash (MSYS) 里：
ls ~/.hermes/trendradar/   # → No such file or directory（找不到！）
ls /c/Users/<user>/.hermes/  # → 也找不到！
ls "$LOCALAPPDATA/hermes/"   # → 找到了，真实数据在这里
```

**铁律**（任何诊断命令必须用环境变量，不要硬编码 `~/.hermes/`）：
```bash
# ✅ 跨平台
HERMES_HOME="${HERMES_HOME:-$LOCALAPPDATA/hermes}"   # Windows
# 或 Linux: HERMES_HOME="$HOME/.hermes"
ls -la "$HERMES_HOME/trendradar/"

# ❌ 硬编码（Windows 找不到）
ls -la ~/.hermes/trendradar/
```

**Python 端** `get_hermes_home()` 已经处理平台差异——**Shell 端**必须自己处理。最稳的做法：诊断时直接读 `hermes_constants.py:HERMES_HOME` 的实际值，或 `python -c "from hermes_constants import get_hermes_home; print(get_hermes_home())"`。

**额外陷阱**（Windows bash）：MSYS 把 `C:\Users\<user>\AppData\Local\hermes` 显示为 `/c/Users/<user>/AppData/Local/hermes`，但 `~/.hermes` 在 MSYS bash 不会被自动展开到 `%LOCALAPPDATA%`——它真的去找 `C:\Users\<user>\.hermes\`（用户根的隐藏目录），那个根本不存在。

## Cron 任务

`hermes cron list` 查看所有任务。日报/周报/月报为 LLM 驱动，体检/维护/看门狗为 no_agent 脚本模式。

**Cron prompt 格式**: 自动生成。`hermes-scripts/gen_cron_prompt.py` 从 `pipeline_orchestrator.py --list-steps` 产出 cron prompt 文本。news-secretary SKILL 引用 cron prompt 作为 SSOT，消除 cron prompt 与 SKILL 双份维护漂移。

### ⚠️ Cron 状态解读陷阱（2026-06-09 诊断踩坑）

`hermes cron list` 显示 **`No scheduled jobs`** 不一定是 scheduler 故障，可能是这两种情况之一——必须分别排查：

1. **`jobs.json` 文件不存在** —— 所有 job 从未注册过（首次安装状态）
2. **scheduler 找不到配置文件 / parse error** —— 已注册的 job 都丢了

**诊断顺序**（5 秒定位）：

```bash
# 1. jobs.json 是否存在（scheduler 把所有 job 写这里）
ls -la "$HERMES_HOME/cron/jobs.json" 2>&1   # Windows: %LOCALAPPDATA%\hermes\cron\jobs.json
# → 不存在 = "从未注册"；存在 = 进入第 2 步

# 2. Gateway 实际状态（独立于 jobs.json）
hermes cron status
# → "Gateway is not running" = gateway 服务未启动，job 即便注册了也不会触发
# → "active jobs: N" + N=0 但 jobs.json 有内容 = parse error / 数据损坏
# → "active jobs: N" + N=jobs.json 内 job 数 = 健康

# 3. scheduler 实际能不能跑 no_agent 脚本（HERMES_HOME/scripts 目录）
ls -la "$HERMES_HOME/scripts/" 2>&1
# 不存在 = scheduler 会被 path traversal guard 拦截（scheduler.py:984-1003）
# 即便 job 注册了 + gateway 跑了 + scripts 文件都在外层 `trendradar/scripts/` 也跑不了
# **铁律**：no_agent cron 的 `script=` 字段必须指向 `$HERMES_HOME/scripts/<file>.py`
# 不是说外层 `trendradar/scripts/` 或 git `hermes-scripts/` 里改了就会跑
```

**重新注册 job**（不是修 scheduler，是补注册）：

```bash
hermes cron create --name "日报推送" --schedule "0 9,12,21 * * *" \
  --prompt-file prompts/news_briefing.md \
  --toolsets "terminal,web,messaging"
# 见 SETUP.md 完整 6 个 job 模板
```

**关键铁律**：
- "No scheduled jobs" + "Gateway not running" 同时出现 → 先 `hermes gateway install` 启 gateway，再注册 job
- no_agent cron 改完 `hermes-scripts/*.py` 必须 `cp` 到 `$HERMES_HOME/scripts/`（`scripts_sync.sh` 不覆盖这个目录）
- `scripts_sync.sh` 只维护 `TR/config/ ⇄ TR/trendradar/config/` 和 `TR/scripts/ ⇄ TR/trendradar/scripts/` 两组——**不**碰 `$HERMES_HOME/scripts/`

### ⚠️ `hermes cron create` argparse 陷阱（2026-06-09 实测）

`hermes cron create` 的 argparse 设计与直觉不同：

| 形参 | argparse 定义 | 陷阱 |
|------|---------------|------|
| `schedule` | positional, **无 nargs**（单 token）| 多 token cron 表达式如 `0 9,12,21 * * *` argparse 报错 |
| `prompt` | `nargs="?"`（可选 1 个）| 但当 schedule 多 token 时，prompt `nargs="?"` 会贪婪吞掉剩余 token |
| `--deliver`, `--skill`, `--name` | keyword | OK |

**症状**（实测 3 种）：

1. `hermes cron create "0 9,12,21 * * *" --skill news-secretary "long prompt..."` →
   `usage: hermes cron create [-h]...` 顶层 usage 错误（**"unrecognized arguments: ..."**，prompt 整段当顶层参数处理）

2. `hermes cron create "0 9 * * *" --name ... --prompt "长 prompt ..."` →
   `exit=0` 但 prompt 被 silent 丢弃（只吃了 schedule）

3. MSYS bash 下 `--prompt "*"` 会 glob 扩展为文件列表 → argparse 全部当 token 处理

**正确流程：先 create（无 prompt），再 edit --prompt 追加**：

```bash
# 步骤 1: 占位创建（不带 prompt）
hermes cron create "0 9,12,21 * * *" \
  --name "TrendRadar 日报推送" \
  --skill news-secretary \
  --deliver local
# → Created job: <id>

# 步骤 2: edit 追加 prompt（--prompt 是 keyword arg，不会被吃掉）
hermes cron edit <id> --prompt "$(cat prompts/daily.md)"
```

**关键**：`hermes cron edit --prompt <str>` 是 `--prompt` keyword 参数，整段字符串作为单个值传入；不像 create 那样受 positional 解析影响。

**调试技巧**（任何 cron create 报 "unrecognized arguments"）：
- 检查 prompt 里有没有 `*`、`[`、`$` 等 shell 特殊字符
- 改用 `hermes cron edit <id> --prompt ...` 两步走
- 长 prompt 写到文件用 `$(cat file.md)` 引用

**已知 cron job ID 命名（trendradar 6 个标准 job）**：
| 名称 | Schedule | mode |
|------|----------|------|
| TrendRadar 自动体检 | `0 15 * * *` | no_agent |
| TrendRadar 每日维护 | `0 3 * * *` | no_agent |
| TrendRadar 推送看门狗 | `0 9,12,21 * * *` | no_agent |
| TrendRadar 日报推送 | `0 9,12,21 * * *` | LLM |
| TrendRadar 周报推送 | `30 9 * * 1` | LLM |
| TrendRadar 月度报告 | `0 9 1 * *` | LLM |

**v6.6 cron prompt 单行模式（2026-06-02 起）**：日报 cron 的 final response 模板已**严格限定为单行状态文字**——「已生成 X 简报（N 片），slot_direct_push 接管投递」。零附加文本，sanity_check 不再需要兜底。生成器也对应在 prompt 第 3 步加 `send_message` 工具调用，遍历 fragments 数组逐片投递。如发现 LLM agent 仍输出 briefing 字段或加 "以下是..." 前缀 → ① 检查 cron job toolset 是否移除 `messaging`（v6.6） ② 检查 cron prompt 第 3 步是否更新 ③ 检查 sanity_check.py 拦截器版本。

### ⚠️ WeCom cron 投递 chat_id 陷阱（2026-06-09 实测）

`hermes cron edit <id> --deliver wecom` 会被 scheduler 接受（wecom platform 不需要 `cron_deliver_env_var`），但**投递时静默失败**除非配置了 `WECOM_HOME_CHANNEL` 环境变量。

**症状**：
- `hermes cron edit` 返回 `Updated job`，看起来 OK
- cron 触发后 wecom 没收到消息
- gateway log 显示 "no home channel" 或 chat_id 为空

**根因**（`gateway/config.py:1725`）：
```python
wecom_home = os.getenv("WECOM_HOME_CHANNEL")
if wecom_home:
    config.platforms[Platform.WECOM].home_channel = HomeChannel(
        platform=Platform.WECOM,
        chat_id=wecom_home,
        name=os.getenv("WECOM_HOME_CHANNEL_NAME", "Home"),
        thread_id=os.getenv("WECOM_HOME_CHANNEL_THREAD_ID") or None,
    )
```

**chat_id 获取方式**（2 选 1）：
1. **用户主动发消息触发回调** — 在企业微信找到机器人发任意一条消息，gateway 通过 `aibot_msg_callback` 收到回调后自动记录 userid 到内存
2. **手动设环境变量** — 已知 userid/chatid 时直接写入 `~/.hermes/.env`：
   ```bash
   # .env 追加
   WECOM_HOME_CHANNEL=<userid_or_chatid>
   WECOM_HOME_CHANNEL_NAME=<display_name>  # 可选
   WECOM_HOME_CHANNEL_THREAD_ID=<thread_id>  # 可选，话题模式
   ```

**铁律**：
- 任何 `deliver=wecom` 的 cron job **必须先配置** `WECOM_HOME_CHANNEL` 才能真投递成功
- 切换 `deliver=wecom` 前先用最低风险 job（看门狗/体检）做 canary
- 失败时**优先回退**到 `deliver=local` 确认 cron pipeline 本身正常，避免误判为脚本 bug

**故障模式 — cron timeout**：LLM 驱动的 cron job（日报/优化器）调用 web_search/extract 工具时依赖直连互联网。若直连中断（Errno 101 Network is unreachable）：
1. pipeline 脚本因内部 `PROXY_URL` 配置仍可正常跑
2. 但 LLM agent 的 web 工具尝试直连 → 全部超时 → cron 整体 timeout
3. 修复：Gateway systemd override.conf 注入 `HTTP_PROXY=http://127.0.0.1:7890` + `NO_PROXY=localhost,127.0.0.1,api.deepseek.com`
详见 `references/proxy-config.md` 的 Gateway 级别代理章节。

## 代码架构（2026-05-30 重构后）

```
trendradar/
├── config/                     # ── 配置子模块（从 settings.py 拆分）──
│   ├── domains.py              # 领域常量 (DOMAINS, MAX_PER_DOMAIN, BRIEFING_RATIO, TIER_DIVERSITY_MIN, HIGH_AUTHORITY_THRESHOLD)
│   ├── scoring.py              # 评分参数 (MIN_SCORE, diversity, heat words)
│   ├── api.py                  # API Key/端点/模型 + .env 路径约束
│   ├── translation.py          # TRANSLATE_BATCH_SIZE/MAX_CONCURRENT
│   ├── fetching.py             # 连接池/超时/重试 (TIMEOUT_SEC=8, etc.)
│   ├── proxy.py                # PROXY_URL, needs_proxy()
│   └── heat_tracking.py        # 热度追踪/指纹参数
├── scripts/
│   ├── settings.py             # ── 向后兼容 re-export shim（~110行）──
│   ├── file_utils.py           # get_data_dir, atomic_write_json, 压缩 I/O
│   ├── logging_config.py       # get_logger + _RunIdFormatter
│   ├── storage.py              # Storage(db, vacuum, checkpoint_db, close_db)
│   ├── llm_providers.py        # LLM Provider 解耦（4 协议类）
│   └── ...（其他脚本不变）
├── config/                     # 原 root config/ 已删除（2026-05-29）
└── ...
```

**关键变更**:
- `settings.py` 现在是 re-export 中心——所有现有 `from settings import X` 无需改动
- 新增配置直接加在对应 `config/*.py` 子模块中，然后在 `settings.py` 加一行 re-export
- `get_storage()` 单例在 `settings.py` 中，`record_fingerprints.py` 和 `heat_tracker.py` 已统一接入
- `storage.Storage.checkpoint_db(filename)` 执行 `PRAGMA wal_checkpoint(TRUNCATE)`
- `llm_providers.py`（2026-06-01 新增）— 4 协议类（OpenAI 兼容/Anthropic/Gemini/Ollama）覆盖 7+ LLM 服务，`ai_translate.py` 通过 `provider.chat()` 统一调用。详见 news-secretary SKILL 中"LLM Provider 解耦"章节。

## Python 环境（Windows）

Windows 上有两套 Python 3.14 并存：

| 版本 | 路径 | 可执行文件 | GIL | Py_GIL_DISABLED | 用途 |
|------|------|-----------|-----|-----------------|------|
| 标准版 3.14.5 | `C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\` | `python.exe` | **ON** | 0 | 测试 / 手动调试 |
| **free-threading 3.14.5t** | `C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14t-64\` | **`python3.14t.exe`** | **OFF** | **1** | 生产 pipeline（I/O 并行） |

### Free-threading Python 3.14t 安装记录（2026-06-10）

- **来源**：python.org FTP 只提供 zip 包（无 .exe 安装器）
  - URL: `https://www.python.org/ftp/python/3.14.5/python-3.14.5t-amd64.zip`
- **下载注意**：Windows 直连 python.org 很慢（~300KB/s），必须走代理 `--proxy http://127.0.0.1:7897`
- **解压后**：可执行文件名是 `python3.14t.exe`（不是 `python.exe`！）
- **装 pip**：`python3.14t.exe -m ensurepip`
- **装依赖**：`python3.14t.exe -m pip install feedparser aiohttp pyyaml pytest pytest-asyncio pytest-timeout`
- **zstandard 不可用**：free-threading 没有预编译 wheel，`--only-binary :all:` 也找不到。zstandard 是压缩 raw JSON 的可选依赖，管线不依赖它也能正常跑
- **测试验证**：239 passed, 7 skipped（与标准版一致）

### 跑 pipeline / 测试的正确命令（Windows）

```bash
export TRENDRADAR_HOME="C:/Users/ASUS/AppData/Local/hermes/trendradar"
export PYTHONPATH="$TRENDRADAR_HOME"  # 必须是 TRENDRADAR_HOME 本身，不是 .parent

# 标准版（调试/手动）
"C:/Users/ASUS/AppData/Local/Python/pythoncore-3.14-64/python.exe" -m pytest trendradar/tests/ -q

# Free-threading 版（生产 pipeline）
"C:/Users/ASUS/AppData/Local/Python/pythoncore-3.14t-64/python3.14t.exe" trendradar/scripts/pipeline_orchestrator.py --push-id noon
```

**铁律**：
- Windows 上 **不要设 `PYTHON_GIL=0`** — 3.14t 把空值当"禁用"处理会崩溃。用 `unset PYTHON_GIL` 显式取消
- Free-threading 版的二进制叫 `python3.14t.exe`，不是 `python.exe`

## ⚠️ 双 `scripts/` 目录阴影陷阱（2026-06-03 实战, debug 30+ 次才定位）

**问题根因**：`~/.hermes/trendradar/` 和 `~/.hermes/trendradar/trendradar/` 是**两个独立**的代码副本，**两份 `scripts/`、`config/` 都有 `__init__.py`**（外层是 `scripts/`，内层是 `trendradar/scripts/`）。

`~/.hermes/trendradar/` 顶层**没有** `__init__.py`，所以 Python 把它当**namespace package**（PEP 420）。当 `import trendradar.scripts.fetch_feeds` 时：

1. Python 在 sys.path 上找 `trendradar` 目录
2. 找到 `/home/asus/.hermes/trendradar/`（**无 `__init__.py`** → namespace package）
3. 找 namespace 下的 `scripts` 子包 → 命中 `/home/asus/.hermes/trendradar/scripts/__init__.py`（**外层 legacy 副本**）
4. **外层 legacy 副本 wins**（**永远比嵌套 `trendradar/trendradar/scripts/` 先找到**）

**症状**：你在嵌套目录 `trendradar/scripts/fetch_feeds.py` 改的代码**完全没生效**。`import trendradar.scripts.fetch_feeds as ff; print(ff.__file__)` 显示的是外层 legacy 路径。`find_spec()` 报正确路径，但**实际 import 时拿外层**（namespace package 解析与 find_spec 行为不一致 — 这是 Python 3.3+ namespace package 的已知陷阱）。

**典型失败模式**（2026-06-03 早报空推送）：
```python
# 嵌套 fetch_feeds.py 已修：
_PARSE_POOL = Lazy(_make_parse_pool)
items = await loop.run_in_executor(_PARSE_POOL.get(), ...)

# 但 cron 实际跑的是外层 legacy 版本：
def _get_parse_pool():  # ← 旧 API
    return _PARSE_POOL
items = await loop.run_in_executor(_get_parse_pool(), ...)

# 错误：NameError: name '_get_parse_pool' is not defined
# (新版 _PARSE_POOL.get() 被外层 legacy 覆盖，从未加载)
```

**诊断命令**（5 秒定位）:
```bash
cd /home/asus/.hermes/trendradar
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
PYTHON_GIL=0 PYTHONPATH=/home/asus/.hermes /usr/local/bin/python3.14t -c "
import importlib.util
spec = importlib.util.find_spec('trendradar.scripts.fetch_feeds')
print('find_spec says:', spec.origin)
import trendradar.scripts.fetch_feeds as ff
print('actual load:  ', ff.__file__)
# 两条输出必须一致！不一致 = 命中 shadow 陷阱
"
```

**修复**（3 选 1，按推荐顺序）:

1. **同步两份副本**（最简单）:
   ```bash
   cp /home/asus/.hermes/trendradar/trendradar/scripts/<file>.py \
      /home/asus/.hermes/trendradar/scripts/<file>.py
   ```

2. **顶层加 `__init__.py`**（最彻底）:
   ```bash
   touch /home/asus/.hermes/trendradar/__init__.py
   # 但这会让 Python 优先用外层 legacy（如果外层 legacy 与内层不同步会再次 shadow）
   ```

3. **删除一份副本**（最干净，但要重建 import 链）:
   ```bash
   rm -rf /home/asus/.hermes/trendradar/scripts /home/asus/.hermes/trendradar/config
   # 然后用 scripts_sync.sh 维护单副本
   ```

**铁律**：
- **改完任何文件后必跑 `find_spec vs actual load` 诊断**（如上）— 5 秒
- **任何 cron agent 跑出"`NameError` 某函数未定义"**，先**怀疑双副本阴影**，再怀疑逻辑错误
- 详细复现步骤见 `references/double-scripts-shadow-trap.md`

## ⚠️ 三副本同步铁律（2026-06-03 实装）

TrendRadar 代码在**三处**必须保持一致（**不**是双副本，cron 实际命中的"哪一份"由 namespace package shadow 决定，因此**两边 + git worktree 全部要改**）：

| # | 路径 | 谁用 |
|---|------|------|
| 1 | `~/.hermes/trendradar/scripts/` + `trendradar/scripts/`（legacy 外层 + 嵌套内层，namespace shadow 命中外层） | cron / pipeline runtime |
| 2 | `~/TrendRadar/trendradar/scripts/`（git worktree 副本） | git tracked |
| 3 | GitHub `BedrockLian/TrendRadar` 远程 | publish |

**单改一处 = 静默无效**。改完一份文件后**必跑**：
```bash
SRC=/home/asus/.hermes/trendradar/trendradar/scripts
cp $SRC/<file>.py /home/asus/.hermes/trendradar/scripts/<file>.py
cp $SRC/<file>.py /home/asus/TrendRadar/trendradar/scripts/<file>.py
# 验证 load 的副本对
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
PYTHON_GIL=0 PYTHONPATH=/home/asus/.hermes /usr/local/bin/python3.14t -c "
import importlib.util, importlib
spec = importlib.util.find_spec('trendradar.scripts.<file>')
mod = importlib.import_module('trendradar.scripts.<file>')
assert spec.origin == mod.__file__, f'MISMATCH: find_spec={spec.origin} load={mod.__file__}'
print(f'OK: {mod.__file__}')
"
# 跑测试
PYTHON_GIL=0 PYTHONPATH=/home/asus/.hermes /usr/local/bin/python3.14t -m pytest trendradar/tests/ -q
```

**触发信号**（一旦出现就要立即怀疑三副本不同步）:
- "明明改了 X.py，行为没变" → 90% 是 namespace shadow 命中了外层 legacy 旧版
- "测试通过但 cron 跑挂" → 测试 import 的可能是内层，cron 跑的是外层
- "A 副本 `md5sum` 改了，B 副本没改" → 标准不同步

**与 `scripts_sync.sh` 的关系**: `scripts_sync.sh` 只 sync 外层↔内层（在同一仓库内），**不**覆盖 git worktree `~/TrendRadar/`。完整三副本 = `scripts_sync.sh` + 显式 cp 到 worktree + git commit + push。

## fetch_feeds.py 三个互相叠加的 bug（2026-06-03 同日修复）

**Bug A**：`InterpreterPoolExecutor` 在 `PYTHON_GIL=0` 模式下**不能 pickle args** → `NotShareableError` → 43 个源全失败。

**修复**：
```python
def _make_parse_pool():
    # InterpreterPoolExecutor (3.14) can't pickle args in free-threaded mode
    return concurrent.futures.ThreadPoolExecutor(max_workers=24)
```

**Bug B**：`_get_parse_pool` vs `_PARSE_POOL` 命名混乱
- **旧代码**: `def _get_parse_pool(): return _PARSE_POOL` + `_PARSE_POOL = None` + manual lock
- **新代码**: `_PARSE_POOL = Lazy(_make_parse_pool)` (Lazy wrapper)
- 错配: line 130 `loop.run_in_executor(_get_parse_pool(), ...)` —— `_get_parse_pool` 已被删 → `NameError`

**修复**: `loop.run_in_executor(_PARSE_POOL.get(), ...)`

**Bug C**：`ensure_raw_exists` 4h 缓存窗口**自我锁死**
- 缓存有效条件: `raw_path.exists() AND age < 4h AND item_count >= 50`
- 首次 fetch 因 A+B 双 bug 返回 0 items → 写 0 item raw 到 cache
- 后续 4h 内: `item_count = 0 < 50` → **触发** `log.warning("low quality, forcing refresh")` — **但**这分支没 `cache_valid = False`，下次仍走 refresh
- 等等，上面其实有。重新看：

```python
if item_count < 50:
    log.warning(f"raw_{today}.json low quality ({item_count} items < 50), forcing refresh")
else:
    cache_valid = True
```

- `if < 50` 分支没设 `cache_valid = False` (实际是隐含默认 False)。**第一次 fetch 返 0 → cache_valid=False → 重 fetch → 仍返 0**。**2-3 次后把 0 写到 cache**。**注意**：默认 `cache_valid = False` 在函数顶设了，但**前提**是 raw 文件已存在。如果 raw 不存在，**默认 False + 直接 fetch**。所以 fresh start OK。**问题在 cron 每小时都跑 + 第一次 fetch 偶尔返 0（瞬时网络问题）+ cache 锁死 4h**。

**修复**（加强 robust）：把 `< 50` 当作 `cache_valid = False` 显式赋值并 log 警告：
```python
if item_count < 50:
    log.warning(f"raw_{today}.json low quality ({item_count} < 50), forcing refresh")
    cache_valid = False  # 显式（防御性，原来依赖 default）
else:
    cache_valid = True
```

**铁律**：任何 cache_valid 分支必须**显式**赋值，不能依赖 default。

## Pipeline 性能基线（2026-06-03 实测, 30 条精选）

| 阶段 | Warm (raw cache HIT) | Cold (cache MISS) | 占比 warm | 优化点 |
|------|:---:|:---:|------|--------|
| **push_prepare** (fetch + curate) | 1.9-2.1s | **17.2s** | 19-20% | warm 已最优；cold 受限于 43 源网络并发 + 5 源重试 |
| **ai_translate** (5 外媒 + N 扩写) | 7.5-7.8s | 7.0s | 72% | **最大瓶颈** — 5 条外媒翻译串行 + 扩写串行 |
| render_markdown | 0.002s | 0.002s | 0% | 已 < 10ms，无需优化 |
| fragment_push | 0s | 0s | 0% | byte-aware split，纯字符串 |
| record_fingerprints | 0.01s | 0.01s | 0% | SQLite 写 |
| **TOTAL** | **~10s** | **~24s** | 100% | cron 9/12/21 走 warm |

**优化建议（按 ROI 排序）**:

1. **ai_translate 7.5s** (最大瓶颈):
   - 当前 batch_size=5 串行 — 改 batch_size=10 + 多 batch 并发 (`TRANSLATE_BATCH_MAX_CONCURRENT` 已设 5)
   - 早/午/晚 slot 大多无外媒翻译需求 → early-skip 路径（`items_to_translate` 空时直接 return）
   - 缓存：相同 title 的扩写结果存 hash 表，30 天内 skip
   - 用更快模型（Haiku/Gemini Flash）做中文短摘要扩写

2. **fetch 1.9s**: 已 43 源并发，3 源失败可加 retry+fallback（机核/澎湃/界面 RSS 偶发 5xx）

3. **总目标**: 10s → 6s（ai_translate 砍半）

**基准测试命令**:
```bash
cd /home/asus/.hermes/trendradar
for i in 1 2 3; do
  rm -f cache/raw_*.json data/curated_morning_*.json
  T0=$(date +%s%N)
  PYTHON_GIL=0 PYTHONPATH=/home/asus/.hermes /usr/local/bin/python3.14t \
    trendradar/scripts/pipeline_orchestrator.py --push-id morning 2>&1 \
    | grep -E '✅|总|fetch 完成' | head -5
  T1=$(date +%s%N)
  /usr/local/bin/python3.14t -c "print(f'TOTAL: {($T1 - $T0) / 1e9:.2f}s')"
done
```

## PYTHONPATH 陷阱：import 死锁

**注意**: `PYTHONPATH=/home/asus/.hermes` 能让 `import trendradar` 找到包，但**在 pytest 环境下会导致 import 死锁**。
`~/.hermes/trendradar/__init__.py` 存在的情况下，Python 在顶层包解析时会与 conftest.py 的 `sys.path.insert` 冲突，`test_push_prepare.py` 在 import 阶段无限阻塞。

**排查**:
```bash
timeout 10 python -c "from push_prepare import count_new_items"  # import 就挂
```

**修复**:
- 运行测试时：`PYTHONPATH=/home/asus/.hermes/trendradar`（父目录不含 trendradar 包即可）
- 生产运行时：`PYTHONPATH=/home/asus/.hermes` 仍可安全使用（仅 pytest + conftest 并发时触发死锁）
- 维护脚本已内置自适应：设 `PYTHONPATH=TRENDRADAR_HOME`（即 `~/.hermes/trendradar/`），`cwd` 自动检测嵌套包目录

## domain_metadata RLock 陷阱（2026-06-02 发现）

`scripts/domain_metadata.py` 用 `threading.Lock()` 保护模块级 lazy-init 缓存（`_config`/`_sources`/`_foreign_sources`/`_china_kw` 等）。**`Lock()` 不可重入**——但 `_foreign_sources()` 首次调用时会**在自身持锁状态下**调 `_sources()`，`_sources()` 内部也 `with _INIT_LOCK`，同一线程二次 acquire 永远阻塞。

**症状**（非常微妙）:
- `classify_items()` 卡 40s+，0% CPU，`wchan=futex_wait_queue`
- 进程无子线程，**不是 GIL 也不是死锁的传统形态**——是单线程自递归锁等待
- 调试时 `cat /proc/<pid>/wchan` 显示 `futex_wait_queue`、ps 显示 `Sl` 状态无 child
- **`faulthandler` + `SIGALRM` 触发 dump_traceback 才能定位**（见 `references/hung-process-diagnosis.md`）

**为什么 cron 跑通而手动跑挂**（关键洞察）:
- cron agent 调 pipeline 顺序：fetch → curate → batch_fetch
- fetch 阶段 fetch_feeds.py 会先调 `_sources()`（只触发 `_INIT_LOCK` 一次），`get_data_dir()` 等 sentinel 全部赋值
- 后续 curate 阶段调 `_foreign_sources()` → `_sources()` 走 fast path（`if _SOURCES_VAL is not None: return`）不 acquire lock
- **手动跑**（特别是 `python3 -c '...'` 单文件 import）**直接调 classify 不经过 fetch**，**首次**进入 `_foreign_sources()` → `_sources()` 死锁

**修复**: `threading.Lock()` → `threading.RLock()`（可重入）。Sentine 检查的双重检查模式 + RLock 是正确组合：同一线程可重入，跨线程仍互斥。

**铁律**: 任何 `with _INIT_LOCK:` 块里调用的同级函数（如 `_sources()` 在 `_foreign_sources()` 内被调）都可能触发 re-acquire。新增 lazy-init 互调函数时**默认 RLock**。

**手动验证脚本**（复现 + 验证修复）:
```python
import time, faulthandler, signal
faulthandler.enable()
def dump(sig, frame): faulthandler.dump_traceback(); raise SystemExit(1)
signal.signal(signal.SIGALRM, dump)
signal.alarm(15)  # 15s 后自动 dump stack

from trendradar.scripts.classifier import classify_items
import json
from pathlib import Path
raw = json.loads(Path('~/.hermes/trendradar/cache/raw_<DATE>.json').expanduser().read_text())['items']
hl, rem, fc = classify_items(raw)
print(f'hl={len(hl)} rem={len(rem)} fc={len(fc)}')  # 修复后 <1s
```

## 手动测试 vs cron 调用的环境差异协议

手动跑 pipeline 时**不能假设和 cron 行为一致**。关键差异：

| 维度 | cron (LLM agent 调 terminal) | 手动（本会话 `env -i` 跑） |
|------|------------------------------|---------------------------|
| Python 解释器 | `python3.14t`（free-threaded）| `/usr/bin/python3`（看怎么调）|
| DEEPSEEK_API_KEY | gateway systemd 注入 | **未注入** → ai_translate 优雅降级（不阻断）|
| TRENDRADAR_HOME | cron prompt 设（内层 `~/.hermes/trendradar/trendradar/`）| **必须显式 export** |
| DEEPSEEK_MODEL | gateway 注入 `deepseek-v4-flash` | **必须显式 export**（否则日文条目原文残留）|
| 父进程 env 污染 | 无（LLM agent env 干净）| bash wrapper 大量变量（HTTP_PROXY 等）|
| PYTHON_GIL | 永远不设 | **永远不设**（3.14t 不支持）|

**手动跑全管线的正确姿势**（`env -i` 干净环境）:
```bash
cd /home/asus/.hermes/trendradar/trendradar
env -i HOME=/home/asus USER=asus \
  PATH=/usr/local/bin:/usr/bin:/bin TERM=xterm \
  PYTHONPATH=/home/asus/.hermes/trendradar \
  TRENDRADAR_HOME=/home/asus/.hermes/trendradar/trendradar \
  DEEPSEEK_MODEL=deepseek-v4-flash \
  /usr/bin/python3 -u scripts/pipeline_orchestrator.py --push-id noon
```

**为什么用 `python3` 不是 `python3.14t`**: 手动跑 = 调试模式，要 fast feedback。`python3.14t` + ahocorasick 在某些 lazy-init 路径会触发上面 RLock 陷阱，**manual 调试一定要先排除这个变量**。

## API Key 加载陷阱（2026-06-02 实战）

`config/api.py::get_api_key()` 的查找顺序（L30-46）：
1. `os.environ.get(API_KEY_ENV)` — **最先查环境变量**（如果设了就直接返回）
2. `$TRENDRADAR_HOME/.env` — 默认 `~/.hermes/trendradar/.env`
3. `~/.hermes/.env` — Hermes Agent 共享 env

**常见坑**（实测三种，2026-06-02）：

### 坑 1：手动 `export DEEPSEEK_API_KEY=*** bug
**症状**：日志 `Your api key: *** is invalid`（值是 3 个星号字面量，不是真 key）
**根因**：从 secrets 文件复制时把脱敏占位符当成了真值
**修复**：
```bash
# ❌ 错
export DEEPSEEK_API_KEY=***
# ✅ 对
set -a && source ~/.hermes/.env && set +a
# 或显式
export DEEPSEEK_API_KEY=$(grep '^DEEPSEEK_API_KEY=' ~/.hermes/.env | cut -d= -f2- | tr -d '"')
```

### 坑 2：cron 副本 `.env` 覆盖真值
**症状**：source 真 env 后 `python -c "import os; print(os.environ['DEEPSEEK_API_KEY'][:8])"` 显示 `sk-bd908...`，但 ai_translate 报 401 "Your api key: *** is invalid"
**根因**：`~/.hermes/trendradar/.env` 里的 key 是占位符 `*** 优先级 #2），os.environ 里真 key 优先级 #1 应当先匹配。**但如果** cron 启动时 LLM agent env 已被 gateway 注入了空值 `DEEPSEEK_API_KEY=""` → `os.environ.get` 返回空串 → 走 .env fallback → 拿到占位符
**修复**：
1. 删除/修复占位符文件：`echo "DEEPSEEK_API_KEY=$(grep '^DEEPSEEK_API_KEY=' ~/.hermes/.env | cut -d= -f2- | tr -d '\"')" > ~/.hermes/trendradar/.env`
2. 或在 cron prompt 里显式 `unset DEEPSEEK_API_KEY` 后再 source

### 坑 3：双 export 覆盖
**症状**：source 后 key 正确，再 `export DEEPSEEK_API_KEY=*** 次 export 覆盖
**根因**：复制粘贴时 `export DEEPSEEK_API_KEY=***`

**排查命令**（一次性诊断所有 401 假阳性）:
```bash
# 1. 验 key 实际值
python3 -c "import os; k=os.environ.get('DEEPSEEK_API_KEY',''); print(f'prefix={k[:8]} len={len(k)}')"
# 期望: prefix=sk-xxx len=35 (DeepSeek key 都是 35 字符)
# 异常: prefix=*** len=3 → 坑 1/3；len=0 → 坑 2

# 2. 直接打 API 验证 key 可用
python3 -c "
import os, urllib.request, json
req = urllib.request.Request('https://api.deepseek.com/v1/chat/completions',
  data=json.dumps({'model':'deepseek-v4-flash','messages':[{'role':'user','content':'hi'}],'max_tokens':5}).encode(),
  headers={'Authorization':f'Bearer {os.environ[\"DEEPSEEK_API_KEY\"]}','Content-Type':'application/json'})
r = urllib.request.urlopen(req, timeout=15)
print('HTTP', r.status, r.read()[:200])
"
# 期望: HTTP 200 ...；异常: HTTP 401 → key 失效需重新申请

# 3. 看 ai_translate 实际拿到什么
strace -f -e openat python3 -m trendradar.scripts.ai_translate --push-id noon 2>&1 | grep -E "\.env|api"
# 看它 open 哪些 env 文件
```

## 投递脚本（v6.6 no_agent 接管）

`slot_direct_push`（`~/.hermes/scripts/slot_direct_push.py` + `slot_direct_push_wrapper.py`）是 2026-06-02 引入的 no_agent cron 任务，从 LLM agent 手中接管分片投递：

```
cron `2 9,12,21 * * *`  ─→  slot_direct_push (no_agent, schedule-bound)
                                 │
                                 ├── _already_delivered(date, slot)  # 命中 marker → SKIP
                                 ├── archive 头部扫 _strip_preamble_from_head()  # 剥离 "以下是..." 前言
                                 ├── split_fragments(content)
                                 ├── 逐片 hermes send
                                 └── 写 delivered_{date}_{slot}.marker
```

**关键设计原则**：5 层防护确保 LLM 行为不再控制投递可靠性——工具物理上不可用（`messaging` toolset 已从日报 cron 移除）+ 脚本权威控制 + 自我修复 archive + 水印去重 + 严格 final response 单行模板。

详见 `news-secretary` SKILL "投递协议 v6.6" 章节。

### delivery_watchdog 真实投递通路：`hermes send -t wecom:bl --file`（2026-06-09 实战确认）

`delivery_watchdog.py` 检查各项指标后通过**调自身内部的 `send_to_wecom()` 函数**来补发——它不直接走 IPC socket（那是只读健康探针）。函数签名：

```python
def send_to_wecom(file_path: str | Path, subject: str | None = None) -> bool:
    cmd = ['hermes', 'send', '--to', 'wecom:bl', '--file', str(file_path)]
    # 注意：chat_id='bl' 是**硬编码**到脚本里的 wecom AI bot internal alias
```

`_send_from_archive()` 调 `split_fragments(content)` 把 archive `.md` 拆成 ≤4KB WeCom 片段，逐片 `hermes send --to wecom:bl --file<tmp.md>`，全部 return 0 才算投递成功。

**手动补推完整协议**（cron 没跑 / silent 失败 / archive 已有但 marker 没写）：

```bash
# 1. 确认 archive 存在且有内容
ARCH="$TRENDRADAR_HOME/archive/$(date +%Y-%m-%d)/evening.md"
[ -f "$ARCH" ] && wc -c "$ARCH"

# 2. 分片并逐片 hermes send（不要直接发整个 .md，超 4KB WeCom 截断）
PY="$HERMES_HOME/hermes-agent/venv/Scripts/python.exe"
PYTHONPATH="$TRENDRADAR_HOME" "$PY" -c "
from trendradar.scripts.fragment_push import split_fragments
content = open(r'$ARCH', encoding='utf-8').read()
for i, frag in enumerate(split_fragments(content)):
    print(f'fragment {i+1}: {len(frag)} chars')
    import subprocess
    r = subprocess.run(['hermes','send','--to','wecom:bl'], input=frag,
                       capture_output=True, text=True, timeout=30)
    print(f'  → exit={r.returncode} {r.stdout.strip()[:80]}')
"

# 3. 写交付 marker（与 auto-delivery 命名格式一致才能被 is_delivered() 找到）
echo "$(date -Iseconds)" > "$TRENDRADAR_HOME/data/delivery_markers/delivered_$(date +%Y%m%d)_evening.marker"

# 4. 验证（重跑 delivery_watchdog 应 silent，不再补发）
PYTHONPATH="$TRENDRADAR_HOME" "$PY" "$HERMES_HOME/scripts/delivery_watchdog.py"
```

### ⚠️ `_write_marker` 命名格式修复（2026-06-09 实战 bug）

`delivery_watchdog.py:_write_marker()` 历史 bug：写 marker 时用 `{today}_{push_id}.marker`（如 `2026-06-09_evening.marker`），但 `mark_delivered(run_id)` 和 `is_delivered(run_id)` 用 `delivered_{run_id}.marker`（如 `delivered_20260609_evening_<hash>.marker`）。**两个命名不一致 → 自动补发永远命中"未投递" → 重复推送**。

**修复**（commit in 2026-06-09 patch）：
```python
# ❌ 错
marker_path = MARKER_DIR / f'{today}_{push_id}.marker'
# ✅ 对（与 mark_delivered 一致）
run_id = f'{today.replace("-", "")}_{push_id}'
marker_path = MARKER_DIR / f'delivered_{run_id}.marker'
```

**铁律**：任何补投后**必须**用 `delivered_<YYYYMMDD>_<slot>.marker` 命名，否则下次 cron 会重发同一份简报。

### delivery_watchdog.py Windows 兼容性 4 个 bug（2026-06-09 实战 + patch）

`hermes-scripts/delivery_watchdog.py` 在 Windows 上有 4 个**只在 Linux 测试过**的 bug：

| Bug | 症状 | 修复 |
|-----|------|-----|
| 1. `HERMES_HOME = os.path.expanduser("~/.hermes")` | 解析为 `C:\Users\<user>\.hermes\`（不存在），所有依赖 HERMES_HOME 的子检查错位 | 用 `_resolve_hermes_home()` helper：env > `hermes_constants.get_hermes_home()` API > Linux fallback |
| 2. `TRENDRADAR_HOME` 默认 `Path.home() / '.hermes' / 'trendradar'` | 同上错位 | `_resolve_trendradar_home()` helper：`HERMES_HOME / 'trendradar'` |
| 3. `PYTHON` 默认 `/usr/local/bin/python3.14t` | Windows 上不存在，subprocess 调不到 python | 自动探测 `HERMES_HOME/hermes-agent/venv/Scripts/python.exe` (Win) 或 `.../bin/python` (Linux) |
| 4. `check_socket()` 只查 `/tmp/*.sock` Linux unix-domain socket | 永远报 "WeCom IPC socket 不可达" | 加 Windows TCP probe：`127.0.0.1:{8765,8000,8888,7777}/health` 探测 gateway HTTP health |
| 5. `get_cron_jobs()` 用 `env={**os.environ, "HERMES_HOME": HERMES_HOME, ...}` 但 `HERMES_HOME` 是 `Path` 对象 | Windows CreateProcess 报 `TypeError: environment can only contain strings` | 显式 `{k: str(v) if not isinstance(v, str) else v for k, v in os.environ.items()}` + `str(HERMES_HOME)` |

**诊断**（任何 no_agent cron 跑挂 + gateway log 显示 "TypeError" 或 "socket 不可达"）：
```bash
python "$HERMES_HOME/scripts/delivery_watchdog.py"
# 期望: exit=0，可能有 WeCom socket 不可达告警（无害）但不应有 TypeError
```

**修复后预期行为**：`HERMES_HOME`、`TRENDRADAR_HOME`、`PYTHON` 路径解析正确（`hermes-scripts/delivery_watchdog.py:21-71`）+ socket check 包含 Windows HTTP probe + `get_cron_jobs()` 不再 crash。

### ⚠️ grep 转义陷阱：MSYS bash `\|` 不工作（2026-06-09 实战）

**症状**：`.env` 里**确实**有 `WECOM_HOME_CHANNEL=bl`（python 读取可见），但 `grep "WECOM_HOME\|bl" .env` 找不到：

```bash
grep "WECOM_HOME\|bl" "$HERMES_HOME/.env"
# → 只 grep 到带 'bl' 的注释行，'WECOM_HOME_CHANNEL=bl' 那行漏掉
# 原因：MSYS grep 把 \| 当字面量，不是 "or"
```

**修复**：
```bash
# ✅ 用 -E + 显式 |
grep -E 'WECOM_HOME_CHANNEL|^\s*WECOM_' "$HERMES_HOME/.env"

# ✅ 或两个 grep 用 pipe
grep 'WECOM_HOME' "$HERMES_HOME/.env" || grep -c 'bl' "$HERMES_HOME/.env"

# ✅ 最稳：直接 python 读
python -c "import os; from pathlib import Path; \
  txt = Path(os.environ['LOCALAPPDATA'] + r'\hermes\.env').read_text(encoding='utf-8'); \
  [print(l) for l in txt.splitlines() if l.startswith('WECOM_')]"
```

**铁律**：在 MSYS bash 下验证 `.env` 写入是否生效，**用 python 读**而不是 grep。

## 仓库推送范围（2026-06-02 仓库清理发现）

**原则**：**只保留必要配置文件 + 运行时，**运行积累的数据不要同步**到 GitHub。本地数据保留（不删），只是不推。

**.gitignore 路径错位陷阱（2026-06-02 教训）**：
- 旧 `.gitignore` 写 `trendradar/data/`（内层路径），但实际仓库根有外层 `data/`、`archive/`、`cache/`、`logs/`——这些规则覆盖不到
- 后果：37 个运行数据文件被误跟踪（archive 简报 9 个 + cache 缓存 7 个 + data curated 10 个 + delivery_markers 6 个 + fingerprints db 2 个 + sources.json 1 个 + 等等）

**正确 .gitignore 规则**（commit 9a70751，仓库已合规）：

```gitignore
# 双层 data 目录都忽略（外层 = TRENDRADAR_HOME/data/，内层 git 跟踪的副本）
data/
cache/
archive/
logs/
output/
mail_queue/
*.db
*.db.backup
*.json.zst
*.marker

# Secrets
.env
trendradar/.env
```

**untrack 已跟踪数据文件**（不删本地，保留运行数据）：
```bash
cd ~/.hermes/trendradar
# 列出待 untrack
git ls-files | grep -E "(^archive/|^data/|^cache/|^logs/|\.db$|\.db\.backup$|\.json\.zst$|\.marker$)"
# untrack（保留本地）
git rm -r --cached -- <files>
# 验证本地数据没动
ls -la data/curated_evening.json data/fingerprints.db archive/2026-06-02/evening.md
# commit + push
git commit -m "chore: untrack 数据/缓存/存档 + 完善 .gitignore"
```

**推送范围铁律**：
| 必须 tracked | 不该 tracked |
|--------------|--------------|
| `trendradar/config/` 全部 (sources.json, ai_interests.yaml, timeline.yaml, keywords.py, translation.py, domains.py) | `data/curated_*.json` 每日精选 |
| `trendradar/scripts/` 全部 | `cache/raw_*.json` `cache/batch_*.json.zst` |
| `trendradar/migrations/` 全部 | `archive/2026-*-*/*.md` 投递存档 |
| `trendradar/skills/` 全部 | `data/fingerprints.db` + `.backup` |
| `hermes-scripts/` 全部 | `data/delivery_markers/*.marker` |
| `references/` 全部 | `logs/` 运行日志 |
| `tests/` 全部 | `output/` `mail_queue/` |
| `README.md` `SETUP.md` `ARCHITECTURE.md` `PIPELINE.md` `TRAPS.md` | `.env` `*.swp` `.DS_Store` |
| `.gitignore` | `data/sources.json`（外层历史残留，代码用内层 `trendradar/config/sources.json`） |

**健康检查**：untrack 后 `git ls-files` 应只 129 个文件（之前 166），多 37 个都是数据/缓存/存档。

## 双 data 目录陷阱（2026-06-02 发现）

TrendRadar 实际有**两个 data 目录**：
- **外层**（生产/cron 用）: `~/.hermes/trendradar/data/` ← `ai_translate.py` / `pipeline_orchestrator.py` 实际读这个（DATA_DIR 默认 `TRENDRADAR_HOME/../data`）
- **内层**（git 跟踪）: `~/.hermes/trendradar/trendradar/data/` ← `git diff` / `git commit` 跟踪这个

`config/` 和 `scripts/` 是 symlink（`config → trendradar/config`、`scripts → trendradar/scripts`），但 `data/` 不是 symlink —— 两边独立。

**症状**：手动跑 `python3 trendradar/scripts/ai_translate.py` 改完 `trendradar/data/curated_*.json`，结果脚本读的是外层（外层没改），看到 0 任务 / 找不到 curated。`md5sum` 比对两目录才发现自己改错地方。

**排查**：
```bash
# 看 ai_translate 实际用的 DATA_DIR
python3 -c "from trendradar.scripts.file_utils import get_data_dir; print(get_data_dir())"
# → /home/asus/.hermes/trendradar/data/   ← 注意：外层，不是内层
```

**铁律**：
1. 手动改 curated JSON **必须改外层** `~/.hermes/trendradar/data/`
2. git commit 之前如果想让 prod 看到内层变更 → `cp` 外层到内层（反之亦然）
3. 改完后 `md5sum` 比对两目录确认一致

## LLM Provider 解耦

2026-06-01 `ai_translate.py` 改用 `llm_providers.py` 的可插拔 provider 架构。**切换 provider 不需改代码**——只设环境变量：

```bash
# Claude
TRENDRADAR_LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=*** TRENDRADAR_LLM_MODEL=claude-3-5-sonnet-20241022

# Gemini
TRENDRADAR_LLM_PROVIDER=google_genai GOOGLE_API_KEY=*** TRENDRADAR_LLM_MODEL=gemini-1.5-flash

# 本地 Ollama
TRENDRADAR_LLM_PROVIDER=ollama TRENDRADAR_LLM_MODEL=llama3.1 TRENDRADAR_LLM_ENDPOINT=http://localhost:11434
```

`DEEPSEEK_*` 环境变量仍可工作（默认 `openai_chat` provider，智能 endpoint 检测），向后兼容。

## gen_cron_prompt.py 引号陷阱

`scripts/gen_cron_prompt.py` 用 f-string 拼接 bash 内容写入 `lines.append()`，双引号嵌套容易写出 `f"export PYTHON=\"{PYTHON}\""` 这类运行时 SyntaxError 的代码。原因是 f-string 中外层 `"` 与内层 `\"` 在 Python 解析器眼中是同一个引号字符的转义序列，Python 3.12+ 的 fstring 解析器会提前闭合外层引号。

**修复模式**: 用单引号 `'` 包裹 f-string 外层：
```python
# ❌ 会报 SyntaxError
lines.append(f"export PYTHON=\"{PYTHON}\"")
# ✅ 正确
lines.append(f'export PYTHON={PYTHON}')
```

`gen_cron_prompt.py` 2026-05-29 前长期处于语法错误状态（从未真正跑通过），修复后需手动 regenerate：`python3 hermes-scripts/gen_cron_prompt.py`。

## ⚠️ gen_cron_prompt.py PYTHONPATH=.parent 错位 bug（2026-06-09 实测，跨平台陷阱）

**问题**：`gen_cron_prompt.py:35` 原本写 `PYTHONPATH = str(HERMES_HOME)`（=`TRENDRADAR_HOME.parent`），在 Linux 上 work，因为 `~/.hermes/trendradar/<pkg>/` 时 parent `~/.hermes/` 包含 `trendradar/` 子目录可被 namespace package 解析。但在 **Windows** 上 parent 是 `%LOCALAPPDATA%\hermes\`（**没有** `trendradar/` 子目录在 parent 里，因为 `trendradar/` 整个就是父目录本身），`import trendradar.scripts.common` 直接 `ModuleNotFoundError`。

**症状**：在 Windows 跑 `gen_cron_prompt.py`（用于生成 cron prompt SSOT）：
```
ModuleNotFoundError: No module named 'trendradar'
```
无论 `PYTHONPATH` 怎么设都报——因为脚本内部硬覆盖成 `.parent`。

**修复**（2026-06-09 patch 到 `gen_cron_prompt.py:35`）：
```python
# ❌ 错（Windows 上找不到 trendradar 包）
PYTHONPATH = str(HERMES_HOME)  # = TRENDRADAR_HOME.parent

# ✅ 对
PYTHONPATH = str(TRENDRADAR_HOME)  # = parent/trendradar/，包路径在这里
```

**铁律**：
- **任何 `scripts/*.py` 在 Windows 上找不到 `trendradar` 包** → 立即怀疑 `PYTHONPATH=.parent`（而不是 `.self`）
- `gen_cron_prompt.py` 是定时 prompt 的 SSOT 生成器，跑不通 = 整个 cron prompt SSOT 流水线断
- 修复后必须手动验证：`TRENDRADAR_HOME=$HERMES_HOME/trendradar PYTHONPATH=$HERMES_HOME/trendradar python3 hermes-scripts/gen_cron_prompt.py > references/cron-prompt-generated.md`（**两个变量都用 `$TRENDRADAR_HOME` 而不是 `$HERMES_HOME`**）

**为什么之前的 `scripts_sync.sh` / `system-config` 都没列出这个 bug**：原 SKILL 假设运行环境是 Linux，namespace package 在 Windows 上解析行为不同。Windows 上 `~/.hermes/trendradar/`（=TRENDRADAR_HOME）整个就是一个目录，包路径必须在 TR 内部 `trendradar/trendradar/`（嵌套），不是 TR.parent。

**诊断命令**：
```bash
python -c "
import sys
sys.path.insert(0, r'$HERMES_HOME/trendradar')  # 必须是 TR 自身，不是 parent
import trendradar.scripts.common
print('OK')
"
# Windows 上：parent 写法 = ModuleNotFoundError；self 写法 = OK
```
## 全量同步协议（两副本 → Git）

TrendRadar 有三处副本：(1) `~/.hermes/trendradar/trendradar/` — cron 运行时，(2) `~/TrendRadar/trendradar/` — Git 工作树，(3) GitHub 远程。`skill_manage`/`skill_view` 操作的是 (1) cron 副本，但 Git 跟踪的是 (2) 工作树。以下为全量同步 checklist。

### ⚠️ 注意：两 git 仓库可能分叉（2026-06-02 发现）

`~/.hermes/trendradar/` 和 `~/TrendRadar/` **是两个独立 git 仓库**（不是 worktree），都 push 到同一个 origin。**HEAD 可能不一致**：
- `~/.hermes/trendradar/`：v6.x source of truth（active）
- `~/TrendRadar/`：stale v5.7.0 工作树（保留为发布仓，但可能落后几个版本）

**诊断**：
```bash
cd ~/.hermes/trendradar && git log --oneline -3 origin/main  # 看实际 origin 状态
cd ~/TrendRadar && git log --oneline -3 origin/main           # 对比
```

**铁律**：
- 提交代码改动 → `~/.hermes/trendradar/`（active 仓库）
- 跨仓库操作（PR review、release tag）→ 在 `~/TrendRadar/` 做（但要先 `git fetch` + `git reset --hard origin/main` 同步）
- 不要在两个仓库同时 commit，merge 复杂度爆炸

### 同步范围（6 个区域）

| # | 区域 | 方向 | 典型差异判定 |
|---|------|------|------------|
| 1 | **skills/** (SKILL.md + references/ + scripts/) | cron → 工作树 | `diff -rq ~/.hermes/skills/trendradar/ ~/TrendRadar/trendradar/skills/ \| grep -v __pycache__` |
| 2 | **scripts/** (.py 源文件) | cron → 工作树 | `diff -rq ~/.hermes/trendradar/scripts/ ~/TrendRadar/trendradar/scripts/ \| grep -v __pycache__` |
| 3 | **config/** (sources.json 等) | 双向验证 | 通常一致，用 `diff` 确认 |
| 4 | **references/** 顶层参考文档 | cron → 工作树 | `diff -rq ~/.hermes/trendradar/trendradar/references/ ~/TrendRadar/trendradar/references/` |
| 5 | **hermes-scripts/** (delivery_watchdog 等) | 工作树 → cron | `diff -q ~/TrendRadar/hermes-scripts/ ~/.hermes/scripts/` |
| 6 | **根文件** (.gitignore, README.md, SETUP.md, one-key-setup.sh, LICENSE) | cron → 工作树 | `for f in README.md SETUP.md one-key-setup.sh LICENSE .gitignore; do diff -q ~/.hermes/trendradar/$f ~/TrendRadar/$f; done` |

### 同步命令速查

```bash
# 1) Skills
cp -r ~/.hermes/skills/trendradar/<skill>/ ~/TrendRadar/trendradar/skills/<skill>/

# 2) Scripts
cp -r ~/.hermes/trendradar/scripts/*.py ~/TrendRadar/trendradar/scripts/

# 3) Config（验证用）
diff -rq ~/.hermes/trendradar/config/ ~/TrendRadar/trendradar/config/ | grep -v __pycache__

# 4) References
diff -rq ~/.hermes/trendradar/trendradar/references/ ~/TrendRadar/trendradar/references/

# 5) Hermes-scripts
diff -q ~/TrendRadar/hermes-scripts/ ~/.hermes/scripts/

# 6) 根文件
for f in README.md SETUP.md one-key-setup.sh LICENSE; do
  cp ~/.hermes/trendradar/$f ~/TrendRadar/$f
done
cp ~/.hermes/trendradar/.gitignore ~/TrendRadar/.gitignore
```

### 提交与推送

```bash
# Stage all（包括新增/删除/修改）
cd ~/.hermes/trendradar && git add -A

# 验证 staged 文件列表
git status --short

# 提交
git commit -m 'sync: 全量同步运行时→仓库 — <概要>'

# 推送（走代理，用 gh token 认证）
TOKEN=$(gh auth token)
GIT_TERMINAL_PROMPT=0 git -c credential.helper='' \
  push "https://<your-username>:${TOKEN}@github.com/<your-username>/<repo>.git" main

# 推送成功后刷新本地 remote-tracking 分支
git fetch origin main
git status  # 应显示 "up to date with 'origin/main'"
```

**注意**：代理推送成功后 `git status` 仍可能显示 "ahead by N commits"——`git push` 不会自动更新本地 remote-tracking 引用。必须 `git fetch origin main` 后 `git status` 才反映真实状态。

### 验证：同步完整性检查

提交前执行一次 diff 确认两端一致：
```bash
echo "=== Skills ==="
diff -rq ~/.hermes/skills/trendradar/ ~/TrendRadar/trendradar/skills/ 2>/dev/null | grep -v __pycache__
echo "=== Scripts ==="
diff -rq ~/.hermes/trendradar/scripts/ ~/TrendRadar/trendradar/scripts/ 2>/dev/null | grep -v __pycache__
echo "=== Root ==="
for f in README.md SETUP.md one-key-setup.sh LICENSE .gitignore; do
  diff -q ~/.hermes/trendradar/$f ~/TrendRadar/$f 2>/dev/null
done
```
任何非 `__pycache__` 的差异都需要处理后再提交。

### 常见陷阱

- **Skills 改完只推了 cron 副本**：`skill_manage` 操作的 `~/.hermes/skills/` 不会被 Git 跟踪。改技能必须显式 copy 到工作树。
- **忘 sync 根文件**：`README.md`/`SETUP.md` 等根文件在 `~/.hermes/trendradar/` 里改了但 `~/TrendRadar/` 的没同步，`git status` 不报差异（Git 只跟踪工作树），推送后 GitHub 仍然显示旧版。
- **Push 后 `git status` 还显示 "ahead"**：正常—— `git push` 不更新本地 remote ref，跑一下 `git fetch origin main` 即消除。
- **跨两 git 仓库误改**：在 `~/TrendRadar/` 改代码并提交，但 `~/.hermes/trendradar/` 没同步 → cron 跑的还是旧代码。**铁律**：cron active 仓库（`~/.hermes/trendradar/`）改了直接 commit，stale 仓库（`~/TrendRadar/`）改完必跑 `git fetch + reset --hard origin/main` 对齐。

## References 一致性维护

详见 `../../references/MAINTENANCE.md`。

## sources.json 位置陷阱

`sources.json` 是**配置文件**（非运行时数据），但在 v2.9.0 之前代码从 `data/sources.json` 读取。已通过 `get_config_dir()` 修复——三个消费者（`curate_and_push.py` / `ai_translate.py` / `fetch_feeds.py`）统一从 `config/sources.json` 读取。

**修复铁律**：配置文件走 `get_config_dir()`，运行时数据走 `get_data_dir()`。`file_utils.py` 提供了两个工厂函数，`settings.py` 统一 re-export。

**验证**：`grep "sources.json" trendradar/scripts/*.py` 应全部指向 `get_config_dir()` 或 `config/`。

## 三段式 sync_repo.sh协议（2026-06-10 新增，最简方案）

用户最终选择"最简方案"——不 cron、不轮询、不双副本。规则只记在 memory：每次我操作 trendradar 代码后**立即手动跑** `sync_repo.sh`。这是一条完整的"运行时 ↔ 本地仓库 ↔ GitHub"三段式同步链路。

### 三段式设计

```
[运行时] C:\Users\ASUS\AppData\Local\hermes\trendradar\
 ├─ scripts/ config/ hermes-scripts/ prompts/ trendradar/ ← 代码
 ├─ data/ cache/ archive/ logs/ .env *.db *.json.zst *.marker ←运行时数据（不同步）
 └─ (无 .git，被 cron 直接读写)
 │
 │ robocopy /MIR + exclude rules（EXCLUDES数组）
 ▼
[本地仓库] C:\Users\ASUS\AppData\Local\hermes\repo trendradar\（带空格）
 ├─ .git（独立 inode，独立 .git/objects，跟运行时 .git 不同）
 ├─ 代码 =运行时镜像（robocopy同步后）
 ├─ sync_repo.sh（手动入口）
 ├─ sync_files.py（robocopy 的 Python wrapper，处理 Windows 上没有 rsync 的问题）
 └─ .sync_state/{last_sync.txt,last_commit.txt}（状态记录）
 │
 │ git add -A → commit "auto-sync: <ts> | N files | ..." → push --dry-run → 真 push
 ▼
[GitHub] https://github.com/BedrockLian/TrendRadar.git (remote: origin)
```

###关键设计选择

1. **本地仓库放 `repo trendradar/`（带空格）而非 `TrendRadar/`**：Windows NTFS case-insensitive，`trendradar/` 和 `TrendRadar/` 是同一 inode。**必须用完全不同的名字**才能真正分离。用"带空格不同名"是 NTFS 大小写不敏感下唯一可靠的物理分离方案。
2. **`git clone --no-hardlinks`**：避免 `.git/objects` 被 hardlink 到运行时 `.git/objects`。验证两个 `.git/HEAD` inode 不同才算独立仓库。
3. **robocopy替代 rsync**：Windows 默认没 rsync；winget/choco 都装不到。`robocopy /MIR /XF /XD` 提供 rsync `--delete --exclude` 等价能力。exit code含义不同：0=no change,1=copied,2=deleted extras,3=both=success,8+=error。
4. **仓库级 git identity**：`TrendRadar Auto-Sync <autosync@bedrocklian.local>`（仓库 .git/config 设，不污染 global）。
5. **冲突保护 + 重试**：push 前 `git fetch origin` + 检测 `behind`（落后拒绝 push）。push失败重试3 次（30s/60s/120s退避），最终失败 WeCom报警。
6. **EXCLUDES数组**：与运行时 .gitignore 对齐——`__pycache__ *.pyc *.bak .broken *.swp data cache archive logs *.db *.db.backup *.json.zst *.marker .env .git`。

### sync_repo.sh5 种模式

| 命令 |作用 |何时用 |
|------|------|--------|
| `bash sync_repo.sh` | 全流程 sync + commit + push |日常：代码改完立即跑 |
| `bash sync_repo.sh --sync` | 只 robocopy 代码到本地仓库，不 commit 不 push |调试 robocopy exclude规则 |
| `bash sync_repo.sh --commit` | sync + commit，不 push |攒一批改动后单独 commit |
| `bash sync_repo.sh --push` | sync + commit + push |跳过 sync 直接 commit + push（信任 working tree已是最新） |
| `bash sync_repo.sh --dry-run` |全部 dry-run |第一次跑前必做，看会改什么 |
| `bash sync_repo.sh --status` | 看 last sync/commit 时间、git status、ahead/behind |排错 /确认上次同步成功 |

### cron 不化原则（用户偏好）

用户多次明确否决过度工程化方案：
- ❌ cron 自动 sync（"搞其他的太麻烦"）
- ❌5min/15min mtime polling（"搞其他的太麻烦"）
- ❌ push失败立即报警（"等用户提醒太晚，我自己每次代码改动后立即跑"）

最终规则只记在 memory，agent 自己每次操作 trendradar 代码后立即手动跑 sync_repo.sh。这是用户偏好的"一切从简"原则的具体表现。

###已知坑(2026-06-10 实踩)

1. **`cp "$RUNTIME/$f" "$REPO/$f"2>&1`**实际创建 `$REPO/<f>2` 文件(MSYS 把 `2>&1`合并到 `<f>`后面)。修复:raw bytes替换 `"$REPO/$f"2>&1` → `"$REPO/$f"2>&1`。
2. **`git config --list`报 `unknown option --list2`**:`2>&1` 后缀被吞。修复:分两次调用或 `git config --list | grep ...`。
3. **`.md2` `.sh2` 等假文件被 git add 进 index**:cp bug残留。修复:`git rm --cached *.md2 *.sh2`。
4. **`.broken` 文件没排除**:第一次 sync 把 `scripts/blog_watcher_bridge.py.broken` 等加进了 commit。修复:EXCLUDES 加 `*.broken`。已 commit 的留着,不影响功能。
5. **CRLF/LF warning**:git警告 `LF will be replaced by CRLF`——Windows 默认换行处理,噪音但无害。
6. **git author identity第一次没配**:cron-style 自动 commit 需要仓库级 `git config user.name/user.email`,否则 `Author identity unknown`拒绝 commit。

### ⚠️ 从 git拉回的脚本本身可能含 MSYS bug(2026-06-10 实测)

**陷阱**:即使 `bash -n <script>` SYNTAX_OK(因为 `exit0` / `FILE"]` 被 bash接受为变量名或 fast path),**运行时**仍报:

- `[: missing ']'` — `[ -f "$LAST_SYNC_FILE"]` (引号后没空格)
- `/dev/null2: Permission denied` — `> /dev/null2>&1`(没空格)
- `exit0: command not found` — `exit0` 被拍成 `exit0`
- `for i in123` 而不是 `for i in123` —数字被拍一起

**根因**:当初 `write_file` / heredoc / `execute_code` 把 bash脚本写到 `.sh` 文件时,二级行缩进被拍平,而 `2>&1`前的空格也被吞。这些 bug **跟着 git commit 进入历史**。

**修复协议**(任何 `git show <sha>:<file> > /path`恢复脚本必做):

```python
# 用 raw bytes 处理(不走 bash,避免 MSYS重新折叠)
python -c "
import subprocess
data = subprocess.check_output(['git', '-C', '<repo>', 'show', '<sha>:<file>'])
sp = bytes([32]) # literal space byte
fixes = [
 (b'exit0', b'exit' + sp + b'0'),
 (b'exit1', b'exit' + sp + b'1'),
 (b'exit2', b'exit' + sp + b'2'),
 (b'exit3', b'exit' + sp + b'3'),
 (b'echo0', b'echo' + sp + b'0'),
 (b'for i in123', b'for i in' + sp + b'1' + sp + b'2' + sp + b'3'),
 (b'origin2>&1', b'origin' + sp + b'2>&1'),
 (b'main2>&1', b'main' + sp + b'2>&1'),
 (b'main2>/dev/null', b'main' + sp + b'2>/dev/null'),
 (b'/dev/null2>&1', b'/dev/null' + sp + b'2>&1'),
 (b'\"\$LAST_SYNC_FILE\"]', b'\"\$LAST_SYNC_FILE\"' + sp + b']'),
 (b'\"\$LAST_COMMIT_FILE\"]', b'\"\$LAST_COMMIT_FILE\"' + sp + b']'),
 (b'\"0\"]', b'\"0\"' + sp + b']'),
 (b'awk \"{print \\\\\"}\"', b'awk \"{print \\\\\$2}\"'),
]
for old, new in fixes:
 data = data.replace(old, new)
open('<output_path>', 'wb').write(data)
"
bash -n <output_path> && echo SYNTAX_OK
bash <output_path> --help #实际跑一次确认无 runtime error
```

**为什么 raw bytes 而非 `sed -i`**:所有 `terminal` / `sed -i` / `python -c "string"` 都通过 MSYS bash传字符串,二次触发 arg-merging bug。`bytes.replace`纯 Python 操作,**不走 bash**。

**为什么 `bash -n` 通过但运行时失败**:`exit0` / `FILE"]` 在 bash解析时是合法 token(把 `exit0` 当未定义命令 / `[ -f "FILE"]` 当 fast path 的 `]`缺失会兜底报错)。**只有运行时**才会实际执行并报错。

### ⚠️ `.gitignore`排除 +脚本依赖 =矛盾(2026-06-10 实测)

**陷阱**:`sync_repo.sh` 里写 `SYNC_HELPER="$REPO/sync_files.py"`(假设 sync_files.py 在仓库根),但用户要求把 `sync_files.py` 加进 `.gitignore`(从 GitHub排除)。**结果**:
- `sync_repo.sh`调 `python "$SYNC_HELPER" --mirror ...` → `can't open file '...sync_files.py'`(因为 sync_files.py 在 .gitignore列表里,robocopy EXCLUDES 也排除了,working tree 没有这个文件)
- git status 显示 `?? sync_files.py` 反向:`git rm --cached`之后文件 untracked,但 robocopy同步时 EXCLUDES 也排它,所以 working tree也没

**修复模式**:**`.gitignore`排除 sync机制产物 =必然修改脚本路径**:

```bash
#决策树:这个文件要被 .gitignore排除吗?
# 是 →脚本依赖它吗?
# 是 →改脚本指向绝对路径(外部 backup位置),不要依赖仓库 working tree
# 否 →没事,ignore就行

# 示例:sync_repo.sh + sync_files.py + .sync_state/全部 ignore
# →脚本移到 C:/Users/ASUS/trendradar-sync-tools/
# → SYNC_HELPER="C:/Users/ASUS/trendradar-sync-tools/sync_files.py"
# → STATE_DIR 也指向 external位置(或保持仓库 working tree,因为 EXCLUDES 也排它所以 working tree永远没这目录)
```

**铁律**:**ignore sync机制产物 + 把同步脚本 +状态文件都搬到仓库外部**(`$HOME/trendradar-sync-tools/`)。仓库里不保留 sync工具,只用 .gitignore列出"这是 sync机制的一部分,不该被跟踪"。

**反例**:把 `sync_repo.sh` 加进 `.gitignore` 但仍留在仓库根 — 下次 `sync_repo.sh --sync`跑时,`bash "$REPO/sync_repo.sh"`找不到文件(`rm -rf`删 working tree 后)。

### ⚠️首次 sync 后 cleanup 已误推的临时文件(2026-06-10 实测)

**陷阱**:第一次 `sync_repo.sh`跑下来 commit 里包含 `.broken` `.bak` 文件(因为 EXCLUDES数组首次跑时不全)。后续虽然 EXCLUDES 加了 `*.broken`,但**已 commit 的还在 git history 里**——下次 sync不会自动清。

**修复协议**(首次 sync 后或发现误推后跑一次):

```bash
cd "$HERMES_HOME/repo trendradar"
#1)找出所有误推的临时文件
git ls-files | grep -E '\.(broken|bak|orig|rej)$|\.md2$|\.sh2$'

#2) 从 index 删除(保留 working tree 文件)
git rm --cached <each_file>

#3) working tree 文件也删(运行时已经不留了)
rm -f <each_file>

#4) commit cleanup
git commit -m "chore: 从 GitHub排除临时文件 (.broken / .bak / *.md2 等)"

#5) push
git push origin main
```

**防患于未然**(`sync_repo.sh` EXCLUDES完整清单,2026-06-10确认):

```bash
EXCLUDES=(
 __pycache__ *.pyc *.bak .pytest_cache .git
 data cache archive logs output mail_queue
 .env .env.local
 *.db *.db.backup *.db-shm *.db-wal
 *.json.zst *.marker
 *.broken *.swp *.swo *.tmp
)
```

**铁律**:**首次 sync 后必跑 cleanup协议**——把误推的临时文件从 git history移除。如果已经推到 GitHub,需要 `git filter-repo` 重写历史(或接受历史里这些文件存在,但 working tree干净)。

###验证清单（每次 sync 后必跑）

- `bash sync_repo.sh --status` 看 last_sync/last_commit 时间戳 + ahead/behind
- `cd "$HERMES_HOME/repo trendradar" && git log --oneline -3` 看新 commit 是否落地
- `git remote -v`确认 origin = `https://github.com/BedrockLian/TrendRadar.git`
-浏览器看 GitHub `main` 分支是否有新 commit（push 后5-10s可见）

### 与现有 TrendRadar仓库协议的关系

|协议 | 来源 |状态 |
|------|------|------|
| `scripts_sync.sh`（内层 ↔ 外层 trendradar/config/scripts） | commit5c21d19 设计 |仍生效，不变 |
|仓库推送范围（"全量同步协议"） | system-config SKILL "全量同步协议"章节 |仍生效，但**更新**为"自动 sync"而非手动 cp |
| **`sync_repo.sh`（运行时 ↔ repo trendradar ↔ GitHub）** | **2026-06-10 新增** | **本次新增**，完全取代"全量同步协议"中的手动 cp步骤 |

未来用户在任何 cron agent / LLM跑完 trendradar 代码改动后，**应立即自动跑** `bash "$HERMES_HOME/repo trendradar/sync_repo.sh"`，不要等用户提醒。

###手动推送全链路工作流

当 cron 未触发或需要手动补推时，不走 `hermes cron run`（可能因工作目录/环境变量差异而静默失败），直接跑管线：

```bash
cd ~/.hermes/trendradar
cd ~/.hermes/trendradar
export TRENDRADAR_HOME=~/.hermes/trendradar/trendradar
export PYTHONPATH=~/.hermes/trendradar
export DEEPSEEK_MODEL=deepseek-v4-flash
unset PYTHON_GIL
python3 trendradar/scripts/pipeline_orchestrator.py --push-id noon

# 若渲染步骤崩了，单独补跑：
unset PYTHON_GIL && python3 trendradar/scripts/render_markdown.py --push-id noon
```

**关键**：
- **`unset PYTHON_GIL`** 必须显式执行（Python 3.14t 不支持 `PYTHON_GIL=0`，会 `config_read_gil: not supported by this build` 崩溃）。若当前 shell 继承了 cron gateway 注入的 `PYTHON_GIL=0`，跑前必须 unset。**注意**：`PYTHON_GIL=`（等号后空）写法在 bash 是**赋值**不是 unset，且 `export` 后等价于 `PYTHON_GIL=空字符串` 仍可能触发子进程崩溃（3.14t 把空值当作"禁用"处理）。**唯一安全做法**：`unset PYTHON_GIL` 显式取消。
- `TRENDRADAR_HOME` 指向内层 `trendradar/` 目录（含 `scripts/` 和 `data/`）
- **`DEEPSEEK_MODEL=deepseek-v4-flash` 必须设置** — 默认 `deepseek-chat` 处理日→中翻译时**必然返回原文不变**（不报错不告警），日文条目会全部以原文残留。Gateway override.conf 已注入此变量给 cron，但手动跑时不继承 gateway env，需要显式 export。详见 news-secretary SKILL 翻译管线第 5 条
- **如要在手动环境用 Claude/Gemini/Ollama**：先 `export TRENDRADAR_LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=***` 等，详见 news-secretary SKILL LLM Provider 解耦章节
- **API key 加载**：`set -a && source ~/.hermes/.env && set +a`（不要用 `export DEEPSEEK_API_KEY=***，详见上文 "API Key 加载陷阱"）

## Python 3.14t 依赖安装

free-threaded Python 的 pip 安装需要 `--break-system-packages`：
```bash
python3 -m pip install --break-system-packages feedparser aiohttp
```

## 路径陷阱：`__file__` 相对 ≠ 运行时数据路径

**错误模式**：
```python
# ❌ 仓库相对路径 — 运行时数据在 ~/.hermes/trendradar/data/，不在仓库目录
_SOURCES_PATH = Path(__file__).resolve().parent.parent / 'data' / 'sources.json'
```

**正确模式**：
```python
# ✅ 始终用 get_data_dir() 获取运行时数据路径
from trendradar.scripts.settings import get_data_dir
_SOURCES_PATH = get_data_dir() / 'sources.json'
```

仓库路径 (`~/TrendRadar/trendradar/`) 只存放源码和配置模板。运行时产出的数据 (`fingerprints.db`、`sources.json`、`curated_*.json` 等) 在 `~/.hermes/trendradar/data/`。

## 代码模式

SQLite 懒迁移、urllib 代理配置、原子文件写入等实现模式详见 `references/audit-fix-workflow.md` 和 `../../references/SETUP.md`。

## TrendRadar 技能

| 名称 | 用途 |
|------|------|
| news-secretary | 日报推送管线 + 质量评分 + 偏好收敛 |
| self-healing | 自动体检 + 自修复 |
| report-generator | 周报（每周一）+ 月报（每月1日）深度趋势研判 |

## 参考文件

> **入口**: `../../references/INDEX.md` — 全局索引（按功能分类），所有文档的唯一导航入口。

| 文件 | 内容 |
|------|------|
| `../../references/INDEX.md` | **全局索引**（首次查阅先读此文件） |
| `../../references/ARCHITECTURE.md` | 架构总览：分层设计、模块边界、数据流 |
| `../../references/PIPELINE.md` | 管线 v2.9.0 全量文档（数据流 Mermaid 图） |
| `references/pipeline-v2.9.md` | v2.9.0 架构变更：subprocess→direct call 细节 |
| `../../references/SETUP.md` | 统一搭建/安装/环境配置 |
| `../../references/TRAPS.md` | 已知陷阱全集 |
| `../../references/REPO-SYNC.md` | 三处同步 + 验证流程 |
| `../../references/MAINTENANCE.md` | References 一致性维护 + Skill 审计清单 |
| `../../references/DELIVERY-WATERMARK.md` | 投递水印机制：MarkerDir + delivery_watchdog + 手动标记 |
| `references/api-key-setup.md` | DeepSeek API Key 配置：Gateway 注入 + 权限陷阱（models≠chat/completions） |\n| `references/proxy-config.md` 的 **Gateway 级别代理** | Hermes web 工具代理配置：`HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` 注入 gateway systemd override.conf。**2026-05-27 日报 cron 超时根因**：直连中断但代理未配置，web_search/extract 全部超时 |
| `scripts/mihomo-update.py` | Mihomo 订阅更新脚本：下载base64订阅→按server:port匹配更新密码→保留名称→验证→重启。换订阅改 SUB_URL 后直接运行 |
| `scripts/tri_sync_verify.py` | **三副本一致性 + namespace shadow 检测** — `python3 scripts/tri_sync_verify.py <file.py>` 5 秒定位 "改完没生效" 问题 |
| `references/patch-tool-indent-bug.md` | **patch 工具缩进 bug 复现 + 修复**（`new_string` 多行带相同前导空格被无脑 dedent，py_compile 验证 + git 历史回滚） |
| `references/double-scripts-shadow-trap.md` | **双 `scripts/` 目录阴影陷阱** — namespace package 解析使外层 legacy `scripts/` 永远 shadow 嵌套 `trendradar/scripts/`，导致编辑嵌套目录不生效。5 秒诊断 + 3 选 1 修复（2026-06-03 早报空推送 debug 30+ 次定位） |
| `scripts/tri_sync_verify.py` | **三副本一致性 + namespace shadow 检测** — `python3 scripts/tri_sync_verify.py <file.py>` 5 秒定位 "改完没生效" 问题。**v2.1 (2026-06-06 修复)**: 原本硬编码的 `WORKTREE_SCRIPTS = Path(.../"scripts")` 是 str/str 除法，TypeError 让脚本启动就 crash。重写为 `_detect_worktree_scripts()` 探测式（`git worktree list` + 常见位置 fallback）。**无 worktree 的单副本安装也跑得通**（探测不到时该列报 MISSING 而非整脚本炸） |
| `references/perf-tuning.md` | 性能参数决策记录（BATCH_SIZE 经验最优点 = 10，P-01 验证）|
| `references/ai-translate-cache.md` | **SHA-1 内容缓存** 设计与实测：3 个 morning run 8.3× 加速对比（2026-06-03 实装）|
| `references/audit-fix-workflow.md` | 审计修复工作流 + 常见修复类型代码模式 + **用户偏好" 一切从简" 7 条原则** + **import-before-shebang Python 陷阱** |
| `references/hung-process-diagnosis.md` | **卡住进程诊断协议** — faulthandler + SIGALRM 自动 dump 找死锁点，0% CPU 场景的通用排查手法（2026-06-02 实战：domain_metadata RLock 自递归） |
| `references/wsl-disk-space-management.md` | C 盘清理：WizTree 分析 + WSL/Docker/缓存清理方法 + 管理员脚本 |
| `references/skill-reference-audit.md` | **SKILL.md 参考路径审计** — root 级 vs skill 本地路径规则 +批量修复命令 |
| `references/repo-restructuring-playbook.md` | **仓库重构前5 分钟必读** — git log 看设计意图 +不可逆操作 bundle备份 + TrendRadar 双层结构教训(2026-06-10实战) |
| `references/sync_files_robocopy_wrapper.md` | **`sync_files.py`完整源码 + robocopy↔rsync flag 对照表** — Windows 上替代 rsync 的 Python wrapper,含 EXCLUDES数组 + exit code语义 +故障排查 |

> **重要**: `references/proxy-config.md` 中按层级区分两类代理：(1) TrendRadar pipeline 内部 `PROXY_URL`（RSS 采集），(2) Gateway 系统级 `HTTP_PROXY` 环境变量（Hermes web 工具）。两类互不替代，都需配置。

## AI 翻译 SHA-1 内容缓存（2026-06-03 实装 + 8.3× 加速）

`ai_translate.py::process_batches` 在每批次**调 batch_func 之前**插入缓存层。Key = `hash(title) | hash(summary) | source_lang`，存 `cache/translate_cache.json`（原子写）。

```python
# ai_translate.py 大致结构
for batch in batches:
    pairs = [(item[3], item[4]) for item in batch]  # (title, summary)
    cache = _load_cache()
    cached_results, uncached_indices = [], []
    for i, (t, s) in enumerate(pairs):
        key = f"{_content_hash(t)}|{_content_hash(s)}|{source_lang or 'auto'}"
        if key in cache: cached_results.append((i, cache[key]))
        else: uncached_indices.append(i)
    if not uncached_indices:
        # 100% 命中，跳过 API
        continue
    # 只对 uncached 调 API，结果 merge 后写回 cache
    ...
```

**性能实测**（3 back-to-back morning runs, 30 items, 5 foreign）:

| 场景 | push_prepare | ai_translate | TOTAL | vs 基线 |
|------|:---:|:---:|:---:|:---:|
| 冷 cache + 冷 fetch | 1.5s | 7.0s | 9.2s | 2.6× |
| 暖 cache + 冷 fetch | 1.8s | 4.5s | 6.1s | 3.9× |
| 暖 cache + 暖 fetch | 0.1s | 1.7s | **2.9s** | **8.3×** |

**实战影响**: cron 9/12/21 三次推送共享 60-80% 条目（同一批 BBC/Reuters 跨 12 小时重复），早报写满 cache → 午/晚报 ai_translate 砍到 <2s。

**铁律**:
- 任何 cache_valid 分支必须**显式**赋值（不依赖 default）
- `_save_cache` 用 `tempfile.mkstemp + os.replace` 原子写（避免半截 JSON）
- `_get_cache_path` lazy 初始化（避免 import 时强制读 disk）

**坑（2026-06-03 实测）**: 单元测试如果用 mock batch_func 测调用次数，cache 命中会让 batch_func **完全不被调用**，断言 `call_count == 2` 直接挂 0。测试 setUp 必须清 cache：

```python
class TestBatchTranslateAllBatching:
    def setup_method(self, method):
        from ai_translate import _get_cache_path
        p = _get_cache_path()
        if p.exists(): p.unlink()
```

## slot_direct_push.py: PYTHON_GIL=0 污染修复（2026-06-03 实装）

`slot_direct_push.py` 调 `subprocess.run(['hermes', 'send', ...])` 投递 WeCom 碎片。**bug**: 父进程（cron/pipeline）环境有 `PYTHON_GIL=0`，hermes CLI 启动其 venv 的 Python 解释器时也看到 `PYTHON_GIL=0` → `config_read_gil: Disabling the GIL is not supported by this build` 立即崩溃。

**修复**（在 `_send_fragment` 里显式过滤 env）:

```python
import os as _os
env = {k: v for k, v in _os.environ.items()
       if k not in ('PYTHON_GIL', 'PYTHONNOUSERSITE')}
result = subprocess.run(
    ['hermes', 'send', '--to', 'wecom:bl', frag],
    capture_output=True, text=True, timeout=30,
    env=env,  # ← 关键：过滤 GIL 变量
)
```

**铁律**（任何 Python 脚本调 `hermes` CLI 时）: `subprocess.run` 必须传 `env=` 显式过滤 `PYTHON_GIL` + `PYTHONNOUSERSITE`，否则在 GIL-disabled 环境下 hermes 必崩。

## fetch_feeds 重试策略优化（2026-06-03）

`fetch_feeds.py::_fetch_one` 默认 `max_retries=2` (3 attempts) + 1s/2s backoff。**实测**: 5 个源（Sixth Tone, Al Jazeera, WSJ, 澎湃, Reuters）持续失败，2 retries 浪费 ~6s 在已知的失败重试。

**调整**: `max_retries=1` (2 attempts) + 0.5s/1s backoff。**结果**:
- 冷 fetch + 4 fail: 22.6s → 16.7s（-5.9s）
- 完整 3-run: cold 9.2s / warm-fresh 6.1s / warm-warm 2.9s

**铁律**: 重试参数默认值应假设**网络问题短暂**，**配置性失败**（被墙 / 404 / 持续 5xx）应快速 bail 而不是重试 N 次。

## RSS 源被 403/屏蔽的 Google News 代理模式（2026-06-03 实装）

**触发信号**: 某个 RSS 源在所有代理节点都返回 HTTP 403（或 IP 地理限制），**不是** timeout/SSL 错误。**403 = 源站封禁数据中心/代理 IP 段**，不是代理质量问题（与 Sixth Tone 的 SSL flake 完全不同的失败模式）。

**典型受害者**（2026-06-03 测过）: `aljazeera.com/xml/rss/all.xml` — 在 🇭🇰 04/08、🇸🇬 狮城 08、🇺🇸 美国 05 全部节点都 403。

**解法**: 切换到 Google News 搜索 RSS（`news.google.com/rss/search?q=site:<domain>`）作为代理层。Google News 聚合器有自己的数据中心 IP 段，**不**会被源站封禁，**且** Google News 索引层把站外 RSS 包成自己 URL，用户点链接还是跳到原站。

**改动 config/sources.json**（3 步）:
```python
# 原: "feed_url": "https://www.aljazeera.com/xml/rss/all.xml"
# 改: "feed_url": "https://news.google.com/rss/search?q=site:aljazeera.com&hl=en-US&gl=US&ceid=US:en"
# 加: "desc": "卡塔尔半岛电视台（Google News 聚合）"
```

**时效性权衡**:
- 直接 RSS: 实时，200ms 内
- Google News 代理: **索引延迟 5-30h**（实测 18h lag），但**100 entries 全量**
- 一天 3 次推送的简报场景，18h 旧内容仍 relevance 高（议题长尾）

**标题格式**: Google News 自动加 ` - <源名>` 后缀（与 BBC 模式一致），渲染时清洗逻辑复用。

**架构统一**: 已有 BBC 中国、Reuters、WSJ 世界新闻 都走 Google News 模式（`news.google.com/rss/search?q=site:<domain>`），加入新源时**优先用此模式**。

**Al Jazeera 切换效果对比**:
| 维度 | 原 RSS | Google News |
|------|--------|-------------|
| 连通性 | 403 全节点 | 200 (0.2-0.7s) |
| 浪费重试 | 8s × 2 = 16s | 0 |
| 精选占比 | 0% | 5-6/30 (17-20%) |
| 独家价值 | N/A | 伊朗/中东议题（Reuters/BBC 没覆盖） |

**何时用方案 A (disable) 而非方案 B (Google News)**:
- 3 天精选占比 < 1%（说明 LLM 评分器不看好）
- Google News 也搜不到该源（极小众）
- 内容**必须是实时**（如交易数据、突发事件 ticker）

**判断 403 源站 vs 代理问题的快速命令**:
```bash
# 4 个不同节点测同一个 403 源
for node in "🇭🇰 香港 04" "🇭🇰 香港 08" "🇸🇬 狮城 08 TR" "🇺🇸 美国 05"; do
  curl -s -X PUT "http://127.0.0.1:9090/proxies/%F0%9F%8C%8D%20%E5%9B%BD%E5%A4%96%E5%AA%92%E4%BD%93" \
    -H "Content-Type: application/json" -d "{\"name\":\"$node\"}" >/dev/null
  curl -x http://127.0.0.1:7890 -sI https://<blocked-domain>/rss/all.xml | head -1
done
# 全是 403 → 源站封禁；不同节点不同状态 → 代理问题
```

## Patch 工具陷阱

### 1. try/except 替换吃掉相邻行

用 patch 工具替换 `except Exception: pass` 块时，若 `old_string` 包含了相邻的控制流行（如 `else:`、`self._db_connections.clear()`），patch 的 diff 引擎可能只匹配前半段而吃掉后半段。**修复铁律**：

```python
# ❌ 危险：old_string 跨越了互不相关的作用域
old_string = """                    try:
                        conn.close()
                    except Exception:
                        pass
                self._db_connections.clear()"""

# ✅ 安全：old_string 严格限定在单个 try/except 块的闭包内，不包含后续语句
old_string = """                    try:
                        conn.close()
                    except Exception:
                        pass"""
```

**案例**：storage.py close_db() 的 except 修复中，`self._db_connections.clear()` 和 `else:` 先后被误删，需要两次回补。每次 patch 后应 `read_file` 验证 ±5 行上下文。

### 2. 多行 new_string 吃缩进（2026-06-02 反复踩坑 2 次）

**症状**：`patch(mode='replace')` 返回 success，但 `python3 -m py_compile` 报 `SyntaxError` 或 `IndentationError`。`od -c` 看到 raw bytes 里一行的开头比预期少了 N 个空格。

**根因**：`patch` 工具的 diff 引擎对 `new_string` 中**看起来像缩进的行**会无脑 dedent。当 `new_string` 含多行 Python 代码且**所有行都有相同的前导空格**时，patch 把这些缩进"解释"为 diff 上下文缩进而剥掉。

**触发场景**（实测 3 种）：

1. **`.py` 字符串里嵌入多行 markdown / bash**（最常见）—— `lines.append("...")` 内的多行字串如果每行带前导空格，patch 视为 diff 缩进剥掉
2. **`try:/except` 块大改** —— `new_string` 重写整个 try 块含 4-8 空格缩进，patch 剥掉
3. **函数体大改** —— 整个函数体从 `def f():\n    body` 重写时，body 的 4 空格被剥

**铁律**:
- **单行** 替换用 `patch` 工具
- **多行** 替换用 `sed -i`（bash） 或 `write_file` 全量重写
- 改完 **必须** `python3.14t -m py_compile <file>` 验证（不是 read_file — read_file 的 `LINE|CONTENT` 输出会掩盖缩进 bug）
- 真污染了从 git 历史恢复：`git show <clean_commit_sha>:<path> > <path>`
- **改完 TrendRadar 任何 .py 后**还必须跑 `find_spec vs actual load` 诊断（见上面"双 scripts/ 阴影陷阱"章节）— 5 秒验证，确保不是 sync 了错的副本

**案例**：
- `health_check.py` v3.0 重写时，new_string 50 行带 4 空格缩进，patch 后 raw bytes `1|` 前缀行被剥成 `1|` 顶格（行号变 raw content）
- `gen_cron_prompt.py` 加降级路径时，new_string 含 markdown `## Deep Analysis` 标题（4 空格缩进），被 patch 剥成顶层 markdown
- 两个文件都被破坏到 SyntaxError，`git checkout` 不一定真恢复（如果污染已 commit 到 HEAD）

**验证命令**（任何 patch 之后必跑）：
```bash
# 1) py_compile 验证语法
python3.14t -m py_compile <file> 2>&1
# 期望: 空输出 = OK

# 2) od 看 line 1 raw bytes（避开 read_file 的 LINE|CONTENT 干扰）
head -1 <file> | od -c | head -1
# 期望: 0000000   #   !   /   u   s   r   /   ...  （无 N| 前缀）
```

**为什么 read_file 救不了你**：`read_file` 工具的输出格式是 `LINE|CONTENT`（N 是行号），看起来每行都带 `1|` `2|` 前缀 —— **这是工具的展示格式不是文件内容**。但当你看到 `1|1|#!...`（两个 `1`）时，**第一个 `1` 是行号，第二个 `1` 是真的 raw byte**。**判断方法**：用 `od -c` 一次性确认 raw bytes 是 `#!` 还是 `1|#!`。

**详细复现案例 + 已踩坑清单** 见 `references/patch-tool-indent-bug.md`。

## GitHub Web UI 陷阱：symlink + 空 __init__.py（2026-06-02 用户反馈）

**陷阱 1：仓库根 `config/` `scripts/` 是 symlink，GitHub 看到一行文本**

Git 不跟踪 symlink 指向的内容，只把 symlink 本身（`config -> trendradar/config` 这一行）存进 git blob。**GitHub Web UI 在目录列表里点 symlink，进去只有 1 行** `config -> trendradar/config` 文本——看起来像"目录是空的"。

**症状**：用户在 GitHub Web 看到仓库根的 `config/` `scripts/` 各只剩一行字，以为"目录被清空了"。

**根因**：5/30 之前有过 root 级重复目录清理，建了 symlink 解决 cron Workdir 路径问题，但 GitHub Web UI 不展开 symlink。

**修法（已用，commit 5c21d19）**：
- 根 `config/` `scripts/` 改**真目录**（13+33=46 个文件）—— git 跟踪真目录，GitHub 显示真目录
- 内层 `trendradar/config/` `trendradar/scripts/` 保留（Python `import trendradar.scripts.settings` 用包路径）
- 加 `scripts_sync.sh` 双向同步脚本（内层 ⇄ 外层，详见下一节）

**陷阱 2：空 `__init__.py` 在 GitHub Web 显示为 0 字节**

仓库内层 `trendradar/config/__init__.py` `trendradar/scripts/__init__.py` 等 5 个 `__init__.py` 是 0 字节空文件（Python 包标记用）。GitHub Web UI 列表按字母序把 `__init__.py` 排在第一个，**点进去看到空编辑器（0 字节）**——视觉上像"目录内容缺失"。

**修法（已用，commit 6355873）**：5 个 `__init__.py` 都填有意义的 docstring：
- `trendradar/__init__.py` 337B（package 总览）
- `trendradar/config/__init__.py` 1417B（12 个 config 文件清单 + 用途）
- `trendradar/scripts/__init__.py` 2085B（18 个脚本清单 + 哪些 cron 跑）
- `trendradar/migrations/__init__.py` 465B（API 说明）
- `trendradar/tests/__init__.py` 388B（pytest 套件说明）

**铁律**：仓库里任何 `__init__.py` 都填一段说明性 docstring（≥ 200 字），让 GitHub Web UI 不显示"空文件"误导。

**诊断**：用户报"GitHub 上某目录只剩一行字/空白" → 1) 是不是 symlink？ 2) 是不是 `__init__.py` 空？两种都用 `cp -rL` 展开成真内容核对。

## **历史** — scripts_sync.sh（2026-06-29 已移除）

**为什么需要双副本**（2026-06-02 设计决策）：

| 路径 | 用途 | 谁读 |
|------|------|------|
| `~/.hermes/trendradar/config/` `scripts/`（根） | cron Workdir LLM agent 用 `config/sources.json` 路径访问 | LLM agent 调 cron 时 |
| `~/.hermes/trendradar/trendradar/config/` `scripts/`（内层） | Python 包路径 `from trendradar.config import X` / `from trendradar.scripts import X` | 解释器 import 时 |

**两者内容必须一致**——改一边后必须同步另一边。

### ⚠️ 隐藏的第三个同步目标：`$HERMES_HOME/scripts/`（2026-06-09 诊断确认）

`scripts_sync.sh` 维护的是上面两个目录，但 scheduler 跑 `no_agent` cron 时强制要求脚本位于：

```
$HERMES_HOME/scripts/<file>.py    # Windows: %LOCALAPPDATA%\hermes\scripts\
```

这是**第三个独立目录**，不被 `scripts_sync.sh` 触及。仓库里的 `hermes-scripts/` 目录是 git 跟踪的源，**必须显式 cp 到这里**才能被 no_agent cron 跑：

```bash
HERMES_HOME="${HERMES_HOME:-$LOCALAPPDATA/hermes}"   # 或 $HOME/.hermes
mkdir -p "$HERMES_HOME/scripts"
cp ~/.hermes/trendradar/hermes-scripts/*.py "$HERMES_HOME/scripts/"
# 验证
md5sum ~/.hermes/trendradar/hermes-scripts/*.py "$HERMES_HOME/scripts/"*.py
```

**铁律**：任何 no_agent cron 脚本变更 = **3 个目录都要 sync**（不是 2 个）：

| # | 目录 | 谁用 |
|---|------|------|
| 1 | `~/.hermes/trendradar/hermes-scripts/` | git tracked source |
| 2 | `~/.hermes/trendradar/scripts/`（外层） + `trendradar/scripts/`（内层） | Python import + cron Workdir |
| 3 | `$HERMES_HOME/scripts/` | scheduler 实际执行 no_agent cron |

`scripts_sync.sh` 只覆盖 #1 ↔ #2。#2 → #3 必须手动 cp。

**验证**（任何 no_agent job 跑挂时跑这3 条）：
```bash
ls "$HERMES_HOME/scripts/" | head -5           # 目录在
md5sum "$HERMES_HOME/scripts/trendradar_health_check.py" \
       ~/.hermes/trendradar/hermes-scripts/trendradar_health_check.py
# 两个 hash 必须一致
```

**`scripts_sync.sh` 用法**：
```bash
cd ~/.hermes/trendradar
bash scripts_sync.sh              # 默认: 内层 → 外层（cron 跑前用）
bash scripts_sync.sh --reverse    # 外层 → 内层
bash scripts_sync.sh --check      # 干跑: 只检查差异
bash scripts_sync.sh --watch      # 持续模式: 5s 同步一次
```

**排除规则**（同步时自动跳过）：`__pycache__/` `*.pyc` `*.bak` `config_real` `scripts_real`。

**实现**：用 `rsync` 如果可用，否则 `cp -r` + 删多出文件。

**手动改了一边之后必跑同步**：
- 改了内层 `trendradar/scripts/foo.py` → push 前 `bash scripts_sync.sh`
- 改了外层根 `scripts/foo.py` → `bash scripts_sync.sh --reverse`
- 改完 `bash scripts_sync.sh --check` 验证 0 差异

**git 提交策略**：`scripts_sync.sh` + 根 `config/` `scripts/` 真目录都 commit，内层 `trendradar/config/` `trendradar/scripts/` 保留 commit。两份内容在 commit 时用 `--check` 验证一致。

## 多文件批量重构模式

处理跨 15+ 文件的同类改动（CST 统一、异常吞噬修复）时，用 `execute_code` 写 Python 脚本比逐个 `patch` 更高效：

```python
# 模式：先用 search_files 扫描所有目标 → execute_code 批量处理
for f in sorted(target_dir.glob('*.py')):
    text = f.read_text()
    # re.sub / replace 处理
    f.write_text(fixed_text)
```

**顺序**：先 `search_files` 扫描确认 → `execute_code` 批量替换 → 再 `read_file` 抽检几个文件验证。公共 import（CST、get_logger）优先添加在现有 import 块之后、空白行之前。

## 审计驱动修复流程

当存在外部审计文档（如 AUDIT-REPORT.md）时，按阶段执行：
1. 建 todo 清单（每项一个 id + 严重度标注）
2. 从 Top N 行动项开始，逐项 patch + 验证
3. 每完成一项更新 todo 状态
4. 全部完成后验证 import + 跑测试
5. rsync 工作副本 → 运行时副本
6. git commit + push（直连优先，代理回退）

常见修复类型（含代码模式）详见 `references/audit-fix-workflow.md`。

### 审计手册易漏陷阱

1. 删除 `CRON_JOB_NAMES` 中的 `'性能优化器'`
2. 删除 `check_scripts()` required 列表中的 `exitcodes.py` / `trace.py`
3. 清理 Docker 注释（行 208）
4. 删除 `check_pipeline()` import_check 中的 `'exitcodes'`
5. 删除 `check_pipeline()` pipeline_steps 中的 `'exitcodes.py'` / `'trace.py'`

执行审计大修时，**Phase 1 完成后必须单独验证 `hermes-scripts/trendradar_health_check.py`**：`grep -n '性能优化器\|exitcodes\|trace\.py'` 应无输出。然后用 `TRENDRADAR_HOME=... python3 ~/.hermes/scripts/trendradar_health_check.py` 运行验证，确认不再出现假阳性。

## CI/CD

`.github/workflows/ci.yml` 包含：
- **ruff lint** — 代码风格 + 安全检查
- **bandit** — 安全漏洞检查
- **mypy** — 类型检查（--ignore-missing-imports）
- **pytest** — smoke test（required）+ full test（continue-on-error）
- **check-references** — 自动拦截 Skill references 与根 references 漂移

## 健康诊断快速参考（2026-06-09 协议）

**触发场景**：用户说 "诊断 TrendRadar"、"确认脚本/数据库健康"、"cron 没跑"、"日报没收到"。

**铁律**：**先读本 skill 的 `Cron 状态解读陷阱` + `双 data 目录陷阱` + `双 scripts/ 阴影陷阱` 三个章节**，再开始动手。不要直接 `ls -la` 一通乱敲——那会让你错过关键的14 项 health_check 协议。

**推荐诊断顺序**（每步都对应 self-healing skill 的某个 check）：

| # | 步骤 | 查什么 | 对应 self-healing check |
|---|------|--------|------------------------|
| 1 | `hermes cron status` | Gateway 状态 | `check_gateway` |
| 2 | `hermes cron list` + `ls $HERMES_HOME/cron/jobs.json` | Job 是否注册 | `check_cron` |
| 3 | `ls -la $HERMES_HOME/scripts/` | no_agent 脚本目录 | `check_scripts` |
| 4 | `python -c "import trendradar.scripts.settings"` | import 链路 | `check_pipeline` (import 子项) |
| 5 | `python -c "import sqlite3; sqlite3.connect(get_data_dir()/'fingerprints.db'); PRAGMA integrity_check"` | DB 健康 | `check_db` |
| 6 | `ls -la $TR/data/curated_*.json` 看 mtime | 数据时效 | `check_data_freshness` |
| 7 | `diff -rq $TR/config/ $TR/trendradar/config/` | 双副本同步 | `check_scripts` (子项) |
| 8 | `diff -rq $TR/hermes-scripts/ $HERMES_HOME/scripts/` | **3rd 副本同步**（常见漏） | （未在 self-healing 中显式列出）|
| 9 | `md5sum $TR/data/fingerprints.db $TR/trendradar/data/fingerprints.db` | data 目录分裂 | `check_blind_spot` / `check_data_freshness` |
| 10 | `curl -sI https://www.google.com` | 直连 vs 代理 | （健康检查之外）|

**加载 self-healing skill 触发全套协议**：
- 完整14 项 + 4 子项见 `../self-healing/SKILL.md`
- 启动命令（手动触发）：`python ~/.hermes/scripts/trendradar_health_check.py`（注意不是仓库内的 `hermes-scripts/` 版本——cron 跑的是 `$HERMES_HOME/scripts/` 那个）
- 14 项检查对应的 `check_*` 函数见 self-healing/SKILL.md 的 L9-L15 行

**常见误区**（2026-06-09 实测）：
- ❌ `ls -la ~/.hermes/trendradar/`（Windows 上找不到 → 误以为系统没装）
- ✅ `ls -la "${HERMES_HOME:-$LOCALAPPDATA/hermes}/trendradar/"`
- ❌ `crontab -l` 为空就报 "cron 没装"——Hermes 用内置 gateway scheduler，不是系统 cron
- ✅ 先 `hermes cron status` 看 Gateway 状态
- ❌ 改完 `hermes-scripts/foo.py` 就以为 cron 会跑新版本
- ✅ 必须 `cp` 到 `$HERMES_HOME/scripts/`（scheduler path traversal guard 会拦截外面的脚本）

**输出模板**（诊断报告标准格式）：

```markdown
# TrendRadar 健康诊断 @ <日期>

## ✅ 健康项
- 生产 DB (外层 fingerprints.db): 10.3 MB · WAL · integrity=ok · 397/3210 rows
- 包结构: TR/trendradar/__init__.py 存在 · import 链路全通
- health_check 模块: 14+ check 函数全部加载
- 外层 data/curated_*.json mtime: <最近时间>

## 🚨 异常项（按优先级排序）
1. Gateway 未运行 — 所有 cron 静默
2. cron/jobs.json 不存在 — 6 个 job 从未注册
3. $HERMES_HOME/scripts/ 不存在 — no_agent cron 会被 path guard 拦截
4. 双 data 目录分裂持续中 — md5 不同步
5. 三副本同步铁律被破坏 — hermes-scripts/ 没 cp 到 HERMES_HOME/scripts/

## 🛠️ 修复命令
hermes gateway install
<创建 6 个 cron job>
mkdir -p $HERMES_HOME/scripts && cp ~/.hermes/trendradar/hermes-scripts/*.py $HERMES_HOME/scripts/
<手动 cp 外层 data → 内层 trendradar/data/>
```

把这份诊断输出存到 `~/.hermes/trendradar/cache/diagnostics/<date>.md` 留底，便于跨会话对比趋势。

## 跨会话发现：umbrella skill 在 skills_list 中不可见（2026-06-09）

**陷阱**：`skills_list` 只列出有顶级 `SKILL.md` 的 skill。`trendradar/` 是一个 umbrella——内含 4 个子 skill（news-secretary / report-generator / self-healing / system-config），**每个都有自己的 SKILL.md**，但 `trendradar/` 目录本身没有 SKILL.md。结果：`skills_list` 完全跳过 `trendradar`，但**子 skill 名字也不在列表里**——只有当用户主动说 "加载 news-secretary" 时才会出现。

**症状**：用户问 "有没有叫 trendradar 的 skill？" 时 `skills_list` 返回空，导致 agent 误判 "不存在"。

**正确做法**：
```python
# skills_list 后，如果用户问的 skill 不在列表里，先 grep 一下技能目录
from pathlib import Path
for d in Path(get_hermes_home() / "skills").iterdir():
    if (d / "SKILL.md").exists():
        # 顶级 skill（skills_list 已列）
        ...
    else:
        # umbrella —— 检查子目录里有没有 SKILL.md
        subs = [s.name for s in d.iterdir() if (s / "SKILL.md").exists()]
        if subs:
            # 这是一个 umbrella，子 skill 列表：{subs}
```

**临时缓解**（已通过 system-config 的 skill metadata 暴露）：`self-healing/SKILL.md` frontmatter 写了 `metadata.hermes.companion_skills: [news-secretary, report-generator, system-config]`，让 agent 在加载 self-healing 时知道还有这些同伴。但 **umbrella 的存在对 `skills_list` 仍然不可见**——这是 Hermes skill library 的一个已知 gap。

**建议**（未来改进）：给 umbrella 加一个最小 `SKILL.md`，仅用于被 `skills_list` 发现，内容是一行 "This umbrella contains: ..." 加 4 个子 skill 的链接。
