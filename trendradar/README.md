# TrendRadar 📡

> 多源 RSS 聚合 + AI 策展 → 企业微信日/周/月简报

TrendRadar 是一个轻量级新闻聚合与智能推送系统。它从 54+ 个 RSS 源和博客异步抓取内容，通过 AC 自动机分类 + AI 评分后，按早/午/晚三个时段推送 Markdown 简报至企业微信。

---

## Pipeline

```
┌─────────────┐    ┌──────────────┐    ┌───────────────┐    ┌──────────────┐
│  RSS Fetch  │ →  │  AC Classify │ →  │  Translate+ │ →  │  WeCom Push  │
│  54 sources │    │  5 domains   │    │  Render     │    │  fragmented   │
│  async/54   │    │  frozenset   │    │  script     │    │  auto-delivery│
└─────────────┘    └──────────────┘    └───────────────┘    └──────────────┘
```

## 时程

| 时段 | 时间 | 条数 | 特点 |
|------|------|------|------|
| 🌅 早报 | 09:00 | 24 | 全天精选，不含去重 |
| 🌤️ 午间速递 | 12:00 | 32 | 增量内容，含去重 |
| 🌙 今日回顾 | 21:00 | 24 | 当日总结，含去重 + 3×Pro 深度分析 |

## 功能

- **多源异步抓取** — 54 RSS/博客源，aiohttp 异步并发，两级连接池（RSSHub + 外网直连）
- **AC 自动机分类** — 505 关键词 × 6 域，frozenset O(1) 查找，比线性匹配快 4.4×
- **纯脚本渲染** — `render_markdown.py` 从 curated JSON 直接拼接，格式硬编码永远一致
- **兴趣偏好评分** — `config/ai_interests.yaml` 定义，正面 +2 分，排除项过滤
- **指纹去重** — MD5 截断指纹，48h 滑动窗口
- **热度追踪** — SQLite 持久化，跨周期追踪频次/平台覆盖/持续时间
- **结构化日志** — 统一 logging 工厂，时间戳/级别/模块三级
- **数据库迁移** — 轻量 SQLite 迁移引擎，schema 版本化管理
- **自动体检** — 每日 15:00 自检（DB/配置/API/Gateway/全链路），异常推送

## 快速开始

```bash
# 1. 环境要求
# Python 3.14+ free-threaded（可选，用于真并行）
sudo apt-get install -y libsqlite3-dev libssl-dev libbz2-dev liblzma-dev \
  libreadline-dev libncurses-dev libgdbm-dev libdb-dev libffi-dev uuid-dev

# 2. 安装依赖
pip install -e ".[dev]"

# 3. 配置
cp .env.example .env   # 填入 API Key
# 编辑 config/timeline.yaml 调整推送时段
# 编辑 config/ai_interests.yaml 设置兴趣偏好

# 4. 初始化数据库
python3 -c "from trendradar.scripts.settings import ensure_db_migrated; ensure_db_migrated()"

# 5. 手动跑一次
cd trendradar && python3 scripts/push_prepare.py --push-id morning
```

## 配置

| 文件 | 用途 |
|------|------|
| `config/keywords.py` | 6 域 505 关键词 |
| `config/timeline.yaml` | 推送时段定义 |
| `data/sources.json` | 54 个 RSS/博客源 + 语言映射（language 字段） |
| `config/ai_interests.yaml` | 兴趣偏好（LLM Agent 可自动管理） |

## 项目结构

```
trendradar/
├── config/            # 配置文件
├── migrations/        # 数据库迁移（SQLite 迁移引擎）
│   ├── runner.py      #   迁移执行引擎
│   └── 001_initial.sql  # 初始 schema
├── scripts/           # 管线脚本
│   ├── push_prepare.py      # 编排：fetch + 分类 + 精选
│   ├── fetch_feeds.py       # 54 源异步抓取
│   ├── curate_and_push.py   # AC 分类 + 评分精选
│   ├── render_markdown.py      # 纯脚本 Markdown 渲染
│   ├── fragment_push.py     # 板块分片
│   ├── ai_translate.py      # 英文摘要翻译
│   ├── heat_tracker.py      # 热度追踪
│   ├── settings.py          # 统一配置
│   ├── exitcodes.py         # 退出码协议
│   └── interest_cli.py      # 兴趣偏好管理 CLI
├── tests/             # 测试（92 用例）
│   pytest — Python 3.14, 覆盖核心管线函数
├── skills/            # Hermes Agent skill 定义
│   └── trendradar/    #   3 个协作 skill
└── pyproject.toml     # 项目元数据
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
| 异步 | asyncio / aiohttp / gather |
| 分类 | pyahocorasick (AC 自动机) |
| 存储 | SQLite (WAL + mmap) |
| AI | DeepSeek Flash / Pro API |
| 推送 | 企业微信 (WeCom) |
| 调度 | Hermes Agent cron |
| 压缩 | zstandard (zstd) |

## 许可证

MIT
