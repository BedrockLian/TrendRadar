# TrendRadar 知识图谱 —— 完整代码分析

> 分析时间: 2026-05-23
> 项目版本: v5.5.0
> 文件总数: 35 Python 文件 + 3 YAML 配置 + 1 SQL 迁移
> 测试覆盖: 92 用例, pytest + asyncio, 5 测试文件

---

## 一、项目概要

TrendRadar 是一个轻量级多源 RSS 聚合 + AI 策展系统，从 39+ 个源异步抓取内容，
经 AC 自动机分类 + AI 评分后，按早/午/晚三个时段推送 Markdown 简报至企业微信。

**技术栈**: Python 3.14/3.14t (free-threaded), asyncio/aiohttp, pyahocorasick, SQLite (WAL+mmap), DeepSeek API, 企业微信

---

## 二、架构全景图

```
┌──────────────────────────────────────────────────────────────────────┐
│                         TRENDRADAR v5.5.0                            │
│                    Pipeline Architecture                              │
├───────────────┬───────────────┬───────────────┬──────────────────────┤
│  PHASE 1      │  PHASE 2      │  PHASE 3      │  PHASE 4             │
│  Fetch        │  Curation     │  Render       │  Push                │
├───────────────┼───────────────┼───────────────┼──────────────────────┤
│ fetch_feeds   │ curate_and    │ ai_translate  │ fragment_push        │
│ (39RSS async) │ _push (AC分类 │ (批量英译中)  │ (WeCom分片)          │
│               │  +评分精选)   │               │                      │
│ blog_watcher  │              │ render_md     │ record_fingerprints  │
│ _bridge (博客)│              │ (纯脚本渲染)  │ (去重指纹)           │
│               │              │               │                      │
│ batch_fetch   │              │ render_deep   │ heat_tracker         │
│ (全文抓取)    │              │ _analysis     │ (热度追踪)           │
│               │              │ (Pro深度分析) │                      │
├───────────────┴───────────────┴───────────────┴──────────────────────┤
│  ORCHESTRATOR: push_prepare.py                                      │
│  入口脚本，编排 fetch + blog + curation 流程，一键完成              │
├─────────────────────────────────────────────────────────────────────┤
│  SCHEDULER DETECTION: push_slot_detect.py                           │
│  读取 timeline.yaml，检测当前时段 (早09:00/午12:00/晚21:00)          │
├─────────────────────────────────────────────────────────────────────┤
│  CROSS-DAY ANALYSIS: track_events.py                                │
│  跨日热度比对，标记新事件/热度上升/事件进展/热度下降                │
├─────────────────────────────────────────────────────────────────────┤
│  HEALTH CHECK: (每日15:00 自检: DB/配置/API/Gateway/全链路)         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 三、模块依赖关系图

```
settings.py (统一配置中心)
  ├── exitcodes.py         [退出码协议]
  ├── common.py            [追溯号+上下文]
  │   └── trace.py         [contextvars 传播]
  ├── storage.py           [存储抽象层 — 待集成]
  └── config/keywords.py   [505关键词×6域 AC自动机]
      ├── GAME_KW (33中文+23英文+12日文 = 68)
      ├── TECH_KW (29中文+24英文 = 53)
      ├── ECONOMY_KW (28中文+22英文 = 50)
      ├── SAFETY_KW (21中文+21英文 = 42)
      ├── POLITICS_KW (27中文+26英文 = 53)
      └── JUNK_KW (21中文+9英文 = 30)
          总计: ~296 去重后 505 关键词

fetch_feeds.py (244行)
  ├── settings (API配置, 连接池参数)
  ├── config/keywords (has_keyword_match_ci)
  ├── aiohttp (TaskGroup 并发)
  ├── feedparser (RSS/Atom/RDF解析)
  ├── InterpreterPoolExecutor/ThreadPoolExecutor (CPU密集解析)
  └── heat_tracker (热度追踪集成)
      ├── _dedup()           [跨平台去重合并 title[:40] + URL domain]
      ├── _preclassify()     [关键词+源category预分类]
      ├── _kw_sets()         [lru_cache 关键词集]
      └── _source_category_map() [源→category 映射]

