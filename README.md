# TrendRadar 📡

> **v5.7.0** — 多源 RSS 聚合 + AI 策展 + flash/Pro 深度分析 → 企业微信日/周/月报。含自动体检、偏好收敛、编排器一键管线、全链路安全加固、CI 持续集成。

> 📖 **[从零搭建指南 → SETUP.md](SETUP.md)** — 从 Hermes Agent 全新安装到测试部署一站完成。

TrendRadar 是一个三层结构的新闻聚合与智能推送系统：**日报**（多 RSS 源，早/午/晚三段）、**周报**（每周一深度趋势研判）、**月报**（每月初聚合分析）。底层共享同一套多源异步抓取管线、AC 自动机分类引擎和 `pipeline_orchestrator.py` 编排器。

---

## 推送体系

### 🌅 日报 — 编排器一键管线，日推 3 次

```
pipeline_orchestrator.py（一键6阶段）
  ① slot检测 → ② fetch+curate → ③ 并行(翻译+全文抓取) → ④ 脚本渲染 → ⑤ 分片 → ⑥ 指纹记录
  → 输出 JSON → auto-delivery → WeCom
  [晚间] 追加 3×flash delegate_task 深度分析
```

| 时段 | 时间 | 条数 | 特点 |
|------|------|------|------|
| 🌅 早报 | 09:00 | 30 | 全天精选 |
| 🌤️ 午间速递 | 12:00 | 30 | 增量去重 |
| 🌙 今日回顾 | 21:00 | 20 | 总结 + 3×flash 深度分析 |

### 📆 周报 — Pro 深度研判，每周一推送

在日报累积数据基础上，每周一 09:30 用 Pro 模型执行：

1. **数据聚合** — 聚合 7 天 curated JSON，提取跨板块趋势
2. **信息茧房突围** — 运行 `blind_spot_audit.py --days 7`，识别偏好盲区
3. **主题验证** — 每主题用 `deep-research-cli` 六步协议做网络搜索验证
4. **输出** — 五大板块 × 3-5 主题，每主题含事件链/数据/影响/展望/置信度/对立视角

### 📊 月报 — 全景复盘，每月 1 日推送

在 4 期周报数据基础上，每月 1 日 09:00 用 Pro 模型执行：

1. **三层聚合** — 近 4 周周报（叙事骨架）+ `aggregate_monthly.py`（量化统计）+ 深度搜索验证
2. **热度 Top10** — `heat_tracker` 跨源覆盖 + 热度分 + 趋势走向
3. **各板块深度** — 每板块 3-5 事件，事件链→数据→影响→展望→置信度
4. **趋势研判** — 跨域交叉 + 下月新兴话题预测

---

## 功能

- **编排器一键管线** — pipeline_orchestrator 自动编排 fetch→curate→翻译→渲染→分片→指纹，含 SSOT 自描述
- **多源异步抓取** — aiohttp 并发 + AC 自动机分类（6 域），比线性匹配快 4×
- **纯脚本渲染** — render_markdown 从 curated JSON 直接拼接，零 token 成本，格式硬编码一致
- **UTF-8 字节分片** — 三级递降拆分（段落→句子→硬切），防 WeCom 静默截断
- **日报/周报/月报** — 日报早/午/晚三段 + 晚间 3×flash 深度分析；每周一 Pro 趋势研判；每月初全景复盘
- **AI 翻译 + 中文扩写** — 外文摘要自动翻译 + 中文短摘要（<90字）AI 扩写为完整信息句
- **兴趣偏好评分** — YAML 配置正面加分/排除过滤，CLI 管理
- **来源多样性保护** — 同源 >3 条权重减半，source_health 负反馈学习环自动淘汰低质源
- **指纹去重 + 热度追踪** — MD5 指纹（48h 窗口）+ SQLite 热度持久化
- **API 熔断退避** — 翻译层指数退避 2→30s + jitter + 连续 5 失败熔断
- **发布前拦截器** — sanity_check 编排器前言剥离/中英文禁语扫描/HTML残留检测/死链检测(代理感知)/敏感词脱敏
- **自动体检 + 推送质量优化 + 看门狗** — 每日自检/评分调优/自动补投
- **CI 持续集成** — GitHub Actions：ruff lint + bandit + mypy + pytest + refs 一致性校验

