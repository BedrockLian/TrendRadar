# Cron Operations & Nightly Checklist

## Cron Skill-Name Triple Consistency

Every cron job that loads skills requires three-way consistency:

```
1. Directory name:   ~/.hermes/skills/trendradar/<name>/
2. Frontmatter name: SKILL.md → `name: <name>` field
3. Cron skills list: hermes cron list → skills: [<name>, ...]
```

All three MUST match. A mismatch causes `⚠️ Skill(s) not found and skipped:` silently at runtime.

**Verification command:**
```bash
echo "=== Directory ===" && ls ~/.hermes/skills/trendradar/ && echo "=== Cron skills ===" && hermes cron list 2>&1 | grep "Skills:"
```

## Post-Gateway-Restart Checklist

After `hermes gateway start`, check:

1. **Gateway status**: `hermes gateway status` → should show `active (running)`
2. **Cron job stuck?**: If a cron job shows `[active]` from before the restart, it's stuck. Kill it and re-trigger:
   ```bash
   hermes cron list | grep "active"
   # If stuck, remove ".tick.lock":
   rm ~/.hermes/cron/.tick.lock 2>/dev/null
   ```
3. **WeCom connection**: Check gateway log for `✓ wecom connected`
4. **Missed push recovery**: If a scheduled push was missed during downtime:
   - Check if curated data still exists: `ls ~/.hermes/trendradar/data/curated_{slot}_*.json`
   - Bypass slot detection: render → fragment → final response (auto-delivery)

## Pipeline Format Baseline (v5.5.0)

| Stage | Tool | Notes |
|-------|------|-------|
| Render | `render_markdown.py` | Pure script, ~0s, zero tokens |
| Fragment | `fragment_push.py` | Splits by `### ` headers |
| Deep analysis | `render_deep_analysis.py` | WeCom-friendly formatting |
| Push | final response (auto-delivery) | Cron returns briefing as output; system delivers to WeCom |

**Deep analysis formatting rules:**
- 5-8 paragraphs, mobile-friendly
- Key data/company names in **bold**
- emoji for section markers (📈 trends, 🎯 directions, ⚡ impacts)
- No tables, code blocks, or horizontal rules
- Pipe through `render_deep_analysis.py --topic "X"` as final response

## Common Failure Modes

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| `Skill not found` for cron job | Skill renamed; cron still uses old name | Update cron skills list to match disk names |
| Cron prompt references deleted script | Prompt has step calling old script name | `cronjob action=update job_id=xxx prompt="...新prompt..."` — see Trap 15 |
| Cron stuck `[active]` from prior run | .tick.lock not cleaned up after process kill | Remove lock file, re-trigger |
| "5/5 sent" but user didn't receive | Gateway crashed between script send and WeCom delivery | Check gateway.log for `signal=KILL`; re-render and push |

## Cron Prompt Audit

Run periodically (especially after script rename/deletion) to detect stale references:

**Key places to check:**
- `cronjob action=list` prompt_preview — actual cron prompt text
- Skill SKILL.md — script names, ref file paths
- Reference .md files — may mention old script names in prose

**Audit checklist:**
1. `hermes cron list` → verify each skill in skills list exists as directory+SKILL.md
2. Match cron prompt script names against `ls scripts/*.py` — no dead names
3. `ls ~/.hermes/trendradar/references/` exists and is non-empty
4. For each reference .md: grep for old script names, path references
