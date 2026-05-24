# TrendRadar 📡

> 多源 RSS 聚合 + AI 策展 + Pro 深度分析 → 企业微信日/周/月报。含自动体检、偏好收敛、编排器一键管线。

> 📖 **[从零搭建指南 → SETUP.md](SETUP.md)** — 从 Hermes Agent 全新安装到测试部署一站完成。

TrendRadar 是一个三层结构的新闻聚合与智能推送系统：**日报**（多 RSS 源，早/午/晚三段）、**周报**（每周一深度趋势研判）、**月报**（每月初聚合分析）。底层共享同一套多源异步抓取管线、AC 自动机分类引擎和 `pipeline_orchestrator.py` 编排器。

---

## 推送体系

### 🌅 日报 — 编排器一键管线，日推 3 次

```
pipeline_orchestrator.py（一键6阶段）
  ① slot检测 → ② fetch+curate → ③ 并行(翻译+全文抓取) → ④ 脚本渲染 → ⑤ 分片 → ⑥ 指纹记录
  → 输出 JSON → auto-delivery → WeCom
  [晚间] 追加 3×Pro delegate_task 深度分析
```

| 时段 | 时间 | 条数 | 特点 |
|------|------|------|------|
| 🌅 早报 | 09:00 | 30 | 全天精选 |
| 🌤️ 午间速递 | 12:00 | 30 | 增量去重 |
| 🌙 今日回顾 | 21:00 | 20 | 总结 + 3×Pro 深度分析 |

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

- **编排器一键管线** — `pipeline_orchestrator.py` 替代 10 步手动操作，6 阶段自动编排，输出 JSON 结果
- **多源异步抓取** — aiohttp 异步并发，两级连接池（RSSHub + 外网直连）
- **AC 自动机分类** — 505 关键词 × 6 域，frozenset O(1) 查找，比线性匹配快 4.4×
- **纯脚本渲染** — `render_markdown.py` 从 curated JSON 直接拼接，~0s，零 token 成本，格式硬编码永远一致
- **auto-delivery 投递** — cron 中 `send_message` 已弃用，全部通过 final response 系统自动投递 WeCom
- **日报推送** — 早/午/晚三段 Flash 管线，晚间附加 3×Pro 深度分析
- **周报研判** — 每周一 Pro 模型深度趋势分析，含信息茧房突围
- **月报分析** — 每月初全景复盘，聚合 4 周数据 + heat_tracker Top10
- **兴趣偏好评分** — `config/ai_interests.yaml` 定义正面+2分/排除过滤，CLI 管理
- **指纹去重** — MD5 截断指纹，48h 滑动窗口
- **热度追踪** — SQLite 持久化，跨周期频次/平台/持续时间
- **数据库迁移** — 轻量 SQLite 迁移引擎（`migrations/runner.py`），schema 版本化管理
- **结构化日志** — 统一 logging 工厂，`[timestamp] [LEVEL] [module]` 格式
- **退出码协议** — 脚本按 `exitcodes.py` 返回 0/2/3/10/11/12/99，Agent 依码决策
- **自动体检** — 每日 15:00 自检 DB/配置/API/Gateway/全链路，异常推送
- **推送质量优化** — 每日 21:15 评分 + 偏好收敛调优
- **推送降级看门狗** — 每日 3 次巡检 WeCom IPC socket + 投递错误检测

## Hermes Agent 要求