curate_and_push.py (322行)
  ├── settings (评分参数, domain配置)
  ├── config/keywords (ALL_KEYWORDS, has_keyword_match)
  ├── config/ai_interests.yaml (兴趣偏好 ±2分)
  └── heat_tracker (热度查询)
      ├── _score()            [清晰度+权威度+时效性+唯一性+热度评分]
      ├── _classify_items()   [主分类引擎: 头条/外媒/domain/垃圾]
      ├── _score_headlines()  [头条单独评分排序]
      ├── _curate_domain()    [单domain精选+排序]
      └── _curate_sections()  [非头条domain组装]
      + 大量 @lru_cache(maxsize=1) 缓存: _config/_sources/_authority/
        _game_sources/_econ_boost/_econ_extra/_foreign_sources/
        _load_interests/_china_kw/_source_domain/_all_source_category

push_prepare.py (231行) — 编排器
  ├── fetch_feeds
  ├── blog_watcher_bridge (subprocess 调用)
  ├── curate_and_push
  └── ThreadPoolExecutor(2) 并行 fetch + blog
      ├── ensure_raw_exists()  [缓存有效≤4h跳过, 否则触发fetch]
      ├── load_blog_articles() [加载blog缓存+指纹去重]
      ├── run_curation()       [主编排: 并行fetch+blog → 合并 → curate]
      ├── strip_curated()      [精简输出: title/summary[:120]/source/url]
      ├── get_today_fingerprints() [查询今日指纹]
      └── count_new_items()    [统计新增条数(title[:20]匹配)]

ai_translate.py (413行)
  ├── settings (API密钥/端点)
  ├── aiohttp (async HTTP)
  ├── CJK检测 (_is_cjk, cjk_ratio: 覆盖10个Unicode范围)
  └── DeepSeek API (批量翻译, 20条/批, 5路并发)
      ├── _load_and_scan()    [加载+扫描需翻译条目]
      ├── _batch_translate_all() [并发批次翻译]
      ├── batch_translate()    [单批翻译: 构建prompt→API调用→解析]
      └── _write_back()       [写入curated JSON + dated副本]

heat_tracker.py (338行)
  ├── settings (HEAT_* 参数)
  ├── SQLite (WAL+mmap, per-thread连接)
  └── 指纹生成 (MD5+trucante 16位+URL特征)
      ├── make_fingerprint()    [标题+CJK保留+URL域/路径]
      ├── update_tracker()      [批量更新热度表]
      ├── get_heat_info()       [批量查询热度数据]
      └── _calc_heat()          [热度评分: 频次+跨度+平台+趋势]

blog_watcher_bridge.py (246行)
  ├── blogwatcher-cli (外部进程 scan --unsafe-client)
  ├── blogwatcher-cli.db (文章查询)
  └── fingerprints.db (今日去重)
      ├── scan_blogs()         [调用外部CLI扫描]
      ├── fetch_blog_articles() [查DB+指纹去重+标记已读]
      ├── _map_domain()        [category关键词→TrendRadar domain映射]
      └── write_cache()        [写入 raw_blogs.json 供 push_prepare 消费]

batch_fetch.py (178行)
  ├── aiohttp (10并发直连抓取)
  ├── curl 兜底 (subprocess)
  ├── charset-normalizer (编码检测)
  └── Docker代理检测 (_proxy_alive)
      ├── _decode()            [8种编码枚举+charset-normalizer+latin-1兜底]
      ├── fetch_aiohttp()      [主抓取通道]
      └── fetch_curl()         [兜底抓取通道]

