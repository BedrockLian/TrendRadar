---
name: system-config
slug: system-config
version: 2.11.0
description: TrendRadar 项目路径、Python 环境、Cron 任务、代理配置速查。
author: Hermes Agent
metadata:
  hermes:
    tags: [trendradar, config, setup]
---

## 触发

Agent 需要 TrendRadar 路径/Python 环境/Cron/代理/同步信息时自动加载。

## 项目结构

- **源码/运行时**: `~/.hermes/trendradar/`
- **Git 发布仓**: `~/TrendRadar/`
- **从零搭建**: `~/TrendRadar/SETUP.md`
- **一条龙部署**: `~/TrendRadar/one-key-setup.sh`

## 同步到 Git 仓库

运行时 → Git 发布仓用 `rsync -av` 批量同步（排除 cache/data/logs/output/mail_queue 等运行时数据）。详见 `references/repo-sync.md`。

## Hermes 关键路径

| 组件 | 路径 |
|------|------|
| 主配置 | `~/.hermes/config.yaml` |
| Cron 配置 | `~/.hermes/cron/jobs.json` |
| 技能目录 | `~/.hermes/skills/trendradar/` |
| 运行日志 | `~/.hermes/logs/agent.log` / `errors.log` |

## Cron 任务

`hermes cron list` 查看所有任务。日报/周报/月报/优化器为 LLM 驱动，体检/维护/看门狗为 no_agent 脚本模式。

**Cron prompt 格式**: 只需透传脚本输出。`sanity_check.py` 在推送层自动拦截禁语，无需 prompt 层重复约束。

## Python 环境

- **解释器**: `python3.14t`（free-threaded）
- **必需**: `export PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0`
- **依赖**: `feedparser zstandard aiohttp pyyaml pyahocorasick`
- **GIL 锁**: `settings.py` 启动时自动检查，`PYTHON_GIL != 0` 输出 RuntimeWarning

## 同步到 Git 仓库

三处需同步：Hermes 运行时、Hermes 脚本、Git 发布仓。详见 `references/repo-sync.md`。

**WSL 环境 GitHub 直连失败** — 两种方式：

1. **走米霍姆代理**（代理开启时）：
   ```bash
   cd ~/TrendRadar && git -c http.proxy=http://127.0.0.1:7890 -c https.proxy=http://127.0.0.1:7890 push origin main
   ```

2. **免代理直接推送**（`gh` CLI 已登录时，更可靠）：
   ```bash
   cd ~/TrendRadar && git push https://$(git config user.name):$(gh auth token)@github.com/... main
   ```
   或完整写法：
   ```bash
   GH_TOKEN=$(gh auth token) git push https://BedrockLian:$(gh auth token)@github.com/BedrockLian/TrendRadar.git main
   ```
   此方式绕过 credential helper 挂起问题，token 内联在 URL 中直接认证。

## 维护注意

修改 skill SKILL.md 或 reference 文件后，两处同步执行：`~/.hermes/skills/trendradar/` ↔ `~/TrendRadar/trendradar/skills/`。

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

## 代码模式：SQLite 懒迁移

避免 `try: ALTER TABLE ADD COLUMN / except sqlite3.OperationalError: pass` 模式——异常范围过宽，会静默吞掉 DB 损坏、锁冲突等真错误。改用 PRAGMA 先检查：

```python
# ✅ 先读 schema，只在确实需要时才 ALTER TABLE
cols = {row[1] for row in conn.execute("PRAGMA table_info(fingerprints)")}
if 'run_id' not in cols:
    conn.execute("ALTER TABLE fingerprints ADD COLUMN run_id TEXT DEFAULT ''")
```

## TrendRadar 技能

| 名称 | 用途 |
|------|------|
| news-secretary | 日报推送管线 |
| self-healing | 自动体检 + 自修复 |
| performance-optimizer | 推送质量评分 + 偏好收敛 |
| weekly-report | 每周深度趋势周报 |
| monthly-report | 月度聚合趋势报告 |

## 参考文件

| 文件 | 内容 |
|------|------|
| `references/skill-audit.md` | Skill 审计清单（dead refs/cron 同步/行数检查） |
| `references/repo-sync.md` | 三处同步 + 验证流程 |
| `references/rsshub-proxy-setup.md` | RSSHub Docker 代理配置（undici + --import） |
| `references/proxy-config.md` | 米霍姆代理分流架构 + 排查 |
| `references/pipeline.md` | 管线 v2.8.0 全量文档 |
| `references/traps.md` | 已知陷阱全集 |
| `references/pitfalls-utf8-bytes.md` | UTF-8 字节计数陷阱修复 |
