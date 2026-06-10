<!-- auto-generated: 2026-06-09 21:50:32 CST -->
<!-- host: ASUS | python: C:\Users\ASUS\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe -->

# TrendRadar 日报 Cron Prompt (v2.9.0)

> Auto-generated from `pipeline_orchestrator.py --list-steps`.
> Run `python3 scripts/gen_cron_prompt.py` to regenerate.

## Environment

```bash
export PYTHON="C:\Users\ASUS\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
export PYTHONPATH="C:\Users\ASUS\AppData\Local\hermes\trendradar"
export TRENDRADAR_HOME="C:\Users\ASUS\AppData\Local\hermes\trendradar"
export PYTHON_GIL=0
```

## Main Flow (Orchestrator)

```bash
# Single command — orchestrator handles the full pipeline
RESULT=$($PYTHON scripts/pipeline_orchestrator.py 2>&1)
```

Parse JSON result:
- `status: "silent"` → return [SILENT] and end
- `status: "error"` → output errors, try fallback
- `status: "ok"` → **DO NOT deliver fragments yourself**. The `slot_direct_push` cron job (no_agent, scheduled at 0 9,12,21) reads `archive/YYYY-MM-DD/{slot}.md`, splits via `split_fragments`, and calls `hermes send` for each fragment. Your job is only to:
  1. Confirm `status: "ok"` in stdout
  2. Output a short final response: "已生成 {date} {slot} 简报（{fragment_count} 片），由 slot_direct_push 接管投递"
  3. End. Do NOT call `send_message`. Do NOT output fragment contents in your final response — auto-delivery to WeCom would 4KB-truncate the briefing.
## Pipeline Steps (for reference)

Pipeline v2.9.0 | Python: `C:\Users\ASUS\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe`

| # | Stage | Script | Description |
|---|-------|--------|-------------|
| 0 | slot_detect | ? | Detect current push slot from timeline.yaml (direct call) |
| 1 | push_prepare | push_prepare.py | Fetch RSS feeds + curate top items (fetch + curate) |
| 2 | track_events | track_events.py | Track event continuity (morning only) |
| 3 | ai_translate | ai_translate.py | Translate foreign articles to Chinese |
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
wait

# 3. Render
BRIEFING=$($PYTHON scripts/render_markdown.py --push-id {PUSH_ID})

# 4. Check for content
# If NEW_COUNT=0 → [SILENT]

# 5. Record fingerprints
$PYTHON scripts/record_fingerprints.py --push-id {PUSH_ID}

# 6. (No manual delivery here — slot_direct_push cron job handles it server-side)
```

## Deep Analysis (evening only)

Only when `push_id=evening` and `needs_deep_analysis=true`:

1. Launch 3 flash `delegate_task` sub-agents in parallel (trends/cross-domain/risks, deepseek-v4-flash)
2. Pipe each result through render_deep_analysis.py:
   `echo "$ANALYSIS" | $PYTHON scripts/render_deep_analysis.py --topic "主题" --push-id evening --context`
3. Output each formatted analysis as separate final response

## Pre-flight

- `TRENDRADAR_HOME`/references/PIPELINE.md — format specs
- `TRENDRADAR_HOME`/references/TRAPS.md — known pitfalls
- Empty line rules: items `


`, section headers `


`
- **MUST NOT use `send_message` or output briefing in final response** — delivery is handled by slot_direct_push cron job (no_agent).
- **MUST NOT add preamble/footer text** like '以下是...''好消息...' — your final response is logged as a status line, not delivered to WeCom.
- `sanity_check.py` auto-scans before push

