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
- **简报存档**: `~/.hermes/trendradar/archive/YYYY-MM-DD/{slot}.md`（render_markdown 自动写入，补发用）
- **Git 发布仓**: `~/TrendRadar/`
- **从零搭建**: `~/TrendRadar/SETUP.md`
- **一条龙部署**: `~/TrendRadar/one-key-setup.sh`

## 同步到 Git 仓库

运行时 → Git 发布仓用 `rsync -av` 批量同步（排除 cache/data/logs/output/mail_queue 等运行时数据）。详见 `references/REPO-SYNC.md`。

## Hermes 关键路径

| 组件 | 路径 |
|------|------|
| 主配置 | `~/.hermes/config.yaml` |
| Cron 配置 | `~/.hermes/cron/jobs.json` |
| 技能目录 | `~/.hermes/skills/trendradar/` |
| 运行日志 | `~/.hermes/logs/agent.log` / `errors.log` |

## Cron 任务

`hermes cron list` 查看所有任务。日报/周报/月报/优化器为 LLM 驱动，体检/维护/看门狗为 no_agent 脚本模式。

**Cron prompt 格式**: 自动生成。`scripts/gen_cron_prompt.py` 从 `pipeline_orchestrator.py --list-steps` 产出 `references/cron-prompt-generated.md`。news-secretary SKILL 引用此文件作为 SSOT，消除 cron prompt 与 SKILL 双份维护漂移。

## Python 环境

- **解释器**: `python3.14t`（free-threaded）
- **必需**: `export PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0`
- **依赖**: `feedparser zstandard aiohttp pyyaml pyahocorasick`

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
## 同步到 Git 仓库

三处需同步：Hermes 运行时 → Hermes skills → Git 发布仓。`rsync -av` 双向映射（排除 cache/data/logs/output/mail_queue 等运行时数据）。详见 `references/REPO-SYNC.md`。

**Git Push**（优先级顺序）：

1. **直连**（TLS 最稳定）：
   ```bash
   cd ~/TrendRadar && TOKEN=$(gh auth token) && \
   GIT_TERMINAL_PROMPT=0 git -c credential.helper='' -c http.proxy= -c https.proxy= \
   push "https://BedrockLian:${TOKEN}@github.com/BedrockLian/TrendRadar.git" main
   ```

2. **走代理**（直连超时时）：
   ```bash
   cd ~/TrendRadar && TOKEN=$(gh auth token) && \
   GIT_TERMINAL_PROMPT=0 git -c credential.helper='' \
   -c http.proxy=http://127.0.0.1:7890 -c https.proxy=http://127.0.0.1:7890 \
   push "https://BedrockLian:${TOKEN}@github.com/BedrockLian/TrendRadar.git" main
   ```

3. **代理 TLS 故障**（GnuTLS handshake failed）→ 回退直连（方案 1）。
   同时取消 repo 级 proxy 配置：`git config --unset http.proxy && git config --unset https.proxy`

## References 一致性维护

**问题**：Skill references/ 与根 references/ 有多份同名副本。修改根目录后忘记同步 Skill 副本 → Agent 读到过时信息。

**检测**：
```bash
cd ~/TrendRadar/trendradar
python3 -c "
import hashlib
from pathlib import Path
root = Path('references')
for skill_refs in Path('skills').glob('*/references'):
    for f in skill_refs.glob('*.md'):
        root_f = root / f.name
        if root_f.exists():
            h1 = hashlib.md5(root_f.read_bytes()).hexdigest()
            h2 = hashlib.md5(f.read_bytes()).hexdigest()
            if h1 != h2:
                print(f'MISMATCH: {root_f} != {f}')
"
```

**修复铁律**：
```
修改根 references/SKILL-AUDIT.md  # was: template example, now points to skill audit 后
    ↓
检查是否有 Skill 同名副本
    ↓
    ├─ 有 → cp references/SKILL-AUDIT.md  # was: template example, now points to skill audit skills/*/references/SKILL-AUDIT.md  # was: template example, now points to skill audit
    └─ 无 → 完成
```

**CI 防护**：`.github/workflows/ci.yml` 的 `check-references` job 会自动拦截漂移。

详尽的冲突修复 + 长期防护机制见 `references/REFERENCES-CONSISTENCY-GUIDE.md`。

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

## 代码模式：原子文件写入（并发安全）

多 cron job 并发写同一 JSON 文件时，`read_text → modify → write_text` 存在 TOCTOU 竞争。解决：临时文件 + `os.replace`（原子 rename）。详见 `references/SETUP.md  # was atomic-file-writes → setup`。

```python
fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.tmp_')
try:
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
except Exception:
    os.unlink(tmp)
    raise
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

> **入口**: `references/INDEX.md` — 全局索引（按功能分类），所有文档的唯一导航入口。
> **归档**: `references/_archive/` — 合并精简后归档的 36 份旧文档。查找历史细节时先看这里。

| 文件 | 内容 |
|------|------|
| `references/INDEX.md` | **全局索引**（首次查阅先读此文件） |
| `references/ARCHITECTURE.md` | 架构总览：分层设计、模块边界、数据流 |
| `references/PIPELINE.md` | 管线 v2.8.0 全量文档（数据流 Mermaid 图） |
| `references/SETUP.md` | 统一搭建/安装/环境配置 |
| `references/TRAPS.md` | 已知陷阱全集 |
| `references/REPO-SYNC.md` | 三处同步 + 验证流程 |
| `references/REFERENCES-CONSISTENCY-GUIDE.md` | References 一致性维护（冲突修复+CI防护+日常铁律） |
| `references/SKILL-AUDIT.md` | Skill 审计清单（dead refs/cron 同步/行数检查） |
| `references/DELIVERY-WATERMARK.md` | 投递水印机制：MarkerDir + delivery_watchdog + 手动标记 |
| `references/cron-prompt-generated.md` | 日报 cron prompt（自动生成，SSOT） |

## CI/CD

`.github/workflows/ci.yml` 包含：
- **ruff lint** — 代码风格 + 安全检查（S/B 系列规则）
- **bandit** — 安全漏洞扫描
- **mypy** — 类型检查（--ignore-missing-imports）
- **pytest** — smoke test（required）+ full test（continue-on-error）
- **check-references** — 自动拦截 Skill references 与根 references 漂移
