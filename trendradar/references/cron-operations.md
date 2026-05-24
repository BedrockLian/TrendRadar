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
   - Bypass slot detection: render → fragment → send_message directly

## Pipeline Format Baseline (v5.5.0)

| Stage | Tool | Notes |
|-------|------|-------|
| Render | `render_markdown.py` | Pure script, ~0s, zero tokens |
| Fragment | `fragment_push.py` | Splits by `### ` headers |
| Deep analysis | `render_deep_analysis.py` | WeCom-friendly formatting |
| Push | `send_message(target="wecom")` | Not cron auto-deliver. Cron returns [SILENT] |

**Deep analysis formatting rules:**
- 5-8 paragraphs, mobile-friendly
- Key data/company names in **bold**
- emoji for section markers (📈 trends, 🎯 directions, ⚡ impacts)
- No tables, code blocks, or horizontal rules
- Pipe through `render_deep_analysis.py --topic "X"` before send_message

## Common Failure Modes

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| `Skill not found` for cron job | Skill renamed/disappeared; cron still uses old name | Update cron skills list to match current disk names |
| Cron prompt references deleted script | Cron prompt has step 5 calling `render_markdown.py` but only `render_markdown.py` exists | `cronjob action=update job_id=xxx prompt="...新prompt..."` — see Trap 23 |
| Cron stuck `[active]` from prior run | .tick.lock not cleaned up after process kill | Remove lock file, re-trigger |
| "5/5 sent" but user didn't receive | Gateway crashed between script send and WeCom delivery | Check gateway.log for `signal=KILL`; re-render and push |
| Dashboard export shows empty containers | Cluster nodes included in export bbox calc | Only export flow-node types (not layer-cluster/domain-cluster) |