---

## Skills

本系统深度集成 [Hermes Agent](https://hermes-agent.nousresearch.com)，4 个 skill 定义完整的 Agent 行为：

| Skill | 版本 | 职责 |
|-------|------|------|
| `news-secretary` | v6.22.0 | 日报推送（核心），早/午/晚三段管线 + 晚间 flash 深度分析 |
| `self-healing` | v3.6.0 | 每日 15:00 自动体检 DB/配置/API/Gateway，修复常见故障 |
| `report-generator` | v1.1.0 | 周报/月报生成，Pro 深度研判 + 全景复盘 |
| `system-config` | v2.19.0 | 项目路径/Python 环境/Cron 任务/代理配置速查 |

| 功能 | 依赖 Hermes 的组件 |
|------|-------------------|
| **推送调度** | 日报 cron（`0 9,12,21 * * *`）+ 周报 cron（`30 9 * * 1`）+ 月报 cron（`0 9 1 * *`） |
| **4 个 skill** | 上述定义，脱离 Hermes 无意义 |
| **WeCom 投递** | cron final response → Gateway auto-delivery |
| **晚间深度分析** | `delegate_task` 3×flash 子 Agent 并行 |
| **周报/月报 Pro 分析** | `delegate_task` + `deep-research-cli` 六步协议 |
| **KV 缓存共享** | Hermes KV cache（3 日报共池） |
| **自动体检** | cron no_agent 模式 + health_check 脚本 |
| **看门狗** | cron no_agent 模式 + delivery_watchdog |

> **最小独立运行**：`trendradar/scripts/` 下的 Python 脚本均可脱离 Hermes 手动执行，用于调试和数据产出。全自动推送流水线依赖 Hermes Agent cron 调度 + auto-delivery。

---

## 目录结构

```
TrendRadar/
├── .github/workflows/ci.yml       # CI 持续集成（在根目录）
├── deploy/                         # 一键部署
│   ├── hermes-scripts/             # Cron 脚本（→ $HERMES_HOME/scripts/）
│   │   ├── trendradar_health_check.py   # 自动体检
│   │   ├── trendradar_maintenance.py    # 每日备份清理
│   │   └── delivery_watchdog.py         # 推送看门狗
│   ├── prompts/                    # Cron prompt 模板
│   └── one-key-setup.sh            # 一条龙部署入口
├── skills/trendradar/              # Hermes Agent 技能（→ $HERMES_HOME/skills/trendradar/）
│   ├── news-secretary/             # 日报推送（核心技能）
│   ├── self-healing/               # 自动体检/自修复
│   ├── report-generator/           # 报告生成
│   └── system-config/              # 系统配置速查
├── trendradar/                     # Python 包（核心代码）
│   ├── scripts/                    # 管线/工具脚本（28 个）
│   │   ├── pipeline_orchestrator.py     # 一键编排器（6阶段自动管线）
│   │   ├── push_prepare.py              # fetch + curation 编排
│   │   ├── fetch_feeds.py               # 多 RSS 异步抓取
│   │   ├── curate_and_push.py           # 5 域并行精选 + 多样性惩罚
│   │   ├── ai_translate.py              # AI 批量翻译 + 熔断退避
│   │   ├── render_markdown.py           # 纯脚本渲染
│   │   ├── render_deep_analysis.py      # flash 深度分析
│   │   ├── fragment_push.py             # UTF-8 字节计数分片
│   │   ├── sanity_check.py              # 发布前拦截器
│   │   ├── blind_spot_audit.py          # 信息茧房盲点检测
│   │   ├── aggregate_monthly.py         # 月度统计
│   │   ├── record_fingerprints.py       # 指纹记录
│   │   ├── track_events.py              # 跨日事件追踪
│   │   ├── heat_tracker.py              # 热度追踪引擎
│   │   ├── push_slot_detect.py          # 推送时段检测
│   │   ├── ...                          # 见 trendradar/scripts/ 目录
│   ├── config/                    # 关键词/时段/翻译/兴趣配置
│   │   ├── sources.json           # 48+ RSS 源列表
│   │   ├── keywords.py            # AC 自动机关键词分类（505 词 × 6 域）
│   │   ├── ai_interests.yaml      # 兴趣偏好评分配置
│   │   └── timeline.yaml          # 推送时段配置
│   ├── migrations/                # SQLite 数据库迁移引擎
│   ├── references/                # 核心参考文档 + INDEX.md 索引
│   ├── tests/                     # 测试用例（146+ 用例）
│   ├── pyproject.toml             # 包定义 v5.7.0
│   └── requirements.txt           # 依赖清单
├── .gitignore
├── LICENSE
├── README.md                      # 本文件
└── SETUP.md                       # 从零搭建指南
```

---

## 快速开始

```bash
# 一条龙部署（推荐）
curl -sSL https://raw.githubusercontent.com/BedrockLian/TrendRadar/main/deploy/one-key-setup.sh | bash

# 或手动安装
git clone https://github.com/BedrockLian/TrendRadar.git ~/TrendRadar
cd ~/TrendRadar

# 安装 Python 依赖
cd trendradar && pip install -e ".[dev]"

# 配置 API Key
export DEEPSEEK_API_KEY="sk-xxx"

# 初始化数据库
python3 -c "from trendradar.migrations.runner import migrate; from pathlib import Path; migrate(Path('data/fingerprints.db'))"

# 手动跑一次日报（设置 PYTHONPATH 为 trendradar/ 的父目录）
export PYTHONPATH=/path/to/trendradar/parent
export TRENDRADAR_HOME=/path/to/runtime/dir
python3.14t -m trendradar.scripts.pipeline_orchestrator --push-id morning --output text

# 查看管道步骤
python3.14t -m trendradar.scripts.pipeline_orchestrator --list-steps

# 部署 Hermes Skills
cp -r skills/trendradar/* ~/.hermes/skills/trendradar/

# 部署 Cron 脚本
cp deploy/hermes-scripts/*.py ~/.hermes/scripts/
```

---

## 测试

```bash
# 全量测试
cd TrendRadar/trendradar && PYTHONPATH=$PWD/.. pytest tests/ -v

# 集成测试（真实管线）
cd TrendRadar/trendradar && PYTHONPATH=$PWD/.. pytest tests/ -m integration -v

# Lint + 安全扫描
cd TrendRadar && ruff check trendradar/ && bandit -r trendradar/scripts/ -s B101
```

GitHub Actions CI 在每次 push 到 `main` 时自动运行 ruff lint → 烟雾测试 → 全量测试 → references 一致性校验。

---

## 技术栈

| 层 | 技术 |
|----|------|
| 运行时 | Python 3.14 / 3.14t (free-threaded) |
| 编排 | pipeline_orchestrator.py（6阶段自动管线） |
| 异步 | asyncio / aiohttp / TaskGroup |
| 分类 | pyahocorasick (AC 自动机，505 关键词 × 6 域) |
| 存储 | SQLite (WAL + mmap) |
| AI | DeepSeek Flash / Pro API |
| 渲染 | `render_markdown.py`（纯脚本，~0s）/ `render_deep_analysis.py`（深度分析格式化） |
| 投递 | 企业微信 (WeCom) — auto-delivery |
| 调度 | Hermes Agent cron（早/午/晚 + 周报 + 月报） |
| 压缩 | zstandard (zstd) |
| CI | GitHub Actions（ruff lint + pytest smoke/test + refs 校验） |
| 文档 | 核心参考文档 + INDEX.md 索引 |

---

## 许可证

MIT 见 [LICENSE](LICENSE)
