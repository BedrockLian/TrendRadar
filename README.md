# TrendRadar 📡

> 多源 RSS 聚合 + AI 策展 → 企业微信日/周/月简报

TrendRadar 是一个轻量级新闻聚合与智能推送系统。从 39+ RSS 源和博客异步抓取内容，经 AC 自动机分类 + AI 评分后，按早/午/晚三段推送 Markdown 简报至企业微信。

---

## 目录结构

```
TrendRadar/
├── trendradar/              # 核心管线代码
│   ├── scripts/             #   20 个管线/工具脚本
│   ├── config/              #   关键词/时段/翻译/兴趣配置
│   ├── migrations/          #   SQLite 数据库迁移引擎
│   ├── skills/              #   Hermes Agent 技能定义
│   │   ├── news-secretary/       # SKILL.md + 7 个参考文档
│   │   ├── self-healing/         # SKILL.md + 4 个参考文档
│   │   └── performance-optimizer/ # SKILL.md + 2 个参考文档
│   ├── tests/               #   92 个测试用例
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── pyproject.toml
│   
├── hermes-scripts/           # 自动体检/维护脚本
│   ├── trendradar_health_check.py
│   └── trendradar_maintenance.py
├── .gitignore
├── LICENSE                   # MIT 许可证
└── README.md                  # 项目说明
```

## Pipeline

```
RSS 异步抓取 (39源) → AC 自动机分类 (5域) → AI 渲染 (5路并行,~9s) → WeCom 分片推送
```

| 时段 | 时间 | 条数 | 特点 |
|------|------|------|------|
| 🌅 早报 | 09:00 | 24 | 全天精选 |
| 🌤️ 午间速递 | 12:00 | 32 | 增量去重 |
| 🌙 今日回顾 | 21:00 | 24 | 总结 + 3×Pro 深度分析 |

## 功能

- **多源异步抓取** — aiohttp 异步并发，两级连接池（RSSHub + 外网直连）
- **AC 自动机分类** — 505 关键词 × 6 域，frozenset O(1) 查找，比线性匹配快 4.4×
- **AI 渲染** — 各板块独立 DeepSeek Flash API 调用，5 路并行，~9s
- **兴趣偏好评分** — `config/ai_interests.yaml` 定义正面+2分/排除过滤，CLI 管理
- **指纹去重** — MD5 截断指纹，48h 滑动窗口
- **热度追踪** — SQLite 持久化，跨周期频次/平台/持续时间
- **数据库迁移** — 轻量 SQLite 迁移引擎（`migrations/runner.py`），schema 版本化管理
- **结构化日志** — 统一 logging 工厂，`[timestamp] [LEVEL] [module]` 格式
- **退出码协议** — 脚本按 `exitcodes.py` 返回 0/2/3/10/11/12/99，Agent 依码决策
- **自动体检** — 每日 15:00 自检 DB/配置/API/Gateway/全链路，异常推送

## Hermes Agent 要求

本系统深度集成 [Hermes Agent](https://hermes-agent.nousresearch.com)，**脱离 Hermes 无法完全运行**。以下列出 Hermes 专属依赖：

| 功能 | 依赖 Hermes 的组件 | 如果不运行 Hermes |
|------|-------------------|------------------|
| **推送调度** | cron job（`0 9,12,21 * * *`） | 脚本可手动跑，但无定时推送 |
| **3 个 skill** | `trendradar-news-secretary`, `trendradar-self-healing`, `trendradar-performance-optimizer` | skill 是 Agent 指令集，脱离 Hermes 无意义 |
| **WeCom 投递** | `send_message(target="wecom")` + Gateway IPC socket | 无法投递到企业微信 |
| **晚间深度分析** | `delegate_task` 3×Pro 子 Agent 并行 | 晚报无深度分析板块 |
| **KV 缓存共享** | Hermes KV cache（3 日报共池） | Flash API 缓存不跨 session，token 成本上升 |
| **自动体检** | cron no_agent 模式 + health_check 脚本 | health_check.py 可单独跑，但无人接收告警 |
| **看门狗** | cron no_agent 模式 + delivery_watchdog | 推送失败无兜底告警 |

> **最小独立运行**：`trendradar/scripts/` 下的 Python 脚本（push_prepare, render_briefing, curate_and_push 等）均可脱离 Hermes 手动执行，用于调试和数据产出。但全自动推送流水线必须依赖 Hermes Agent。

## 快速开始

```bash
# 1. 安装依赖
cd trendradar && pip install -e ".[dev]"

# 2. 配置环境变量
export DEEPSEEK_API_KEY="sk-xxx"

# 3. 初始化数据库
python3 -c "from scripts.settings import ensure_db_migrated; ensure_db_migrated()"

# 4. 手动跑一次全流程
python3 scripts/push_prepare.py --push-id morning
python3 scripts/render_briefing.py --push-id morning
python3 scripts/fragment_push.py < output.md
```

## 测试

```bash
cd trendradar && pytest tests/ -v --timeout 15
# 92 passed
```

## 技术栈

| 层 | 技术 |
|----|------|
| 运行时 | Python 3.14 / 3.14t (free-threaded) |
| 异步 | asyncio / aiohttp / TaskGroup |
| 分类 | pyahocorasick (AC 自动机) |
| 存储 | SQLite (WAL + mmap) |
| AI | DeepSeek Flash / Pro API |
| 推送 | 企业微信 (WeCom) |
| 调度 | Hermes Agent cron |
| 压缩 | zstandard (zstd) |

## 许可证

MIT
