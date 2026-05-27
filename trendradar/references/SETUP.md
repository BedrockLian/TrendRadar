<!-- version: 2.8.0 | consolidated: 2026-05-27 | source: 9 docs merged -->

# TrendRadar Setup & Operations

Consolidated from: proxy-config.md, rsshub-proxy-setup.md, cache-cleanup.md, cron-operations.md, migration-rollback.md, cron-prompt-canonical.md, cron-sendmessage-fallback.md, sources-management.md, sources-format.md

---

## 1. Proxy Configuration

TrendRadar v5.5.0+ supports **automatic proxy routing**: domestic RSS sources go direct, foreign sources route through Mihomo (127.0.0.1:7890).

### Architecture

```
RSS fetch (fetch_feeds.py)
  ├─ Domestic sources (anyfeeder.com / .cn)   → direct session
  └─ Foreign (BBC/NYT/RSSHub etc.)             → proxy session (PROXY_URL)
                                                     ↓
                                               Mihomo 127.0.0.1:7890

Article details (batch_fetch.py)
  └─ Auto-detect 127.0.0.1:7890 reachability
       ├─ Reachable → proxy for foreign full-text
       └─ Not reachable → direct fallback
```

### Core Configuration

| Config | Location | Notes |
|--------|----------|-------|
| `PROXY_URL` | `scripts/settings.py` | Default `http://127.0.0.1:7890`, overridable via `TRENDRADAR_PROXY` env |
| `needs_proxy()` | `scripts/settings.py` | Determines if RSS source needs proxy |
| `DOMESTIC_PROXY_PATTERNS` | `scripts/settings.py` | Domestic domain whitelist |

### Traffic Routing

| Category | Typical Sources | Route |
|----------|----------------|-------|
| Domestic direct | 爱范儿, 虎嗅, 机核, 澎湃, 钛媒体, 联合早报 | Direct |
| RSSHub proxy | Reuters/中国新闻网/半月谈/游民星空/触乐/日经亚洲/少数派 | Mihomo |
| Foreign direct proxy | BBC/NYT/Guardian/SCMP/PC Gamer/4Gamer/NHK/Japan Times | Mihomo |

### Proxy Unreachable Consequences

- `fetch_feeds.py`: Foreign + RSSHub sources all fail → daily report has only domestic content
- `batch_fetch.py`: Auto-degrades to direct (curl fallback), foreign full-text may not be fetched
- `self-healing`'s `check_api` item detects if internet egress is reachable

### Mihomo Listen Config (Docker-accessible)

```yaml
# ~/.config/mihomo/config.yaml
port: 7890
socks-port: 7891
allow-lan: true
bind-address: "0.0.0.0"
mode: rule
```

Restart after config change: `systemctl --user restart mihomo.service`
Verify: `ss -tlnp | grep 7890` should show `*:7890` not `127.0.0.1:7890`

### Proxy Troubleshooting

```bash
# 1. Is Mihomo running?
systemctl --user status mihomo.service

# 2. Is port listening?
ss -tlnp | grep 7890

# 3. Test proxy routing for a specific source
python3 -c "from scripts.settings import needs_proxy; print('needs proxy:', needs_proxy('https://feeds.bbci.co.uk/news/rss.xml'))"

# 4. Docker → mihomo connectivity
curl -s -o /dev/null -w "HTTP %{http_code} (%{time_total}s)" --max-time 5 \
  -x http://172.30.21.131:7890 http://www.gstatic.com/generate_204
```

---

## 2. RSSHub Docker Proxy Setup

RSSHub container needs proxy to access foreign sources (Reuters, Nikkei Asia, etc.). Node.js 24's built-in HTTP client (undici) does NOT auto-read `HTTP_PROXY`/`HTTPS_PROXY` env vars — requires manual `EnvHttpProxyAgent` injection.

### Build Image

```bash
# 1. Start original RSSHub
docker run -d --name rsshub --restart always -p 1200:1200 \
  --add-host host.docker.internal:172.30.21.131 \
  -e NODE_ENV=production -e TZ=Asia/Shanghai \
  diygod/rsshub

# 2. Install CA certs (container lacks them → HTTPS fails)
docker exec rsshub apt-get update -qq
docker exec rsshub apt-get install -y -qq ca-certificates

# 3. Create proxy preload script
docker exec rsshub sh -c 'cat > /app/proxy-fix.mjs << "EOF"
import undici from "undici";
const proxyUrl = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
if (proxyUrl) {
  const agent = new undici.EnvHttpProxyAgent();
  globalThis[Symbol.for("undici.globalDispatcher.1")] = agent;
}
EOF'

# 4. Commit as new image
docker commit rsshub rsshub-final
docker stop rsshub && docker rm rsshub
```