本系统深度集成 [Hermes Agent](https://hermes-agent.nousresearch.com)，**脱离 Hermes 无法完全运行**。

| 功能 | 依赖 Hermes 的组件 | 如果不运行 Hermes |
|------|-------------------|------------------|
| **推送调度** | 日报 cron（`0 9,12,21 * * *`）+ 周报 cron（`30 9 * * 1`）+ 月报 cron（`0 9 1 * *`） | 脚本可手动跑，但无定时推送 |
| **6 个 skill** | `news-secretary`, `self-healing`, `performance-optimizer`, `system-config`, `weekly-report`, `monthly-report` | skill 是 Agent 指令集，脱离 Hermes 无意义 |
| **WeCom 投递** | cron final response → Gateway auto-delivery | 脱离 Hermes 无法接收推送 |
| **晚间深度分析** | `delegate_task` 3×Pro 子 Agent 并行 | 晚报无深度分析板块 |
| **周报/月报 Pro 分析** | `delegate_task` + `deep-research-cli` 六步协议 | 无深度研判，仅数据聚合 |
| **KV 缓存共享** | Hermes KV cache（3 日报共池） | Flash API 缓存不跨 session |
| **自动体检** | cron no_agent 模式 + health_check 脚本 | health_check.py 可单独跑，但无人接收告警 |
| **看门狗** | cron no_agent 模式 + delivery_watchdog | 推送失败无兜底告警 |

> **最小独立运行**：`trendradar/scripts/` 下的 Python 脚本均可脱离 Hermes 手动执行，用于调试和数据产出。全自动推送流水线依赖 Hermes Agent cron 调度 + auto-delivery。

## 目录结构

```
TrendRadar/
├── trendradar/              # 核心 Python 包
│   ├── scripts/             #   管线/工具脚本
│   │   ├── pipeline_orchestrator.py     # 一键编排器（6阶段自动管线）
│   │   ├── push_prepare.py             # fetch + curation 编排
│   │   ├── fetch_feeds.py              # 多 RSS 异步抓取
│   │   ├── curate_and_push.py          # 5 域并行精选
│   │   ├── ai_translate.py             # AI 批量翻译
│   │   ├── batch_fetch.py              # 10 并发全文抓取
│   │   ├── render_markdown.py          # 纯脚本 Markdown 渲染
│   │   ├── render_deep_analysis.py     # Pro 深度分析格式化
│   │   ├── fragment_push.py            # WeCom 分片
│   │   ├── record_fingerprints.py      # 指纹记录
│   │   ├── track_events.py             # 跨日事件追踪
│   │   ├── heat_tracker.py             # 热度追踪引擎
│   │   └── ... (settings, common, exitcodes, 等)
│   ├── config/              #   关键词/时段/翻译/兴趣配置
│   ├── migrations/          #   SQLite 数据库迁移引擎
│   ├── skills/              #   Hermes Agent 技能定义（6个）
│   │   ├── news-secretary/           # 日报推送（核心，v6.0）
│   │   ├── self-healing/             # 自动体检/自修复（v3.0）
│   │   ├── performance-optimizer/    # 推送质量优化（v2.3）
│   │   ├── system-config/            # 系统配置速查（v2.0）
│   │   ├── weekly-report/            # 周报深度研判（v2.2）
│   │   └── monthly-report/           # 月报全景分析（v2.2）
│   ├── references/           #   运行时参考文档
│   ├── tests/               #   92 个测试用例
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── pyproject.toml
├── hermes-scripts/           # 自动体检/维护/看门狗脚本
│   ├── trendradar_health_check.py     # 每日自动体检（15项检查）
│   ├── trendradar_maintenance.py      # 每日备份清理
│   └── delivery_watchdog.py           # 推送降级看门狗
├── .gitignore
├── LICENSE
├── README.md
└── SETUP.md
```

## 快速开始

```bash
# 1. 安装依赖
cd trendradar && pip install -e ".[dev]"

# 2. 配置环境变量
export DEEPSEEK_API_KEY="sk-xxx"

# 3. 初始化数据库
python3 -c "from scripts.settings import ensure_db_migrated; ensure_db_migrated()"

# 4. 手动跑一次日报（编排器模式）
export PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0
python3.14t scripts/pipeline_orchestrator.py --push-id morning --output text

# 5. 或分步跑
python3 scripts/push_prepare.py --push-id morning
python3 scripts/render_markdown.py --push-id morning
```

## 测试

```bash
cd trendradar && pytest tests/ -v --timeout 15
```

## 技术栈

| 层 | 技术 |
|----|------|
| 运行时 | Python 3.14 / 3.14t (free-threaded) |
| 编排 | pipeline_orchestrator.py（6阶段自动管线） |
| 异步 | asyncio / aiohttp / TaskGroup |
| 分类 | pyahocorasick (AC 自动机) |
| 存储 | SQLite (WAL + mmap) |
| AI | DeepSeek Flash / Pro API |
| 渲染 | `render_markdown.py`（纯脚本，~0s） / `render_deep_analysis.py`（深度分析格式化） |
| 投递 | 企业微信 (WeCom) — auto-delivery（send_message 已弃用于 cron） |
| 调度 | Hermes Agent cron |
| 压缩 | zstandard (zstd) |

## 许可证

MIT 见 [LICENSE](LICENSE)
