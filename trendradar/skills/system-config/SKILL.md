---
name: system-config
slug: system-config
version: 2.19.0
pipeline_compat: ">=2.9.0"
description: TrendRadar 项目路径、Python 环境、Cron 任务、代理配置速查。
author: Hermes Agent
metadata:
  hermes:
    tags: [trendradar, config, setup]
---

## 触发

Agent 需要 TrendRadar 路径/Python 环境/Cron/代理/同步信息时自动加载。

## 项目结构

- **源码/运行时**: `~/.hermes/trendradar/`（所有代码在 `trendradar/` 子目录内）
- **简报存档**: `~/.hermes/trendradar/archive/YYYY-MM-DD/{slot}.md`（render_markdown 自动写入，补发用）
- **Git 发布仓**: `~/TrendRadar/`
- **从零搭建**: `~/TrendRadar/trendradar/../../references/SETUP.md`
- **一条龙部署**: `~/TrendRadar/one-key-setup.sh`

> **2026-05-29**: root 级 `scripts/` `config/` `migrations/` `references/` 已删除（与 `trendradar/` 重复）。所有路径引用统一用 `trendradar/scripts/`、`trendradar/references/` 等。Cron prompt 已同步更新。
> **2026-05-30**: Pipeline v2.9.0 — subprocess 架构替换为直接函数调用。`pipeline_orchestrator.run_stage()` 签名为 `(name: str, func, *args)`。详见 `references/pipeline-v2.9.md`。
>
> **⚠️ root级目录删除后的 cron 陷阱（2026-05-30）**: 删除 root 级 `config/` `scripts/` 后，cron job 的 `TRENDRADAR_HOME=~/.hermes/trendradar`（外层）依然通过 `get_config_dir()` 期望 `$TRENDRADAR_HOME/config/`。实际配置文件在 `trendradar/config/` 内层 → 所有配置文件读不到，cron 静默失败（`sources.json` not found, `timeline.yaml` not found）。**修复**: 在外层创建 symlink —— `config/` → `trendradar/config/`, `scripts/` → `trendradar/scripts/`。`ln -sf trendradar/config config && ln -sf trendradar/scripts scripts`。维护铁律：任何删除/移动 root 级目录的操作后，必须检查并更新这些 symlink。

## Hermes 关键路径

| 组件 | 路径 |
|------|------|
| 主配置 | `~/.hermes/config.yaml` |
| Cron 配置 | `~/.hermes/cron/jobs.json` |
| 技能目录 | `~/.hermes/skills/trendradar/` |
| 运行日志 | `~/.hermes/logs/agent.log` / `errors.log` |

## Cron 任务

`hermes cron list` 查看所有任务。日报/周报/月报为 LLM 驱动，体检/维护/看门狗为 no_agent 脚本模式。

