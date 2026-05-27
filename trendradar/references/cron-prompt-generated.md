<!-- auto-generated: 2026-05-27 13:18:46 CST -->
<!-- source: pipeline_orchestrator.py v2.8.0 --list-steps -->

# TrendRadar 日报 Cron Prompt (v2.8.0 auto-generated)

> ⚠️ This file is auto-generated from `pipeline_orchestrator.py --list-steps`.
> Do not edit manually. Run `python3 scripts/gen_cron_prompt.py` to regenerate.

## Environment

```bash
export PYTHON=/usr/local/bin/python3.14t
export PYTHONPATH=/home/asus/.hermes
export PYTHON_GIL=0
```

## Main Flow (Orchestrator)

```bash
# Step 0: Run orchestrator (single command)
RESULT=$($PYTHON scripts/pipeline_orchestrator.py 2>&1)
```

Parse JSON result:
- `status: "silent"` → return [SILENT]
- `status: "error"` → output errors, try fallback
- `status: "ok"` → output `briefing` field as final response (auto-delivery)

## Pipeline Steps (for reference)

Pipeline v2.8.0, Python: `/usr/local/bin/python3.14t`

| # | Stage | Script | Description |
|---|-------|--------|-------------|
| 0 | slot_detect | push_slot_detect.py | Detect current push slot from timeline.yaml |
| 1 | push_prepare | push_prepare.py | Fetch RSS feeds + curate top items (fetch + curate) |
| 2 | track_events | track_events.py | Track event continuity (morning only) |
| 3 | parallel ∥ | ai_translate.py, batch_fetch.py | Parallel: translate foreign articles + fetch full text |
| 4 | render_markdown | render_markdown.py | Render curated items to WeCom markdown |
| 5 | fragment_push | fragment_push.py | Split markdown into WeCom-safe byte-counted fragments |
| 6 | record_fingerprints | record_fingerprints.py | Record item fingerprints for cross-slot dedup |

## Fallback (manual pipeline)

If orchestrator fails, run steps manually:

```bash
# 0. Detect slot
$PYTHON scripts/push_slot_detect.py

# 1. Fetch + curate
$PYTHON scripts/push_prepare.py --push-id {PUSH_ID} {DEDUP_FLAG}

# 2. Parallel: translate + full-text fetch
$PYTHON scripts/ai_translate.py --push-id {PUSH_ID} &
$PYTHON scripts/batch_fetch.py --push-id {PUSH_ID} &
wait

# 3. Render
BRIEFING=$($PYTHON scripts/render_markdown.py --push-id {PUSH_ID})

# 4. Check for content
# If NEW_COUNT=0 → [SILENT]

# 5. Record fingerprints
$PYTHON scripts/record_fingerprints.py --push-id {PUSH_ID}

# 6. Output BRIEFING as final response (auto-delivery)
```

## Deep Analysis (evening only)

Only when `push_id=evening` and `needs_deep_analysis=true`:

1. Launch 3 Pro `delegate_task` sub-agents in parallel (trends/cross-domain/risks)
2. Pipe each result through render_deep_analysis.py:
   `echo "$ANALYSIS" | $PYTHON scripts/render_deep_analysis.py --topic "主题" --push-id evening --context`
3. Output each formatted analysis as separate final response

## Pre-flight

- Read `references/PIPELINE.md` for format specs
- Read `references/TRAPS.md` for known pitfalls
- Empty line rules: items `\n\n\n`, section headers `\n\n\n`
- Never use `send_message`, always use final response auto-delivery
- `sanity_check.py` auto-scans before push