### Start Container

```bash
docker run -d --name rsshub --restart always -p 1200:1200 \
  --add-host host.docker.internal:172.30.21.131 \
  -e HTTP_PROXY=http://host.docker.internal:7890 \
  -e HTTPS_PROXY=http://host.docker.internal:7890 \
  -e NO_PROXY=localhost,127.0.0.1 \
  -e NODE_ENV=production -e TZ=Asia/Shanghai \
  rsshub-final \
  dumb-init -- node --max-http-header-size=32768 \
    --import /app/proxy-fix.mjs dist/index.mjs
```

### Trap Checklist

1. **npm run start clobbers NODE_OPTIONS**: `npm run start` internally uses `cross-env` which resets `NODE_OPTIONS`. Use `node dist/index.mjs` directly.
2. **host.docker.internal IP changes**: WSL restart changes NIC IP. Update `--add-host` accordingly.
3. **Container lacks CA certs**: Default `diygod/rsshub` (Debian slim) has no CA certs → HTTPS fails. Install `ca-certificates`.
4. **proxychains4 incompatible with Node.js 24**: undici uses new async I/O → TLS fails mid-handshake. Don't use proxychains4.
5. **redsocks transparent proxy also fails**: Same undici I/O path issue.

### Verification

```bash
# Route test
for r in reuters/business reuters/technology reuters/world/china nikkei/asia; do
  echo -n "$r: "
  curl -s -o /dev/null -w "HTTP %{http_code} (%{time_total}s)\n" --max-time 10 "http://localhost:1200/$r"
done

# Domestic baseline
curl -s -o /dev/null -w "HTTP %{http_code} (%{time_total}s)" --max-time 8 http://localhost:1200/sspai/index
```

---

## 3. Cache Cleanup Procedures

Execute in priority order, check disk freed after each step.

### Steps

```bash
# 1. TrendRadar old cache
cd ~/.hermes/trendradar/cache
rm -f raw_$(date -d yesterday +%Y%m%d).json batch_*.json

# 2. __pycache__ (exclude venv)
find ~/.hermes -path "*/venv/*" -prune -o -name __pycache__ -type d -exec rm -rf {} +

# 3. pip cache
pip cache purge  # Usually frees 10-14MB

# 4. apt cache
sudo apt-get clean
sudo apt-get autoremove --purge -y

# 5. Thumbnails
rm -rf ~/.cache/thumbnails/*

# 6. Logs
gzip ~/.hermes/logs/agent.log.1
rm -f ~/.hermes/logs/agent.log.1
rm -f ~/.hermes/logs/gateway-shutdown-diag.log
rm -f ~/.hermes/logs/gateway-exit-diag.log

# 7. Temp session files
rm -f ~/.hermes/sessions/*.jsonl

# 8. SQLite VACUUM
sqlite3 ~/.hermes/state.db "VACUUM;"
sqlite3 ~/.hermes/trendradar/data/fingerprints.db "VACUUM;"
```

