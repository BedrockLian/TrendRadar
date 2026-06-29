# 2026-06-29 仓库重构：双层 → 单包结构

## 背景

原 TrendRadar 仓库采用**嵌套双层结构**（commit 5c21d19 设计）：
- 外层 `config/` `scripts/` `tests/` = cron Workdir + GitHub Web UI 显示
- 内层 `trendradar/config/` `trendradar/scripts/` `trendradar/tests/` = Python 包路径
- 靠 `scripts_sync.sh` 双向同步
- 另有 `hermes-scripts/` `prompts/` 部署层 + `skills/` Hermes 本地技能

2026-06-29 评估后认为该结构有 5 个问题：
1. **双层重复** — 新手改代码不知道改哪份，必须靠同步脚本
2. **CI 埋错位置** — `.github/workflows/` 在 `trendradar/` 内层，GitHub Actions 搜不到
3. **Skills 进仓库** — Hermes Agent 本地配置（含环境特定路径）推到公开 GitHub
4. **运行时数据残留** — `archive/` `reports/` 历史 commit 过
5. **部署层混淆** — `hermes-scripts/` `prompts/` `scripts_sync.sh` 是部署物不是代码

## 变更内容（commit 65d1715 + e5d4629）

### 删除（98 个文件，-14614 行）

| 目录/文件 | 原因 |
|-----------|------|
| `config/`（根） | 与 `trendradar/config/` 完全重复 |
| `scripts/`（根） | 与 `trendradar/scripts/` 完全重复 |
| `tests/test_render_deep_analysis.py`（根） | 重复 |
| `hermes-scripts/` | 部署层，非包代码 |
| `prompts/` | 部署层 |
| `scripts_sync.sh` | 双层结构不再存在 |
| `one-key-setup.sh` | 部署脚本 |
| `audit_20260620.md` | 操作文档 |
| `trendradar/skills/` | Hermes Agent 本地技能，不入仓库 |
| `trendradar/archive/` | 运行时数据 |
| `trendradar/reports/` | 运行时数据 |
| `trendradar/.gitignore` | 合并到根 `.gitignore` |
| `.sync_state/` | 本地 sync 机制产物（fix commit） |

### 迁移

| 路径变化 | 说明 |
|----------|------|
| `trendradar/.github/workflows/ci.yml` → `.github/workflows/ci.yml` | CI 移到根目录 |

### 保留

```
TrendRadar/
├── .github/workflows/ci.yml
├── trendradar/                    # ← 单一 Python 包
│   ├── __init__.py
│   ├── config/          (11 文件)
│   ├── scripts/         (28 文件)
│   ├── tests/           (20 文件)
│   ├── migrations/      (4 文件)
│   ├── references/      (10 文件)
│   ├── pyproject.toml
│   └── requirements*.txt
├── .gitignore
├── LICENSE
├── README.md
└── SETUP.md
```

## 对本地运行的影响

### cron workdir 不变
cron job 的 Workdir 仍指向 `$HERMES_HOME/trendradar/`（外层），该目录结构未变——外层 `scripts/` `config/` 没有被删除，只是不再被 git 跟踪。

### 运行时脚本路径不变
`$HERMES_HOME/scripts/trendradar_health_check.py` 等 no_agent cron 脚本不受影响。

### 不再需要 `scripts_sync.sh`
该文件已从 Git 中移除。本地文件 `$HERMES_HOME/trendradar/scripts_sync.sh` 仍存在但不再维护——Python import 现在只走 `trendradar/trendradar/scripts/`，不再有外层副本阴影陷阱。

### 双副本阴影陷阱不再存在
根 `scripts/` `config/` 已从 git 中移除。Python 的 namespace package shadow 不再触发（只剩 `trendradar/trendradar/` 一个路径）。

### 三副本同步铁律已降级
之前需要同步三处：hermes-scripts/（git）→ 外层 scripts/（cron Workdir）→ $HERMES_HOME/scripts/（scheduler）。现在：
- hermes-scripts/ 不再在 git 中跟踪（本地 `$HERMES_HOME/trendradar/hermes-scripts/` 仍存在）
- 外层 scripts/ 不再在 git 中跟踪
- `$HERMES_HOME/scripts/` 仍然是 no_agent cron 的强制路径

## 同步协议更新

```bash
# 改完代码后推 GitHub（仍用 sync_repo.sh）
bash "$HOME/trendradar-sync-tools/sync_repo.sh"

# 改完 no_agent cron 脚本后同步到 scheduler（仍需要）
cp "$TR/hermes-scripts/*.py" "$HERMES_HOME/scripts/"
md5sum "$TR/hermes-scripts/trendradar_health_check.py" "$HERMES_HOME/scripts/trendradar_health_check.py"
```
