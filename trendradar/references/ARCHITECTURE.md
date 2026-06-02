<!-- version: 2.9.0 | consolidated: 2026-05-27 -->

# TrendRadar 架构

---

## 1. 系统概述

TrendRadar 是一个多 RSS 源聚合管道，负责抓取、分类、精选、翻译、渲染并推送每日新闻简报到企业微信。管道由 `pipeline_orchestrator.py` v2.9.0 编排，按 cron 调度运行（`0 9,12,21 * * *`）。

### 管道流程

```
pipeline_orchestrator.py (v2.9.0 — 一键式 7 阶段)
  ① push_slot_detect → ② push_prepare(抓取+精选) → ③ ai_translate
  → ④ render_markdown → ⑤ fragment_push (UTF-8 字节计数分片) → ⑥ record_fingerprints (Storage 统一接入)
  → 输出 JSON: {status, fragments, briefing, stats, needs_deep_analysis}
```

---

## 2. 脚本导入架构

### 裸导入问题

脚本之前使用裸导入如 `from settings import ...` — 当执行 `python scripts/xxx.py` 时正常（sys.path 自动添加 scripts/），但作为模块导入时（`python -c "import trendradar.scripts.xxx"`）会报 `ModuleNotFoundError`。

### 修复：完全限定导入

```python
# ❌ 裸导入
from settings import get_logger
from heat_tracker import make_fingerprint

# ✅ 完全限定导入
from trendradar.scripts.settings import get_logger
from trendradar.scripts.heat_tracker import make_fingerprint
```

### 验证命令

```bash
# 检查残留的裸导入
grep -rn "^from \(settings\|heat_tracker\|fetch_feeds\) \|^import \(heat_tracker\|fetch_feeds\)" \
  ~/.hermes/trendradar/scripts/*.py | grep -v "from trendradar" | grep -v __pycache__

# 验证所有模块导入正确
cd ~/.hermes/trendradar
for mod in push_prepare ai_translate render_markdown fragment_push \
  curate_and_push track_events record_fingerprints heat_tracker fetch_feeds \
  push_slot_detect blog_watcher_bridge render_deep_analysis pipeline_orchestrator; do
  PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0 /usr/local/bin/python3.14t \
    -c "import trendradar.scripts.$mod" && echo "✅ $mod" || echo "❌ $mod"
done
```

- 2026-05-24：15 个文件全部修复。14/14 导入测试通过。
- 新脚本默认使用完全限定导入。以 `pipeline_orchestrator.py` 为参考实现。

---

## 3. 分类管道架构

### 双关键词集陷阱

| 位置 | 变量 | 用途 | 词数 |
|------|------|------|------|
| `fetch_feeds.py::_kw_sets()` | — | 抓取预分类 | ~130（子集） |
| `curate_and_push.py::_config()` | — | 精选主分类 | ~505（全集） |

`_preclassify()` 将 `_likely_domain` 写入原始 JSON。如果两个集合不同步，原始 JSON 中会有大量 `other`。**修改 `_kw()` 时必须同步更新 `_kw_sets()`**。

### 分类管道（curate_all）

```
foreach item:
  1. foreign_china: src_is_foreign ∧ china_hit  → foreign_china
  2. gaming:       src∈GAME_SRC ∨ game_kw_hit  → gaming
  3. junk:         junk_kw_hit                  → _drop=True
  4. headline:     safety_kw ∨ politics_kw      → headline
  5. tech:         tech_kw_hit                  → tech
  6. economy:      economy_kw_hit               → economy
  7. 回退（按来源分类）：
     news    → headline
     game    → gaming
     tech    → tech
     economy → economy
     无匹配   → _drop=True
```

### 关键设计决策

**回退路由**：`_all_source_category()` 按来源分类路由。`news` 分类来源（联合早报、澎湃等 12 个来源）→ `headline`，与安全/政治类条目竞争 top-10。

**politics 特殊处理**：124 个政治关键词路由到 `headline`，但不在 `_kw_sets()` 中 — 抓取预分类标记为 `other`，精选阶段通过政治关键词正确路由。绝不将政治词加入经济词集。

### 信源覆盖审计陷阱

`blind_spot_audit.py` 只查看已精选的 JSON。MAX_PER_DOMAIN 会导致活跃来源在精选数据中显示为零但在原始数据中正常。**真正的死源 = 原始数据为零**。2026-05-21 审计：报告 18 个死亡 → 实际仅 4 个真死亡（已删除），35 个活跃。

---

## 4. 关键词架构（v4.7 — 505 词，6 个领域）

