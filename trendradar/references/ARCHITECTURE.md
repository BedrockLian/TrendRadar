<!-- version: 2.8.0 | consolidated: 2026-05-27 | source: 9 docs merged -->

# TrendRadar Architecture

Consolidated from: classification-architecture.md, import-architecture.md, script-rendering.md, render-markdown.md, orchestrator-notes.md, keyword-architecture.md, migration-mechanism.md, health-check-design.md, api-backoff-circuit-breaker.md

---

## 1. System Overview

TrendRadar is a multi-RSS feed aggregation pipeline that fetches, classifies, curates, translates, renders, and pushes daily news briefings to WeCom (企业微信). The pipeline is orchestrated by `pipeline_orchestrator.py` v2.8.0 and runs on a cron schedule (`0 9,12,21 * * *`).

### Pipeline Flow

```
pipeline_orchestrator.py (v2.8.0 — one-click 7-stage)
  ① push_slot_detect → ② push_prepare(fetch+curate) → ③ parallel(ai_translate ∥ batch_fetch)
  → ④ render_markdown → ⑤ fragment_push (UTF-8 byte-counted splitting) → ⑥ record_fingerprints (Storage unified access)
  → output JSON: {status, fragments, briefing, stats, needs_deep_analysis}
```

---

## 2. Script Import Architecture

### The Bare Import Problem

Scripts previously used bare imports like `from settings import ...` — works when running `python scripts/xxx.py` (sys.path auto-adds scripts/), but fails as module import (`python -c "import trendradar.scripts.xxx"`) with `ModuleNotFoundError`.

### Fix: Fully-Qualified Imports

```python
# ❌ Bare imports
from settings import get_logger
from heat_tracker import make_fingerprint

# ✅ Fully-qualified imports
from trendradar.scripts.settings import get_logger
from trendradar.scripts.heat_tracker import make_fingerprint
```

### Verification Commands

```bash
# Check for residual bare imports
grep -rn "^from \(settings\|heat_tracker\|fetch_feeds\) \|^import \(heat_tracker\|fetch_feeds\)" \
  ~/.hermes/trendradar/scripts/*.py | grep -v "from trendradar" | grep -v __pycache__

# Verify all modules import correctly
cd ~/.hermes/trendradar
for mod in push_prepare batch_fetch ai_translate render_markdown fragment_push \
  curate_and_push track_events record_fingerprints heat_tracker fetch_feeds \
  push_slot_detect blog_watcher_bridge render_deep_analysis pipeline_orchestrator; do
  PYTHONPATH=/home/asus/.hermes PYTHON_GIL=0 /usr/local/bin/python3.14t \
    -c "import trendradar.scripts.$mod" && echo "✅ $mod" || echo "❌ $mod"
done
```

- 2026-05-24: Full fix of 15 files. 14/14 import tests pass.
- New scripts default to fully-qualified imports. `pipeline_orchestrator.py` is the reference implementation.

---

## 3. Classification Pipeline Architecture

### Dual Keyword Set Trap

| Location | Variable | Purpose | Word Count |
|----------|----------|---------|------------|
| `fetch_feeds.py::_kw_sets()` | — | fetch pre-classification | ~130 (subset) |
| `curate_and_push.py::_config()` | — | curate main classification | ~505 (full set) |

`_preclassify()` writes `_likely_domain` into raw JSON. If unsynchronized, raw JSON gets lots of `other`. **When modifying `_kw()`, must sync `_kw_sets()`**.

### Classification Pipeline (curate_all)

```
foreach item:
  1. foreign_china: src_is_foreign ∧ china_hit  → foreign_china
  2. gaming:       src∈GAME_SRC ∨ game_kw_hit  → gaming
  3. junk:         junk_kw_hit                  → _drop=True
  4. headline:     safety_kw ∨ politics_kw      → headline
  5. tech:         tech_kw_hit                  → tech
  6. economy:      economy_kw_hit               → economy
  7. Fallback (by source category):
     news    → headline
     game    → gaming
     tech    → tech
     economy → economy
     no match → _drop=True
```

### Key Design Decisions

**Fallback routing**: `_all_source_category()` routes by source category. `news` category sources (联合早报, 澎湃等 12 sources) → `headline`, competing with safety/politics items for top-10.

**politics special handling**: 124 politics keywords route to `headline` but are NOT in `_kw_sets()` — fetch pre-classification marks as `other`, curate stage correctly routes via politics keywords. Never add politics words to economy set.

### Source Coverage Audit Pitfall