### Scope
- Automated maintenance: `trendradar_maintenance.py` daily 03:00 auto-runs `cleanup()` — cleans >7 day cache/*.json, data/curated_*_YYYYMMDD.json, etc.
- This manual procedure is for aggressive extra cleaning (logs/thumbnails/pip cache/VACUUM)
- Full procedure reclaims 20-40MB per run

---

## 4. Cron Operations & Nightly Checklist

### Skill-Name Triple Consistency

Every cron job loading skills requires three-way consistency:
1. Directory name: `~/.hermes/skills/trendradar/<name>/`
2. Frontmatter name: SKILL.md `name: <name>` field
3. Cron skills list: `hermes cron list` → skills: [<name>, ...]

All three MUST match. Mismatch causes `⚠️ Skill(s) not found and skipped:` silently.

**Verification**: `echo "=== Directory ===" && ls ~/.hermes/skills/trendradar/ && echo "=== Cron skills ===" && hermes cron list 2>&1 | grep "Skills:"`

### Post-Gateway-Restart Checklist

1. **Gateway status**: `hermes gateway status` → `active (running)`
2. **Stuck cron job?**: If cron job shows `[active]` from before restart, kill it and re-trigger
3. **WeCom connection**: Check gateway log for `✓ wecom connected`
4. **Missed push recovery**: If scheduled push missed during downtime, bypass slot detection: render → fragment → final response

### Pipeline Format Baseline (v5.5.0)

| Stage | Tool | Notes |
|-------|------|-------|
| Render | `render_markdown.py` | Pure script, ~0s, zero tokens |
| Fragment | `fragment_push.py` | Splits by `### ` headers |
| Deep analysis | `render_deep_analysis.py` | WeCom-friendly formatting |
| Push | final response (auto-delivery) | Cron returns briefing as output; system delivers to WeCom |

### Common Failure Modes

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| `Skill not found` for cron job | Skill renamed; cron still uses old name | Update cron skills list |
| Cron prompt references deleted script | Prompt has old script name | `cronjob action=update job_id=xxx prompt="..."` |
| Cron stuck `[active]` | .tick.lock not cleaned up | Remove lock file, re-trigger |
| "5/5 sent" but not received | Gateway crashed between send and delivery | Check gateway.log; re-render and push |

### Cron Prompt Audit

**Key places to check:**
- `cronjob action=list` prompt_preview — actual cron prompt text
- Skill SKILL.md — script names, ref file paths
- Reference .md files — may mention old script names

**Checklist:**
1. `hermes cron list` → verify each skill exists as directory+SKILL.md
2. Match cron prompt script names against `ls scripts/*.py` — no dead names
3. `ls ~/.hermes/trendradar/references/` exists and is non-empty
4. For each reference .md: grep for old script names, path references

---

## 5. Migration Rollback Convention

### Problem
`migrations/runner.py` originally only supported forward migration (up), not rollback (down). If migration corrupts schema, only recovery was manual DROP + re-migrate, losing data.

### Solution: `-- down:` Inline Rollback Comments

Add `-- down:` comment with rollback DDL at end of `.sql` migration files:

```sql
-- 001_initial.sql
CREATE TABLE IF NOT EXISTS fingerprints (...);
CREATE TABLE IF NOT EXISTS heat_tracker (...);

-- down: DROP TABLE IF EXISTS heat_tracker; DROP TABLE IF EXISTS fingerprints;
```

### Convention
- **Position**: Last line(s) of migration file
- **Format**: `-- down: <SQL statements>`
- **Multi-statement**: Semicolon-separated, executed by `executescript()`
- **Idempotent**: Use `IF EXISTS` / `IF NOT EXISTS`

### Safety Guarantees
- **Missing comment → reject**: `ValueError` instead of silent skip
- **Reverse order rollback**: Newest version first, going downward
- **Version precision**: `target_version` inclusive — rollback stops at this version
- **Non-destructive**: `_migrations` table itself is not deleted by down SQL

### Adding New Migrations
1. Create `migrations/NNN_description.sql`
2. Write CREATE/ALTER up-migration SQL
3. Add `-- down: <rollback SQL>` at file end
4. Rollback SQL must undo all structural changes of this migration

### Tests
`tests/test_pipeline_e2e.py::TestMigrationRollback` — 3 items: full up→down cycle, rollback to current version = noop, missing `-- down:` comment rejects rollback

---

## 6. Daily Cron Prompt (Canonical)

> ⚠️ NOTE: The canonical cron prompt is now auto-generated from `pipeline_orchestrator.py --list-steps`.
> See `references/cron-prompt-generated.md` for the latest auto-generated version.
> The manual version below is preserved for reference only.

Every modification to news-secretary skill MUST also update the cron prompt (Trap 15). The prompt is independent of skill content and won't auto-sync.

```bash
cronjob action=update job_id=90a2866775df prompt="..."
```

### Full Text (Manual Version)

Execute this push slot per news-secretary skill (v6.5 auto-delivery mode).

```
export PYTHON=/usr/local/bin/python3.14t
export PYTHONPATH=/home/asus/.hermes
export PYTHON_GIL=0

## Main Flow

1. Run orchestrator: RESULT=$($PYTHON scripts/pipeline_orchestrator.py 2>&1), capture JSON from stdout
2. Parse JSON status:
   - "silent" → return [SILENT]
   - "error" → output errors field
   - "ok" → continue to step 3

3. Output JSON briefing field (sanity_check.py auto-intercepts forbidden prefixes/suffixes)

4. Only push_id=evening (JSON needs_deep_analysis=true):
   Launch 3 Pro delegate_task sub-agents in parallel (trends/cross-domain/risks).
   Each analysis result pipes through render_deep_analysis.py:
     echo "$ANALYSIS_TEXT" | $PYTHON scripts/render_deep_analysis.py --topic "主题" --push-id evening --context
   Then output as separate final responses — each analysis as its own message.

## Fallback (orchestrator failure)

0. $PYTHON scripts/push_slot_detect.py
1. $PYTHON scripts/push_prepare.py --push-id {PUSH_ID} {DEDUP_FLAG}
2. [parallel] $PYTHON scripts/ai_translate.py --push-id {PUSH_ID} & $PYTHON scripts/batch_fetch.py --push-id {PUSH_ID}; wait
3. BRIEFING=$($PYTHON scripts/render_markdown.py --push-id {PUSH_ID})
4. NEW_COUNT=0 → [SILENT]
5. $PYTHON scripts/record_fingerprints.py --push-id {PUSH_ID}
6. Output BRIEFING

## Pre-flight

- cat references/render-format.md (now in PIPELINE.md)
- cat references/deep-analysis-format.md (now in PIPELINE.md)
- cat references/translation-pipeline-sync.md (now in TRAPS.md)
- Empty line rules: items \n\n\n, section headers \n\n\n
- Never use send_message, always use final response auto-delivery
- sanity_check.py auto-scans banned phrases/dead links/sensitive words before push
```

---

## 7. Cron Context Delivery: Auto-Delivery Protocol

> `send_message` is **unavailable** in cron context. All delivery happens via final response auto-delivery.

### How It Works

Cron job finishes → system auto-delivers Agent's final response to configured delivery target (WeCom). Agent does not (and cannot) use `send_message` tool in cron.

### Correct Approach
1. Pipeline produces rendered briefing (`render_markdown.py` stdout)
2. Agent returns briefing text as final response
3. System auto-delivers to WeCom

### Wrong Approaches
- ❌ Attempting `send_message(target="wecom")` in cron — tool unavailable
- ❌ Returning `[SILENT]` as final response — nothing delivered
- ❌ Agent rewriting briefing in own words — format drifts, translation lost
- ❌ Only returning fragments JSON array without actual content

### History
Previously designed for per-fragment send_message delivery, but cron context lacks this tool. v5.7.0+ switched to auto-delivery: Agent outputs full briefing, system handles delivery.

---

## 8. RSS Source Management

### Source Config Location

`sources.json` — 54+ source definitions. Exists in two places:
- **Runtime**: `~/.hermes/trendradar/data/sources.json` (pipeline reads this)
- **Repository**: `~/TrendRadar/trendradar/config/sources.json` (version control)

Must sync after modification: modify runtime file then cp to repo and git push.

### Source Object Format (v2.0)

```json
{
  "version": "2.0",
  "last_updated": "ISO-8601",
  "data_sources": [{
    "id": "bbc_china",
    "name": "BBC 中国",
    "platform": "bbc",
    "type": "rss",
    "category": "foreign_china",
    "enabled": true,
    "feed_url": "https://feeds.bbci.co.uk/news/world/asia/china/rss.xml",
    "authority": 3,
    "language": "en"
  }]
}
```

Fields: `id` (unique), `name` (display name), `type` (rss/blog/hotlist), `feed_url`, `category` (news/tech/economy/game/foreign), `enabled`, `language` (zh/en/ja), `update_interval_minutes`, `last_fetched`.

### Source Naming Convention
- `name` field must appear in `source_platform` as display name
- Use Chinese names, not Japanese kana (e.g., `NHK 商业` not `NHK ビジネス`)
- Keep short for `kw in plat.lower()` substring matching

### Translation Config Decoupled

Translation language detection is driven by `sources.json` `language` field. Adding a new source only requires setting `language` in the source entry — no separate mapping file needed.

### Known Available Sources

**BBC** (feeds.bbci.co.uk) — all direct: /news/rss.xml, /news/world/rss.xml, /news/world/asia/china/rss.xml, /news/business/rss.xml, /news/technology/rss.xml, etc.

**NYT** (rss.nytimes.com) — all direct: /services/xml/rss/nyt/World.xml, Technology.xml, Business.xml, Science.xml, etc.

**NPR** (feeds.npr.org): Format `https://feeds.npr.org/{ID}/rss.xml` — 1001 (News), 1004 (World), 1006 (Business), 1007 (Science), etc.

**NHK** (www3.nhk.or.jp): Format `https://www3.nhk.or.jp/rss/news/cat{N}.xml` — 0 (General), 3 (Science), 4 (Politics), 5 (Economy), 6 (Business).

**Reuters** — via local RSSHub (localhost:1200): /reuters/business, /reuters/technology, /reuters/world/china, /reuters/world. (Reuters public RSS all 404.)

**Korea Herald** (koreaherald.com): `https://www.koreaherald.com/rss/newsAll`

### Deprecated/Unavailable
- **AP**: All public RSS offline
- **Yonhap News**: DNS unreachable in this environment. Alternative: Korea Herald
- **RSSHub public (rsshub.app)**: Unreachable. Local `localhost:1200` available.

### Adding Steps
1. Verify source URL available (curl or confirm returns RSS XML)
2. Determine `category`
3. Use Chinese `name`, add to `sources.json` `data_sources` array
4. Set `language` field for translation
5. `cp data/sources.json ~/TrendRadar/trendradar/config/sources.json`
6. `cd ~/TrendRadar && git add -A && git commit -m "feat: add <name> feed" && git push`
7. Next pipeline auto-fetches (no restart needed)