双位置维护：`config/keywords.py::KEYWORDS`（全集，v4.7 — 505 词，6 个领域）/ `fetch_feeds.py::_kw_sets()`（约 150 词子集，仅 game/tech/economy）

| 领域 | 数量 | 语言 |
|------|------|------|
| game | 131 | 中/英/日 |
| tech | 87 | 中/英 |
| economy | 94 | 中/英 |
| politics | 124 | 中/英 |
| safety | 31 | 中 |
| junk | 38 | 中 |

### game（131 词）
zh: 游戏, 独立游戏, 原神, 黑神话, 塞尔达, 艾尔登法环, 博德之门, 魔兽, 暴雪, 使命召唤, 我的世界, 评测, 游戏版号, 米哈游, 崩坏, 星穹铁道, 绝区零, 机核, 触乐, 主机, 手游, 掌机, 索尼, 任天堂
en: Game/GTA/Steam/Epic/Switch/Xbox/PlayStation/PS5/Nintendo/MOD/DLC/FPS/RPG/3A/Genshin/Elden Ring/Dark Souls/Baldur's Gate/HoYoverse/Honkai/Star Rail/Zenless/ZZZ/GameLook/Famitsu/Steam Deck/Game Pass/Monster Hunter/Final Fantasy/esports/tournament/MMO/MOBA/roguelike/soulslike/JRPG/Unreal Engine/Unity/remaster/remake/Early Access/beta/Twitch/Gamescom
ja: ゲーム, ファミ通, 4Gamer, 発売, 配信, リリース, レビュー, 体験版, アップデート, ゲーム機, スクエニ, カプコン, バンナム, セガ, コナミ, フロム, アトラス, モンハン, ドラクエ, ファイナルファンタジー

### tech（87 词）
zh: AI, 大模型, 芯片, 半导体, 英伟达, GPU, CPU, 手机, 操作系统, 苹果, 华为, 特斯拉, 自动驾驶, 机器人, 电动汽车, 云计算, 5G, 开源, 编程
en: ChatGPT, LLM, AMD, Meta, Google, Nvidia, Intel, Apple, Samsung, Microsoft, Tesla, semiconductor, chip, foundry, SpaceX, NASA, cryptocurrency, blockchain, Bitcoin, cybersecurity, ransomware, startup, SaaS, cloud, API, open source, Kubernetes, Docker, GitHub

### economy（94 词）
zh: 就业, 消费, 工资, 物价, CPI, 房价, 裁员, 社保, GDP, 财政, 税收, 养老金, 贸易, 进出口, 贷款, 融资, 农业, 物流, 制造
en: employment, unemployment, layoff, inflation, interest rate, Federal Reserve, housing market, trade war, tariff, supply chain, recession, GDP growth, commodity, energy crisis, manufacturing, poverty

### politics（124）/ safety（31）
politics en: Trump, Biden, Putin, Xi Jinping, Zelensky, Ukraine, Russia, Taiwan, Israel, Gaza, North Korea, Iran, NATO, EU, election, sanctions, war, missile, military, Pentagon, UN, G7, G20, BRICS
politics zh: 访华, 会见, 外交, 中美, 中俄, 北约, 联合国, 制裁, 习近平, 总理, 欧盟, 美国, 日本, 韩国, 印度, 乌克兰, 俄罗斯, 选举, 战争, 冲突, 军演, 航天
safety: 纯中文 31 词（灾害/安全类别）

### 扩展原则
1. 先运行 `blind_spot_audit.py` + 检查原始 `other` 领域
2. 避免泛词（不加入 `studio`/`発表`/`sales` 等跨行业词）
3. 双语配对，日文发行商使用缩写
4. 修改 `_kw()` 时同步 `_kw_sets()`
5. politics 永不进入 `_kw_sets()`，由 `curate_all()` 处理

---

## 5. 脚本渲染架构

### 为什么使用脚本渲染

基于 LLM 的渲染（`render_briefing.py`）已被纯脚本渲染替代：

| 维度 | LLM 渲染 | 脚本渲染 |
|------|----------|----------|
| 速度 | ~9s（5 路并行 API） | ~0s |
| Token 成本 | 每次运行消耗 API 费用 | 零 |
| 格式一致性 | 依赖 LLM 提示遵循度 | 硬编码，100% 可靠 |
| 用户投诉 | 频繁（空行问题） | 无 |

### 脚本

**`render_markdown.py`** — 读取精选后的 JSON → 按渲染格式规范直接格式化 Markdown。
- 无 API 调用，零 token 成本
- 摘要截断至 120 字符，以句号边界感知方式裁切
- 空行规则硬编码（无 LLM 漂移）
- 输出兼容 `fragment_push.py`