**Cron prompt 格式**: 自动生成。`scripts/gen_cron_prompt.py` 从 `pipeline_orchestrator.py --list-steps` 产出 cron prompt 文本。news-secretary SKILL 引用 cron prompt 作为 SSOT，消除 cron prompt 与 SKILL 双份维护漂移。

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
│   └── ...（其他脚本不变）
├── config/                     # 原 root config/ 已删除（2026-05-29）
└── ...
```

**关键变更**:
- `settings.py` 现在是 re-export 中心——所有现有 `from settings import X` 无需改动
- 新增配置直接加在对应 `config/*.py` 子模块中，然后在 `settings.py` 加一行 re-export
- `get_storage()` 单例在 `settings.py` 中，`record_fingerprints.py` 和 `heat_tracker.py` 已统一接入
- `storage.Storage.checkpoint_db(filename)` 执行 `PRAGMA wal_checkpoint(TRUNCATE)`

## Python 环境

- **解释器**: `python3.14t`（free-threaded）
- **必需**: `export PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0`
- **依赖**: `feedparser zstandard aiohttp pyyaml pyahocorasick pytest-asyncio`
- **测试**: `cd trendradar && python3 -m pytest tests/ -q`（177 passed, 0 failed）

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

## gen_cron_prompt.py 引号陷阱

`scripts/gen_cron_prompt.py` 用 f-string 拼接 bash 内容写入 `lines.append()`，双引号嵌套容易写出 `f"export PYTHON=\"{PYTHON}\""` 这类运行时 SyntaxError 的代码。原因是 f-string 中外层 `"` 与内层 `\"` 在 Python 解析器眼中是同一个引号字符的转义序列，Python 3.12+ 的 fstring 解析器会提前闭合外层引号。

**修复模式**: 用单引号 `'` 包裹 f-string 外层：
```python
# ❌ 会报 SyntaxError
lines.append(f"export PYTHON=\"{PYTHON}\"")
# ✅ 正确
lines.append(f'export PYTHON={PYTHON}')
```

`gen_cron_prompt.py` 2026-05-29 前长期处于语法错误状态（从未真正跑通过），修复后需手动 regenerate：`python3 scripts/gen_cron_prompt.py`。
## 两副本架构

详见 `../../references/REPO-SYNC.md`。

### 同步陷阱：Skills 改动只改了 cron 副本

`skill_manage` / `skill_view` 等技能工具操作的是 `~/.hermes/skills/`（cron 副本）。Git 仓库跟踪的是 `~/TrendRadar/trendradar/skills/`（工作树）。

**症状**：Skills 精简/合并/删除后 `git push`，GitHub 上旧 skill 目录仍然存在。

**根因**：只操作了 cron 副本的技能文件，没有同步到工作树就提交了。

**修复铁律** — 任何技能改动后，双向同步：
```bash
# Skills: cron 副本 → 工作树（涉及新增/修改时）
cp -r ~/.hermes/skills/trendradar/<skill>/ ~/TrendRadar/trendradar/skills/<skill>/

# References: 工作树 → cron 副本（涉及顶层 references 修改时）
cp ~/TrendRadar/trendradar/references/<file>.md ~/.hermes/trendradar/trendradar/references/

# Hermes-scripts: 工作树 → cron 副本
cp ~/TrendRadar/hermes-scripts/<script>.py ~/.hermes/scripts/
```

**验证**：`git add -A && git status --short` 应能看到技能目录的删除/新增/修改。提交前用 `diff` 对比两端的 skills 文件列表是否一致。

## References 一致性维护

详见 `../../references/MAINTENANCE.md`。

## sources.json 位置陷阱

`sources.json` 是**配置文件**（非运行时数据），但在 v2.9.0 之前代码从 `data/sources.json` 读取。已通过 `get_config_dir()` 修复——三个消费者（`curate_and_push.py` / `ai_translate.py` / `fetch_feeds.py`）统一从 `config/sources.json` 读取。

**修复铁律**：配置文件走 `get_config_dir()`，运行时数据走 `get_data_dir()`。`file_utils.py` 提供了两个工厂函数，`settings.py` 统一 re-export。

**验证**：`grep "sources.json" trendradar/scripts/*.py` 应全部指向 `get_config_dir()` 或 `config/`。

## 手动推送全链路工作流

当 cron 未触发或需要手动补推时，不走 `hermes cron run`（可能因工作目录/环境变量差异而静默失败），直接跑管线：

```bash
cd ~/.hermes/trendradar
export TRENDRADAR_HOME=~/.hermes/trendradar/trendradar
export PYTHONPATH=~/.hermes/trendradar
export DEEPSEEK_MODEL=deepseek-v4-flash
PYTHON_GIL= python3 trendradar/scripts/pipeline_orchestrator.py --push-id noon

# 若渲染步骤崩了，单独补跑：
PYTHON_GIL= python3 trendradar/scripts/render_markdown.py --push-id noon

# 推送到 WeCom：
PYTHON_GIL= cat trendradar/archive/$(date +%Y-%m-%d)/noon.md | hermes send --to wecom:bl
```

**关键**：
- `PYTHON_GIL=` 必须 unset（Python 3.14t 不支持 `PYTHON_GIL=0`，会 `config_read_gil` 崩溃）。
- `TRENDRADAR_HOME` 指向内层 `trendradar/` 目录（含 `scripts/` 和 `data/`）。
- **`DEEPSEEK_MODEL=deepseek-v4-flash` 必须设置** — 默认 `deepseek-chat` 处理日→中翻译时**必然返回原文不变**（不报错不告警），日文条目会全部以原文残留。Gateway override.conf 已注入此变量给 cron，但手动跑时不继承 gateway env，需要显式 export。详见 news-secretary SKILL 翻译管线第 5 条。

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
| `references/pytest-fixtures.md` | pytest 测试夹具模式 — tmp_db 对齐、async 环境配置 |
| `references/perf-tuning.md` | 性能参数决策记录（BATCH_SIZE=5 陷阱、超时/并发/熔断阈值） |
| `references/audit-fix-workflow.md` | 审计修复工作流 + 常见修复类型代码模式 |
| `references/wsl-disk-space-management.md` | C 盘清理：WizTree 分析 + WSL/Docker/缓存清理方法 + 管理员脚本 |
| `references/skill-reference-audit.md` | **SKILL.md 参考路径审计** — root 级 vs skill 本地路径规则 + 批量修复命令 |

> **重要**: `references/proxy-config.md` 中按层级区分两类代理：(1) TrendRadar pipeline 内部 `PROXY_URL`（RSS 采集），(2) Gateway 系统级 `HTTP_PROXY` 环境变量（Hermes web 工具）。两类互不替代，都需配置。

## patch 工具陷阱：try/except 替换吃掉相邻行

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
5. 删除 `check_pipeline()` pipeline_steps 中的 `exitcodes.py` / `trace.py`

执行审计大修时，**Phase 1 完成后必须单独验证 `hermes-scripts/trendradar_health_check.py`**：`grep -n '性能优化器\|exitcodes\|trace\.py'` 应无输出。然后用 `TRENDRADAR_HOME=... python3 ~/.hermes/scripts/trendradar_health_check.py` 运行验证，确认不再出现假阳性。

## CI/CD

`.github/workflows/ci.yml` 包含：
- **ruff lint** — 代码风格 + 安全检查（S/B 系列规则）
- **bandit** — 安全漏洞扫描
- **mypy** — 类型检查（--ignore-missing-imports）
- **pytest** — smoke test（required）+ full test（continue-on-error）
- **check-references** — 自动拦截 Skill references 与根 references 漂移