`blind_spot_audit.py` only looks at curated JSON. MAX_PER_DOMAIN causes active sources to show zero in curated but normal in raw. **True dead source = raw zero**. 2026-05-21 audit: reported 18 dead → actually 4 truly dead (deleted), 35 alive.

---

## 4. Keyword Architecture (v4.7 — 505 words, 6 domains)

Dual-location maintenance: `curate_and_push.py::_kw()` (full set) / `fetch_feeds.py::_kw_sets()` (~150 word subset, only game/tech/economy)

| domain | count | languages |
|--------|-------|-----------|
| game | 131 | zh/en/ja |
| tech | 87 | zh/en |
| economy | 94 | zh/en |
| politics | 124 | zh/en |
| safety | 31 | zh |
| junk | 38 | zh |

### game (131 words)
zh: 游戏, 独立游戏, 原神, 黑神话, 塞尔达, 艾尔登法环, 博德之门, 魔兽, 暴雪, 使命召唤, 我的世界, 评测, 游戏版号, 米哈游, 崩坏, 星穹铁道, 绝区零, 机核, 触乐, 主机, 手游, 掌机, 索尼, 任天堂
en: Game/GTA/Steam/Epic/Switch/Xbox/PlayStation/PS5/Nintendo/MOD/DLC/FPS/RPG/3A/Genshin/Elden Ring/Dark Souls/Baldur's Gate/HoYoverse/Honkai/Star Rail/Zenless/ZZZ/GameLook/Famitsu/Steam Deck/Game Pass/Monster Hunter/Final Fantasy/esports/tournament/MMO/MOBA/roguelike/soulslike/JRPG/Unreal Engine/Unity/remaster/remake/Early Access/beta/Twitch/Gamescom
ja: ゲーム, ファミ通, 4Gamer, 発売, 配信, リリース, レビュー, 体験版, アップデート, ゲーム機, スクエニ, カプコン, バンナム, セガ, コナミ, フロム, アトラス, モンハン, ドラクエ, ファイナルファンタジー

### tech (87 words)
zh: AI, 大模型, 芯片, 半导体, 英伟达, GPU, CPU, 手机, 操作系统, 苹果, 华为, 特斯拉, 自动驾驶, 机器人, 电动汽车, 云计算, 5G, 开源, 编程
en: ChatGPT, LLM, AMD, Meta, Google, Nvidia, Intel, Apple, Samsung, Microsoft, Tesla, semiconductor, chip, foundry, SpaceX, NASA, cryptocurrency, blockchain, Bitcoin, cybersecurity, ransomware, startup, SaaS, cloud, API, open source, Kubernetes, Docker, GitHub

### economy (94 words)
zh: 就业, 消费, 工资, 物价, CPI, 房价, 裁员, 社保, GDP, 财政, 税收, 养老金, 贸易, 进出口, 贷款, 融资, 农业, 物流, 制造
en: employment, unemployment, layoff, inflation, interest rate, Federal Reserve, housing market, trade war, tariff, supply chain, recession, GDP growth, commodity, energy crisis, manufacturing, poverty

### politics (124) / safety (31)
politics en: Trump, Biden, Putin, Xi Jinping, Zelensky, Ukraine, Russia, Taiwan, Israel, Gaza, North Korea, Iran, NATO, EU, election, sanctions, war, missile, military, Pentagon, UN, G7, G20, BRICS
politics zh: 访华, 会见, 外交, 中美, 中俄, 北约, 联合国, 制裁, 习近平, 总理, 欧盟, 美国, 日本, 韩国, 印度, 乌克兰, 俄罗斯, 选举, 战争, 冲突, 军演, 航天
safety: zh-only 31 words (disaster/safety category)

### Expansion Principles
1. Run `blind_spot_audit.py` first + check raw `other` domain
2. Avoid generic words (no `studio`/`発表`/`sales` cross-industry words)
3. Bilingual pairing, use abbreviations for JP publishers
4. When modifying `_kw()`, sync `_kw_sets()`
5. politics never enters `_kw_sets()`, handled by `curate_all()`

---

## 5. Script Rendering Architecture

### Why Script Rendering

LLM-based rendering (`render_briefing.py`) was replaced with pure-script rendering:

| Dimension | LLM Rendering | Script Rendering |
|-----------|--------------|-----------------|
| Speed | ~9s (5× parallel API) | ~0s |
| Token cost | API cost per run | Zero |
| Format consistency | Dependent on LLM prompt adherence | Hardcoded, 100% reliable |
| User complaints | Frequent (empty line issues) | None |

### Scripts