render_markdown.py (132行) — 纯脚本，零LLM成本
  ├── settings (DOMAINS, DOMAIN_LABELS, SLOT_NAMES)
  └── curated JSON 输入
      ├── _detect_emoji()      [热度emoji: 🔥/🆕/📌]
      ├── _format_item()       [3行块格式: emoji+标题/摘要/链接]
      ├── _generate_section()  [domain区块]
      └── render()             [主渲染: 标题+5区块+尾注]

fragment_push.py (99行)
  └── stdin markdown → JSON fragments
      └── split_fragments()    [按 ### 分片, 标题仅首片, 尾注仅末片]

render_deep_analysis.py (87行)
  └── stdin Pro分析 → WeCom格式化
      ├── clean()              [去代码块/表格/HTML/空行]
      └── format_analysis()    [段落+emoji映射, 截断1600字]

record_fingerprints.py (85行)
  └── fingerprints.db 写入
      └── record()             [INSERT OR IGNORE 批量写入指纹]

push_slot_detect.py (67行)
  └── timeline.yaml → 时段检测 (±1分钟容差, fallback 10分钟)

track_events.py (168行)
  ├── heat_tracker (make_fingerprint)
  └── 跨日 curated JSON 比对
      ├── compare()            [新事件/热度上升/事件进展/热度下降/消失]
      └── find_yesterday_morning() [自动找昨日早报]

interest_cli.py (106行)
  └── ai_interests.yaml CRUD
      ├── list/add/remove/exclude 命令

migrations/runner.py (50行)
  └── 轻量 SQLite 迁移引擎 (无 Alembic)
      └── migrate()            [版本追踪+增量迁移]

storage.py (54行) — ✅ API就绪，尚未集成
  └── 统一文件读写抽象 (JSON/文本/DB/清理)

trace.py (17行) — contextvars RUN_ID 自动传播
common.py (39行) — 追溯号生成/解析/WeCom标记
exitcodes.py (8行) — 退出码协议 (0/2/3/10/11/12/99)
```

---

## 四、数据流全景

```
                   ┌─────────────────┐
                   │  cron / Hermes  │
                   │  Agent Scheduler│
                   └────────┬────────┘
                            │
                   ┌────────▼────────┐
                   │ push_slot_      │ 读取 timeline.yaml
                   │ detect.py       │ → PUSH_ID=morning|noon|evening
                   └────────┬────────┘
                            │
                   ┌────────▼────────┐
                   │ push_prepare.py │ 编排器
                   │ run_curation()  │
                   └───┬───────┬─────┘
                       │       │
          ┌────────────▼─┐  ┌──▼──────────────┐
          │fetch_feeds.py│  │blog_watcher_     │
          │39源异步抓取  │  │bridge.py         │
          │aiohttp       │  │blogwatcher-cli   │
          │TaskGroup     │  │+ SQLite 查询     │
          └──────┬───────┘  └──┬──────────────┘
                 │              │
          ┌──────▼──────┐  ┌───▼───────┐
          │raw_{date}.json│ │raw_blogs. │
          │(cache/)      │  │json(cache)│
          └──────┬───────┘  └───┬───────┘
                 │              │
                 └──────┬───────┘
                        │ merge
                 ┌──────▼──────┐
                 │curate_and_  │
                 │push.py      │
                 │AC分类+评分  │
                 │5 domain     │
                 └──────┬──────┘
                        │
          ┌─────────────┼─────────────┐
          │             │             │
   ┌──────▼──────┐ ┌───▼──────┐ ┌───▼──────────┐
   │heat_tracker │ │record_   │ │curated_{slot} │
   │.py          │ │finger-   │ │.json (data/)  │
   │SQLite热度表│ │prints.py │ │+ dated副本    │
   └─────────────┘ │去重指纹  │ └───┬──────────┘
                   └──────────┘     │
                          ┌─────────▼─────────┐
                          │ ai_translate.py   │
                          │ 英→中 批量翻译    │
                          │ 20条/批 5路并发   │
                          └────────┬──────────┘
                                   │
                          ┌────────▼─────────┐
                          │ render_markdown   │
                          │ .py              │
                          │ 纯脚本渲染       │
                          │ (零LLM成本)      │
                          └────────┬─────────┘
                                   │
                          ┌────────▼─────────┐
                          │ fragment_push.py │
                          │ 分片 (### 分割)  │
                          │ → JSON fragments │
                          └────────┬─────────┘
                                   │
                          ┌────────▼─────────┐
                          │ WeCom 推送       │
                          │ 1.5s 间隔        │
                          │ + trace marker   │
                          └──────────────────┘
```

---

## 五、核心算法

### 5.1 综合评分算法 (_score)
```
total = clarity + authority + recency + uniqueness + heat + interest_bonus

clarity:   1 (含?或<10字) | 2 (>40字) | 3 (10~40字)
authority: base(from sources.json, default=1) + 1(economy+高权威源)
recency:   3 (<1h) | 2 (<6h) | 1 (<24h) | 0 (≥24h)
           blog内容保底: recency=0→1
uniqueness: 3 (含[续]/[新]/[更新]) | 2 (有URL) | 1 (无URL)
heat:      3 (coverage≥4 或 coverage≥2+hits≥2)
         | 2 (coverage≥3 或 hits≥2)
         | 1 (coverage≥2 或 hits≥1)
         | 0
interest:  +2 (正面关键词命中) | 0 (排除项命中→过滤)

PASS条件: total >= MIN_SCORE (6) 且 recency > 0
```

### 5.2 热度评分算法 (_calc_heat)
```
freq_score  = min(appearance_count/10, 1.0) × 3
span_score  = min(span_hours/48, 1.0) × 2
plat_score  = min(platform_count/10, 1.0) × 3
trend_bonus = 1.0 (rising) | 0.5 (stable) | 0 (fading)
heat_score  = round(freq_score + span_score + plat_score + trend_bonus, 1)

趋势判定: 比较最近两次 signal 的 coverage + heat_words
- recent > prev → rising
- recent < prev → falling
- recent = prev → stable

持续性标记:
- is_deep: fetch_cycles ≥ 3 且 span_hours ≥ 12 → 深度追踪
- is_sustained: fetch_cycles ≥ 2 或 span_hours ≥ 6 → 持续关注
- is_new: fetch_cycles ≤ 1 且 span_hours < 1 → 新出现
```

### 5.3 指纹生成 (make_fingerprint)
```
1. title.lower().strip()
2. 保留 CJK + 片假名/平假名 + 字母数字
3. 加入 URL 域名 + 前3段路径防碰撞 (日语源如4Gamer)
4. MD5 → 截取前16位
```

### 5.4 去重策略
```
fetch层: title[:40].lower() + URL domain → 跨平台合并
         (保留 coverage_count, coverage_platforms)
blog层: title[:40].lower() in 今日指纹set → 跳过
         (但保留未读状态，供后续时段)
推送层: fingerprints表 INSERT OR IGNORE (MD5 16位)
         48h 滑动窗口 status: active→dormant
```

---

## 六、分类体系 (AC 自动机)

### 6.1 6域关键词分布
```
GAME_KW:    68 关键词 (33中文 + 23英文 + 12日文)
TECH_KW:    53 关键词 (29中文 + 24英文)
ECONOMY_KW: 50 关键词 (28中文 + 22英文)
SAFETY_KW:  42 关键词 (21中文 + 21英文)
POLITICS_KW:53 关键词 (27中文 + 26英文)
JUNK_KW:    30 关键词 (21中文 + 9英文)
----------------------------------------------
总计: 296 个 (去重后 505，部分跨域共享)
```

### 6.2 分类优先级
```
1. foreign_china: 外媒 + 中国关键词 (且非游戏源) → 最高优先
2. gaming:       游戏源 或 游戏关键词命中
3. junk:         垃圾关键词 → 丢弃(_drop=True)
4. headline:     safety/politics → 头条域
5. tech:         tech关键词命中
6. economy:      economy关键词命中
7. fallback:    源配置 category 兜底 (news→头条, game→gaming, tech→tech, economy→economy)
8. 兜底:        _drop=True (无法分类的丢弃)
```

### 6.3 AC自动机加速
```
pyahocorasick Automaton:
- has_keyword_match():     精确/大小写敏感匹配
- has_keyword_match_ci():  大小写不敏感 (lowercase both)
- 线性匹配回退: any(k in text for k in kw_set)
- 加速比: 4.4× vs 线性匹配 (README声称)
```

---

## 七、数据库 Schema

### 7.1 fingerprints 表
```sql
fingerprint     TEXT PRIMARY KEY  -- MD5 16位
title           TEXT
summary         TEXT
source_platform TEXT
url             TEXT
push_id         TEXT              -- morning/noon/evening
push_time       TEXT
created_at      TEXT
run_id          TEXT DEFAULT ''   -- 追溯号
索引: idx_fp_push_time, idx_fp_url
```

### 7.2 heat_tracker 表
```sql
fingerprint      TEXT PRIMARY KEY  -- MD5 16位
title            TEXT NOT NULL
first_seen       TIMESTAMP
last_seen        TIMESTAMP
appearance_count INTEGER DEFAULT 1
fetch_cycles     INTEGER DEFAULT 1
platforms        TEXT DEFAULT '[]'  -- JSON array
platform_count   INTEGER DEFAULT 1
heat_signals     TEXT DEFAULT '[]'  -- JSON array of signal objects
domain           TEXT DEFAULT ''
status           TEXT DEFAULT 'active'  -- active/dormant
rank_history     TEXT DEFAULT '[]'  -- JSON array
索引: idx_heat_status, idx_heat_last_seen,
      idx_heat_platform_count, idx_heat_status_lastseen,
      idx_heat_status_platcount
```

### 7.3 迁移引擎 (_migrations 表)
```sql
version    INTEGER PRIMARY KEY
applied_at TEXT
```

---

## 八、配置体系

### 8.1 环境变量
```
TRENDRADAR_HOME          → 项目根目录 (默认 ~/.hermes/trendradar)
TRENDRADAR_API_KEY_ENV   → API Key 环境变量名 (默认 DEEPSEEK_API_KEY)
TRENDRADAR_API_ENDPOINT_ENV → API 端点环境变量名
TRENDRADAR_MODEL_ENV     → 模型名环境变量名 (默认 DEEPSEEK_MODEL)
TRENDRADAR_DEFAULT_ENDPOINT → 默认端点
TRENDRADAR_DEFAULT_MODEL → 默认模型 (deepseek-chat)
TRENDRADAR_LOG_LEVEL     → 日志级别 (默认 INFO)
TRENDRADAR_ENV           → .env 文件路径
```

### 8.2 可调参数 (settings.py)
```
连接池: RSSHUB_CONCURRENT=12, EXTERNAL_CONCURRENT=20, TIMEOUT_SEC=6
评分:   MIN_SCORE=6, RECENCY_HOURS_HIGH=1, RECENCY_HOURS_MID=6, RECENCY_HOURS_LOW=24
热度:   HEAT_SLEEP_HOURS=24, HEAT_DEEP_CYCLES=3, HEAT_DEEP_SPAN=12
       HEAT_SUSTAINED_CYCLES=2, HEAT_SUSTAINED_SPAN=6
指纹:   FINGERPRINT_MD5_LEN=16, FINGERPRINT_URL_SEGMENTS=3, FINGERPRINT_TITLE_TRUNCATE=40
限制:   DAILY_LIMIT=80, BRIEFING_RATIO={morning:24, noon:32, evening:24}
搜索:   SEARCH_RATIO=0.6 (前60%条目标记 _needs_search)
```

### 8.3 时段配置 (timeline.yaml)
```
morning:  09:00, filter=keyword, dedup=false, 24条
noon:     12:00, filter=keyword, dedup=false, 32条
evening:  21:00, dedup=true, 24条 + 3×Pro深度分析
```

---

## 九、测试覆盖

### 9.1 测试文件 (5文件, 92用例)
```
tests/test_push_prepare.py       → 编排流程 (count_new_items, strip_item 等)
tests/test_curate_and_push.py    → 分类评分 (关键词验证, 评分算法, 分类逻辑)
tests/test_fetch_feeds.py        → RSS抓取 (源配置, 解析, 去重, 预分类)
tests/test_heat_tracker.py       → 热度追踪 (指纹, 更新, 查询, 状态)
tests/test_ai_translate.py       → 翻译 (CJK检测, 批量翻译)
tests/test_record_and_common.py  → 记录+公共工具 (指纹记录, 追溯号)
tests/test_push_slot_detect.py   → 时段检测
tests/test_batch_fetch.py        → 批量抓取
tests/conftest.py                → 共享 fixtures (tmp_db, sample_curated)
```

### 9.2 Pytest 配置
```
pytest-asyncio, pytest-timeout (15s/30s)
Markers: smoke(CI必须), slow(可选), integration(需外部依赖)
pythonpath: [.] → 直接 import 项目模块
```

---

## 十、退出码协议

```
EXIT_SUCCESS       = 0   # 成功有产出
EXIT_NO_CONTENT    = 2   # 无新内容 (正常, 不告警)
EXIT_PARTIAL       = 3   # 部分成功 (部分源失败, 推送降级)
EXIT_CONFIG_ERROR  = 10  # 配置错误 (需人工介入)
EXIT_API_ERROR     = 11  # API 不可达 (自动重试)
EXIT_DB_ERROR      = 12  # 数据库损坏 (触发自愈)
EXIT_FATAL         = 99  # 致命错误 (停止管线)
```

---

## 十一、性能特征

### 11.1 并发模型
```
RSS抓取:    asyncio.TaskGroup (Python 3.11+ 原生)
            Semaphore: RSSHub 12路 + 外网 20路
            TCP连接池: limit=40, per_host=10
            总超时: 6s/源, 最多3次重试

CPU解析:    InterpreterPoolExecutor(max_workers=12) Python 3.14
            → 真并行 feedparser (无GIL)
            降级: ThreadPoolExecutor

翻译:       asyncio.gather + Semaphore(5)
            20条/批, 5路并发
            总超时: 120s/批, 最多3次重试

curation:   frozenset O(1) 查找 (分类/评分)
            AC自动机 加速关键词匹配
            大量 @lru_cache(maxsize=1) 缓存

batch_fetch: 10并发 aiohttp + curl兜底 + ThreadPoolExecutor
```

### 11.2 存储优化
```
SQLite:     WAL模式 + mmap(256MB) + cache_size(32MB)
            busy_timeout=5000ms
zstd压缩:   compression.zstd (stdlib) → zstandard → JSON fallback
            压缩比 ~1/6
原子写入:   tempfile + os.replace (防止写坏)
```

---

## 十二、代码质量特征

### 12.1 良好实践
- 统一配置中心 (settings.py) 避免硬编码
- 结构化日志工厂 (get_logger) 按模块复用
- 退出码协议供 Agent 决策
- 追溯号系统 (RUN_ID) 贯穿全链
- 原子写入 (atomic_write_json)
- zstd 压缩带 fallback
- 迁移引擎版本化管理
- per-thread SQLite 连接 (WAL 线程安全)

### 12.2 待改进点
- storage.py 标注 "API就绪, 尚未集成" — 各脚本仍有直接文件IO
- common.py 和 trace.py 存在 duplicated contextvars (两处定义 current_run_id)
- 部分脚本用 `from settings import ...` 而非常规 `from trendradar.scripts.settings import ...` (依赖 sys.path 操作)
- ai_translate.py 413行过大，可进一步拆分
- 部分异常处理使用 `except Exception` 过于宽泛

---

## 十三、文件清单

```
trendradar/
├── config/
│   ├── keywords.py          (182行) 505关键词 + AC自动机
│   ├── timeline.yaml        (23行)  推送时段

│   ├── ai_interests.yaml    (12行)  兴趣偏好
│   └── __init__.py          (空)
├── migrations/
│   ├── runner.py            (50行)  SQLite迁移引擎
│   ├── 001_initial.sql      (36行)  初始schema
│   └── __init__.py          (空)
├── scripts/
│   ├── push_prepare.py      (231行) 管线编排器 ★
│   ├── fetch_feeds.py       (254行) RSS异步抓取 ★
│   ├── curate_and_push.py   (322行) AC分类+评分精选 ★
│   ├── ai_translate.py      (413行) 批量英译中 ★
│   ├── render_markdown.py   (132行) 纯脚本Markdown渲染
│   ├── render_deep_analysis.py (87行) Pro深度分析格式化
│   ├── fragment_push.py     (99行)  WeCom分片
│   ├── heat_tracker.py      (338行) 热度追踪 ★
│   ├── batch_fetch.py       (178行) 批量全文抓取
│   ├── blog_watcher_bridge.py (246行) 博客桥接
│   ├── record_fingerprints.py (85行) 指纹记录
│   ├── track_events.py      (168行) 跨日事件跟踪
│   ├── push_slot_detect.py  (67行)  时段检测
│   ├── interest_cli.py      (106行) 兴趣管理CLI
│   ├── settings.py          (224行) 统一配置 ★
│   ├── common.py            (39行)  追溯号生成
│   ├── trace.py             (17行)  contextvars传播
│   ├── storage.py           (54行)  存储抽象 [待集成]
│   ├── exitcodes.py         (8行)   退出码协议
│   └── __init__.py          (空)
├── tests/
│   ├── conftest.py          (100行) 共享fixtures
│   ├── test_push_prepare.py
│   ├── test_curate_and_push.py
│   ├── test_fetch_feeds.py
│   ├── test_heat_tracker.py
│   ├── test_ai_translate.py
│   ├── test_record_and_common.py
│   ├── test_push_slot_detect.py
│   ├── test_batch_fetch.py
│   └── __init__.py          (空)
├── pyproject.toml           (43行)  项目元数据
├── requirements.txt         (10行)  运行依赖
├── requirements-dev.txt     (9行)   开发依赖
├── README.md                (120行) 项目文档
└── .gitignore               (26行)
```

★ = 核心模块 (>200行)

**总行数**: ~3,500行 Python + 120行 Markdown + 120行配置/YAML/SQL

---

## 十四、运行管线命令

```bash
# 完整流程 (手动)
cd ~/.hermes/trendradar

# 1. 检测时段
python3 scripts/push_slot_detect.py
# → PUSH_ID=morning

# 2. 编排抓取+精选
python3 scripts/push_prepare.py --push-id morning

# 3. 翻译英文摘要
python3 scripts/ai_translate.py --push-id morning

# 4. 渲染 Markdown
python3 scripts/render_markdown.py --push-id morning

# 5. 分片推送
python3 scripts/render_markdown.py --push-id morning | python3 scripts/fragment_push.py

# 6. 记录指纹
python3 scripts/record_fingerprints.py --push-id morning

# 晚间 Pro 深度分析 (可选)
cat analysis.txt | python3 scripts/render_deep_analysis.py --topic "AI · 科技趋势"

# 跨日事件跟踪
python3 scripts/track_events.py --today curated_morning_20260523.json

# 兴趣偏好管理
python3 scripts/interest_cli.py list
python3 scripts/interest_cli.py add "量子计算突破"
python3 scripts/interest_cli.py exclude "娱乐八卦"
```
