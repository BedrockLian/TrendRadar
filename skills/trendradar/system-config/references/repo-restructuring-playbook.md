#仓库重构 Playbook — 重构前5 分钟必读 git log

> **2026-06-10实战来源**：用户说"两个 trendradar 文件夹嵌套,分离一个做运行时一个做 GitHub仓库"。我直接假设"git仓库 = 内层",差点 `mv .git`破坏188 个 tracked 文件。读了 commit `5c21d19` 的 message 才意识到双层是设计选择,不是 bug。
>
> **教训**:任何"看着别扭"的结构,重构前**必读** git log 看设计意图。

##触发场景

下列任一情况,先读本 playbook,再决定动手:

- "X 文件夹嵌套 Y,分离一下"
- "git仓库应该在 X 还是 Y"
- "内层/外层重复了,合并掉一份吧"
- "目录里有 symlink/重复文件,清理掉"
-任何 `mv .git` / `rm -rf <dir>` / `git reset --hard` 等不可逆操作

##5 分钟前置清单(必跑)

```bash
#1) 看最近10 个 commit标题(找最近的 fix commit)
cd <repo>
git log --oneline -10

#2)找最近的 "fix"/"refactor" commit,大概率有设计意图说明
git log --oneline --grep='fix\|refactor\|restructure\|reorganize' -20

#3) 看每个嫌疑 commit 的 message(找根因 + 设计决策)
git show <sha> --stat | head -80
# 看 commit body,通常有 "**问题**:" / "**根因**:" / "**修法**:" / "**未触动**:"章节

#4) 看 working tree 当前状态(确认改动范围)
git status -s | head -30
git status -s | wc -l # 总改动数

#5) 看 index跟踪的所有文件(确认仓库"知道"哪些路径)
git ls-files | wc -l
git ls-files | grep -v '^trendradar/' | head -20 # 看仓库根视角(外层视角)
git ls-files | grep '^trendradar/' | head -20 # 看嵌套视角(内层视角)
```

**关键**:第3步的 `git show <sha> --stat`输出的 commit message几乎总是包含"为什么这样设计"。**别跳过这一步**。

##不可逆操作前的强制备份

任何 `mv .git` / `rm -rf <dir>` / `git reset --hard` / `git filter-branch`之前,**必**留 bundle:

```bash
# 全历史 + 所有 ref备份到一个文件
git bundle create "$HOME/<repo>-$(date +%Y%m%d-%H%M).bundle" --all

#验证 bundle 可恢复
git clone "$HOME/<repo>-20260610-1411.bundle" /tmp/test-restore
cd /tmp/test-restore && git log --oneline -3
#期望:历史完整,与原仓库一致
```

**bundle 文件本身**就是完整仓库 — 含所有 commit / branch / tag。丢了原仓库也能从 bundle重建。

##常见"看似 bug 实为设计"的模式

|现象 |实际含义 |怎么识别 |
|------|---------|---------|
| **目录嵌套同名**(trendradar/trendradar) | 外层 = cron/workdir视角,内层 = Python 包视角 | `git log`找 `5c21d19` 类 commit |
| **symlink 在仓库根**(`config -> trendradar/config`) | GitHub Web UI 不展开 symlink,但 cron走得通 | 看 commit是否有 "GitHub Web UI 显示" 字样 |
| **空 `__init__.py`** | Python 包标记,但视觉上像"空文件" | 看 commit是否有 "填 docstring" 字样 |
| **重复 `data/`**目录(外层 + 内层) | 外层 =运行时(cron写),内层 = git跟踪 | 看 `get_data_dir()`解析哪边 |
| **`.bak` / `.broken`备份文件** | 历史回滚保险,别删 | `git log -- <bak_file>` 看历史 |

## TrendRadar 具体教训(本次踩坑)

```bash
# 我差点做的(WRONG):
cd ~/.hermes/trendradar
mv .git trendradar/.git
# 结果:git status爆188 个 D(因为 index跟踪的是外层视角的176 个文件,搬到内层后全部路径失效)

#真实情况(从5c21d19 commit message读到):
# - 外层是 git 主视角:config/ scripts/ hermes-scripts/ prompts/ 都是真目录
# - 内层是 Python 包镜像:trendradar/scripts/ trendradar/config/保留 __init__.py
# -两者内容由 scripts_sync.sh双向同步
# - 重构代价 = 重写整个 index(176 个文件路径映射),风险巨大

#正确做法(READ-ONLY探查):
git log --oneline -10 | grep -E 'fix|refactor' #找设计决策 commit
git show5c21d19 --stat | head -60 #读设计意图
# 然后:不动 .git,改向用户澄清"你想要的分离是什么意思"——选 A/B/C 不同方案
```

## 用户反馈时的回应模板

用户说"X嵌套了,分离"时,**不要**直接动手。先用1-2段回答澄清方向:

> 我摸完了,先停下来确认方向。`git log` 显示 [N] 个 commit 里 [关键 commit] 是 [设计意图]。这意味着 [X] 看起来是 bug,实际上是 [设计]。有3 条路线:
>
> **路线 A** (保守):保持现状,只清理未提交改动 —0风险
> **路线 B** (技术大手术):重构 index + cp跨目录 +改 cron路径 — 高风险,改动面 [N] 个文件
> **路线 C** (物理分离):git clone 到新位置 `~/TrendRadar/`,原 `hermes\trendradar\`纯做运行时 —0风险
>
> 我推荐 C,因为 [理由]。选哪个?

**关键**:即使用户授权("你建议哪个就哪个"),只要涉及不可逆操作,必须先 bundle备份,然后**确认**具体动作清单,最后逐项执行 +验证。

##验证清单(任何重构后必跑)

- [] `git log --oneline -10` 与重构前一致
- [] `git status` 没有意外的 modified/deleted
- [] `git ls-files | wc -l` 与重构前一致(176 → 不变)
- [] cron job状态不变(`hermes cron list` 显示6 个 active)
- [] cron Workdir路径不变(`jobs.json` 里 workdir字段)
- [] PYTHONPATH路径不变(`gen_cron_prompt.py`生成的 prompt)
- [] no_agent脚本可执行(`python $HERMES_HOME/scripts/delivery_watchdog.py` exit=0)
- [] TRENDRADAR_HOME路径不变(no_agent脚本默认 fallback)

任何一项变了,立即 bundle 回滚。

##详见

- `../../system-config/SKILL.md` 的 "项目结构"章节(已更新为反映双层设计意图)
- `../../self-healing/SKILL.md` 的 "嵌套包结构"章节(已加"不要尝试合并"警告)
- `../double-scripts-shadow-trap.md` — 双 scripts/阴影陷阱(代码层面解释)