**`render_markdown.py`** — Reads curated JSON → directly formats markdown per render-format spec.
- No API calls, zero token cost
- Summaries truncated at 150 chars with sentence-boundary-aware cutoff
- Empty line rules hardcoded (no LLM drift)
- Output compatible with `fragment_push.py`

**`render_deep_analysis.py`** — Reads Pro subagent output from stdin → formats for WeCom mobile.
- Strips tables/code blocks/horizontal rules (unsupported by WeCom)
- Detects section headings by keyword → adds emoji (📈🎯📌⚡)
- Auto-truncates at 1600 chars (WeCom single-message limit)
- Preserves natural paragraph breaks

| Scenario | Renderer |
|----------|----------|
| Daily briefing (morning/noon/evening) | `render_markdown.py` (always) |
| Deep analysis (evening Pro agents) | `render_deep_analysis.py` (always) |
| LLM-based fallback | Not needed — script covers all cases |

---

## 6. Render Markdown Internals

**Location**: `/home/asus/.hermes/trendradar/scripts/render_markdown.py`

Replaces `render_briefing.py` (deleted). Renders curated JSON directly to WeCom markdown. Cron references MUST use this script name — never fall back to deleted old names.

Advantages:
- Speed: ~0s (vs LLM ~9s)
- Cost: zero tokens (vs LLM API consumption)
- Format: 100% consistent, no LLM output drift

The format contract (7 iron rules) is stored in the script's docstring. Any format change must update the docstring before changing code.

---

## 7. Orchestrator Reliability Notes

### fragment_push Output Parsing
`fragment_push.py` writes JSON array to stdout, logs to stderr. But logs may leak to stdout in some environments. Orchestrator finds the first line starting with `[` and ending with `]` as JSON, ignores rest. On failure, falls back to single fragment (entire briefing as one message).

### ThreadPoolExecutor for Parallel Stage
`ai_translate` and `batch_fetch` run in parallel via `concurrent.futures.ThreadPoolExecutor(max_workers=2)`. This is in-process parallelism (not subprocess), so both share GIL state. With `PYTHON_GIL=0` (python3.14t), no GIL contention.

### NEW_COUNT Detection
The orchestrator parses `NEW_COUNT=N` from push_prepare stdout for stats tracking.

---

## 8. Database Migration Mechanism

### Architecture

`trendradar/migrations/` directory manages SQLite schema versions:

```
migrations/
├── __init__.py
├── runner.py        # Migration engine (~50 line SQLite engine)
└── 001_initial.sql  # fingerprints + heat_tracker + 5 indices
```

### Replaced Code

Migration engine unifies 2 scattered CREATE TABLE locations:

| Original location | Replacement |
|-------------------|-------------|
| `heat_tracker.py:init_db()` | Calls `settings.ensure_db_migrated(DB_PATH)` |
| `health_check.py:auto_repair_missing_table()` | Calls `migrations.runner.migrate(db)` |

### How It Works
1. `_migrations` table records applied versions
2. On startup, scans `migrations/*.sql`, sorted by filename prefix version number
3. Only applies SQL files with version > current version
4. Idempotent: already-applied migrations are skipped

### Adding New Migrations

Create `migrations/002_xxx.sql` with new field/index DDL:

```sql
-- 002_add_emotion.sql
ALTER TABLE heat_tracker ADD COLUMN emotion_score REAL DEFAULT 0.0;
ALTER TABLE heat_tracker ADD COLUMN emotion_label TEXT DEFAULT '';
```

Auto-detected and executed by runner — no business code changes needed.

### Verification
```bash
cd ~/.hermes/trendradar
PYTHONPATH=/home/asus/.hermes python3 -c "
from scripts.settings import ensure_db_migrated
ver = ensure_db_migrated()
print(f'Schema version: v{ver}')
"
```

---

## 9. Health Check Design

### Operation
Cron `c987a2883174`, daily 15:00, no_agent=true, silent.
Script: `~/.hermes/scripts/trendradar_health_check.py`

### Silent Design
- Normal → stdout empty → no push
- Abnormal → stdout = Markdown → push to WeCom

### Checks (14 items)