**`render_deep_analysis.py`** — 从 stdin 读取 Pro 子 agent 输出 → 格式化为企业微信移动端友好格式。
- 去除表格/代码块/水平线（企业微信不支持）
- 按关键词检测章节标题 → 添加 emoji（📈🎯📌⚡）
- 自动截断至 1600 字符（企业微信单条消息限制）
- 保留自然段落分隔

| 场景 | 渲染器 |
|------|--------|
| 每日简报（早/午/晚） | `render_markdown.py`（始终） |
| 深度分析（晚间 Pro agent） | `render_deep_analysis.py`（始终） |
| LLM 回退 | 不需要 — 脚本覆盖所有情况 |

---

## 6. Render Markdown 内部机制

**位置**：`/home/asus/.hermes/trendradar/scripts/render_markdown.py`

替代 `render_briefing.py`（已删除）。将精选后的 JSON 直接渲染为企业微信 Markdown。Cron 引用必须使用此脚本名 — 绝不回退到已删除的旧名称。

优势：
- 速度：~0s（对比 LLM ~9s）
- 成本：零 token（对比 LLM API 消耗）
- 格式：100% 一致，无 LLM 输出漂移

格式契约（7 条铁律）存储在脚本的 docstring 中。任何格式修改必须先更新 docstring 再改代码。

---

## 7. 编排器可靠性说明

### fragment_push 输出解析
`fragment_push.py` 将 JSON 数组写入 stdout，日志写入 stderr。但在某些环境下日志可能泄漏到 stdout。编排器查找第一行以 `[` 开头、以 `]` 结尾的行作为 JSON，忽略其余内容。解析失败时，回退到单片段模式（整份简报作为一条消息）。

### ThreadPoolExecutor 并行阶段
（batch_fetch 已从管线移除，ai_translate 为串行阶段。）

### NEW_COUNT 检测
编排器从 push_prepare 的 stdout 解析 `NEW_COUNT=N` 用于统计追踪。

---

## 8. 数据库迁移机制

### 架构

`trendradar/migrations/` 目录管理 SQLite schema 版本：

```
migrations/
├── __init__.py
├── runner.py        # 迁移引擎（约 50 行 SQLite 引擎）
└── 001_initial.sql  # fingerprints + heat_tracker + 5 个索引
```

### 替代的代码

迁移引擎统一了 2 处分散的 CREATE TABLE 位置：

| 原始位置 | 替代方案 |
|----------|----------|
| `heat_tracker.py:init_db()` | 调用 `settings.ensure_db_migrated(DB_PATH)` |
| `health_check.py:auto_repair_missing_table()` | 调用 `migrations.runner.migrate(db)` |

### 工作原理
1. `_migrations` 表记录已应用的版本
2. 启动时扫描 `migrations/*.sql`，按文件名前缀版本号排序
3. 仅应用版本号大于当前版本的 SQL 文件
4. 幂等性：已应用的迁移会被跳过

### 添加新迁移

创建 `migrations/002_xxx.sql` 包含新字段/索引 DDL：

```sql
-- 002_add_emotion.sql
ALTER TABLE heat_tracker ADD COLUMN emotion_score REAL DEFAULT 0.0;
ALTER TABLE heat_tracker ADD COLUMN emotion_label TEXT DEFAULT '';
```

Runner 自动检测并执行 — 无需修改业务代码。

### 验证
```bash
cd ~/.hermes/trendradar
PYTHONPATH=/home/asus/.hermes python3 -c "
from scripts.settings import ensure_db_migrated
ver = ensure_db_migrated()
print(f'Schema version: v{ver}')
"
```

---

## 9. 健康检查设计

### 运行方式
Cron `c987a2883174`，每日 15:00，no_agent=true，静默运行。
脚本：`~/.hermes/scripts/trendradar_health_check.py`

### 静默设计
- 正常 → stdout 为空 → 不推送
- 异常 → stdout = Markdown → 推送到企业微信

### 检查项（14 项）