| # | Function | Check | Auto-repair |
|---|----------|-------|-------------|
| 1 | check_db | fingerprints table | ✅ migrate() |
| 2 | check_db | heat_tracker table | ✅ migrate() |
| 3 | check_db | DB non-zero-byte | ✅ delete empty shell |
| 4 | check_scripts | 18 core scripts exist | ❌ |
| 5 | check_config | YAML+JSON+keywords.py integrity | ❌ |
| 6 | check_settings_constants | DOMAINS/DOMAIN_LABELS/BRIEFING_RATIO etc | ❌ |
| 7 | check_cron | 7 job IDs all registered | ❌ |
| 8 | check_gateway | IPC socket + hermes wecom process | ❌ |
| 9 | check_data_freshness | curated < 15h | ❌ |
| 10 | check_api | deepseek + internet egress reachable | ❌ |
| 11 | check_stale_processes | Stale processes for all cron job IDs | ❌ |
| 12 | check_memory_size | MEMORY/USER usage (>75% warn) | ❌ |
| 13 | check_push_log_backpressure | push_log.json size (100KB/1MB) | ❌ |
| 14 | check_pipeline | slot_detect+RSS connectivity+import+step integrity | ❌ |
| 15 | _check_system_resources | Disk usage (≥90% alert) | ❌ |

### 7 Cron Job IDs

| ID | Name | Type |
|----|------|------|
| `c987a2883174` | Auto health check | no_agent |
| `90a2866775df` | Daily briefing push | LLM |
| `68db70cd8556` | Daily maintenance | no_agent |
| `cab79825520e` | Push watchdog | no_agent |
| `718b663e8c04` | Performance optimizer | LLM |
| `c20e2c82deda` | Weekly report push | LLM |
| `0b14c67429ba` | Monthly report | LLM |

### Auto-repair
- `auto_repair_missing_table()` — calls `repair_missing_tables()` + `migrate()` to rebuild fingerprint/heat tables
- `auto_repair_empty_db()` — deletes 0-byte DB files
- Migration engine is idempotent-safe, records version to `_migrations` table

### Python Interpreter Notes

All subprocess calls (push_slot_detect, import checks) MUST use pipeline's python3.14t, not system python3:

```python
pipeline_python = os.environ.get('PYTHON', '/usr/local/bin/python3.14t')
if not os.access(pipeline_python, os.X_OK):
    pipeline_python = sys.executable  # fallback
penv = os.environ.copy()
penv['PYTHONPATH'] = str(TR.parent)     # /home/asus/.hermes
penv.setdefault('PYTHON_GIL', '0')
subprocess.run([pipeline_python, ...], env=penv)
```

System python3 lacks `feedparser`, `zstandard` etc. only installed on python3.14t → import check false positives.

### History
- v1.0: 20 items, with memory warning
- v1.1: Removed memory check (desktop thresholds inappropriate), 12h fingerprint, curated freshness 6h→15h, added full chain check
- v2.0: 15 items, added settings constants / push_log volume / disk resources / 7 cron IDs

---

## 10. API Backoff + Circuit Breaker (Reusable Pattern)

`ai_translate.py`'s DeepSeek API calls use this pattern, applicable to all LLM API integrations.

### Configuration Constants

```python
RETRY_BASE_DELAY = 2.0        # Initial wait seconds
RETRY_MAX_DELAY = 30.0        # Cap seconds
RETRY_JITTER = 0.5            # ±50% random jitter
RETRY_MAX_ATTEMPTS = 4        # Max 5 attempts (initial + 4 retries)
CIRCUIT_BREAKER_THRESHOLD = 3  # 3 consecutive batch failures → trip
```

### Backoff Algorithm

```
attempt 0: no delay (first try)
attempt 1: base * 2^0 = 2s   ± 50% jitter → 1-3s
attempt 2: base * 2^1 = 4s   ± 50% jitter → 2-6s
attempt 3: base * 2^2 = 8s   ± 50% jitter → 4-12s
attempt 4: base * 2^3 = 16s  ± 50% jitter, capped at 30s → 8-24s
```

Each retry timeout increases by 30s (stream drops may need longer wait).

### Circuit Breaker

Module-level counter `_translate_failures`:
- Each batch success → reset to 0
- Each batch failure → +1
- Reaches CIRCUIT_BREAKER_THRESHOLD → `circuit_broken()` returns True → skip all remaining batches
- Manual reset: `reset_circuit()`

### Usage Pattern

```python
for batch in batches:
    if circuit_broken():
        skip_remaining()  # Don't waste API quota
    try:
        result = await call_api()
        reset_circuit()   # Reset on success
    except Exception:
        increment_failures()
```

### Adaptation Traps
- Jitter uses `random.random() * 2 - 1` for ±50%, never fixed `* 0.5`
- Module-level counter in asyncio doesn't need locks (Python GIL protects single bytecode ops)
- Circuit breaker threshold should = concurrent batch count (e.g., 5 concurrent → threshold=5), otherwise 3 concurrent failures won't trigger