| # | 功能 | 检查内容 | 自动修复 |
|---|------|----------|----------|
| 1 | check_db | fingerprints 表 | ✅ migrate() |
| 2 | check_db | heat_tracker 表 | ✅ migrate() |
| 3 | check_db | DB 非零字节 | ✅ 删除空壳文件 |
| 4 | check_scripts | 18 个核心脚本存在 | ❌ |
| 5 | check_config | YAML+JSON+keywords.py 完整性 | ❌ |
| 6 | check_settings_constants | DOMAINS/DOMAIN_LABELS/BRIEFING_RATIO 等 | ❌ |
| 7 | check_cron | 7 个 job ID 全部已注册 | ❌ |
| 8 | check_gateway | IPC socket + hermes wecom 进程 | ❌ |
| 9 | check_data_freshness | 精选数据 < 15h | ❌ |
| 10 | check_api | deepseek + 互联网出口可达 | ❌ |
| 11 | check_stale_processes | 所有 cron job ID 的僵尸进程 | ❌ |
| 12 | check_memory_size | MEMORY/USER 使用率（>75% 警告） | ❌ |
| 13 | check_push_log_backpressure | push_log.json 大小（100KB/1MB） | ❌ |
| 14 | check_pipeline | slot_detect+RSS 连通性+导入+步骤完整性 | ❌ |
| 15 | _check_system_resources | 磁盘使用率（≥90% 告警） | ❌ |

### 7 个 Cron Job ID

| ID | 名称 | 类型 |
|----|------|------|
| `c987a2883174` | 自动健康检查 | no_agent |
| `90a2866775df` | 每日简报推送 | LLM |
| `68db70cd8556` | 每日维护 | no_agent |
| `cab79825520e` | 推送看门狗 | no_agent |
| `718b663e8c04` | 性能优化器 | LLM |
| `c20e2c82deda` | 周报推送 | LLM |
| `0b14c67429ba` | 月报 | LLM |

### 自动修复
- `auto_repair_missing_table()` — 调用 `migrate()` 重建 fingerprint/heat 表
- `auto_repair_empty_db()` — 删除 0 字节 DB 文件
- 迁移引擎幂等安全，版本记录到 `_migrations` 表

### Python 解释器注意事项

所有子进程调用（push_slot_detect、导入检查）必须使用管道的 python3.14t，而非系统 python3：

```python
pipeline_python = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')
if not os.access(pipeline_python, os.X_OK):
    pipeline_python = sys.executable  # 回退
penv = os.environ.copy()
penv['PYTHONPATH'] = str(TR.parent)     # /home/asus/.hermes
penv.setdefault('PYTHON_GIL', '0')
subprocess.run([pipeline_python, ...], env=penv)
```

系统 python3 缺少 `feedparser`、`zstandard` 等库（仅安装在 python3.14t 上）→ 导入检查会误报。

### 历史
- v1.0：20 项，含内存警告
- v1.1：移除内存检查（桌面阈值不合适），12h 指纹，精选新鲜度 6h→15h，新增全链检查
- v2.0：15 项，新增 settings 常量 / push_log 容量 / 磁盘资源 / 7 个 cron ID

---

## 10. API 退避 + 熔断器（可复用模式）

`ai_translate.py` 的 DeepSeek API 调用使用此模式，适用于所有 LLM API 集成。

### 配置常量

```python
RETRY_BASE_DELAY = 2.0        # 初始等待秒数
RETRY_MAX_DELAY = 30.0        # 上限秒数
RETRY_JITTER = 0.5            # ±50% 随机抖动
RETRY_MAX_ATTEMPTS = 4        # 最多 5 次尝试（初始 + 4 次重试）
CIRCUIT_BREAKER_THRESHOLD = 3  # 连续 3 次批量失败 → 熔断
```

### 退避算法

```
attempt 0: 无延迟（首次尝试）
attempt 1: base * 2^0 = 2s   ± 50% 抖动 → 1-3s
attempt 2: base * 2^1 = 4s   ± 50% 抖动 → 2-6s
attempt 3: base * 2^2 = 8s   ± 50% 抖动 → 4-12s
attempt 4: base * 2^3 = 16s  ± 50% 抖动，上限 30s → 8-24s
```

每次重试超时增加 30s（流中断可能需要更长的等待时间）。

### 熔断器

模块级计数器 `_translate_failures`：
- 每批次成功 → 重置为 0
- 每批次失败 → +1
- 达到 CIRCUIT_BREAKER_THRESHOLD → `circuit_broken()` 返回 True → 跳过所有剩余批次
- 手动重置：`reset_circuit()`

### 使用模式

```python
for batch in batches:
    if circuit_broken():
        skip_remaining()  # 不浪费 API 配额
    try:
        result = await call_api()
        reset_circuit()   # 成功时重置
    except Exception:
        increment_failures()
```

### 适配陷阱
- Jitter 使用 `random.random() * 2 - 1` 实现 ±50%，绝不使用固定的 `* 0.5`
- asyncio 中的模块级计数器不需要锁（Python GIL 保护单字节码操作）
- 熔断器阈值应 = 并发批次数（如 5 个并发 → threshold=5），否则 3 个并发失败不会触发熔断
