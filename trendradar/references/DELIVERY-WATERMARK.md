<!-- version: 1.0.0 | created: 2026-05-27 -->

# Delivery Watermark (delivery_marker) Mechanism

## Overview

The delivery_marker system provides a reliable way to track whether a scheduled push
was actually delivered to the end user (WeCom). Since `pipeline_orchestrator.py` 
reporting `status=ok` does NOT guarantee the user received the briefing, delivery
markers serve as the ground truth for delivery confirmation.

## Architecture

### MarkerDir

Location: `data/delivery_markers/`

Each push creates a marker file named `{date}_{slot}.marker` containing:
```json
{
  "push_id": "morning",
  "date": "2026-05-27",
  "pipeline_status": "ok",
  "fragment_count": 3,
  "delivered": true,
  "delivered_at": "2026-05-27T09:05:23+08:00",
  "verified_by": "delivery_watchdog"
}
```

### Marker States

| State | Meaning |
|-------|---------|
| `delivered: true` | Confirmed delivery to WeCom |
| `delivered: false` | Pipeline ran but delivery not confirmed |
| No marker file | Pipeline did not run or failed before marker creation |

## delivery_watchdog.py

The delivery watchdog (cron `cab79825520e`, runs as `no_agent=true`) periodically
checks `push_log.json` for recent pipeline runs and verifies that corresponding
delivery markers exist and show `delivered: true`.

If a pipeline run has no delivery marker or shows `delivered: false`, the watchdog
triggers auto-redelivery:
1. Reads the archived briefing from `archive/{date}/{slot}.md`
2. Validates the archive file exists and is non-empty
3. Re-delivers via the same auto-delivery mechanism (final response to WeCom)
4. Updates the marker with the new delivery timestamp

### Watchdog Schedule
- Runs every 15 minutes
- Checks push_log.json for entries in the last 2 hours
- Verifies markers for morning (09:00), noon (12:00), evening (21:00) slots

## Manual Delivery Marking

### Create a marker manually
```bash
mkdir -p data/delivery_markers
cat > data/delivery_markers/2026-05-27_morning.marker << 'EOF'
{
  "push_id": "morning",
  "date": "2026-05-27",
  "pipeline_status": "ok",
  "fragment_count": 3,
  "delivered": true,
  "delivered_at": "2026-05-27T09:05:23+08:00",
  "verified_by": "manual"
}
EOF
```

### Check delivery status for today
```bash
ls -la data/delivery_markers/$(date +%Y-%m-%d)_*.marker
```

### Mark a push as delivered after manual resend
```bash
# After using archive_resend.py to resend
echo '{"delivered": true, "delivered_at": "'$(date -Iseconds)'", "verified_by": "manual_resend"}' \
  | python3 -c "
import json, sys
from pathlib import Path
marker = Path('data/delivery_markers/2026-05-27_morning.marker')
data = json.loads(marker.read_text()) if marker.exists() else {}
data.update(json.loads(sys.stdin.read()))
marker.parent.mkdir(parents=True, exist_ok=True)
marker.write_text(json.dumps(data, ensure_ascii=False, indent=2))
"
```

## Integration with Pipeline

The pipeline orchestrator (`pipeline_orchestrator.py`) writes to `push_log.json`
after each run. The watchdog uses this log as its trigger source.

The marker files complement push_log.json by providing delivery confirmation
rather than just pipeline execution confirmation.

## Known Failure Modes (Redelivery Triggers)

1. **Gateway WebSocket disconnect during delivery window**: Pipeline runs, fragments
   generated, but WebSocket drops before final response delivered → marker shows
   `delivered: false` → watchdog redelivers from archive.

2. **DeepSeek API stream truncation**: Pipeline reports `ok` with partial content.
   Watchdog can't fix content but ensures whatever was produced gets delivered.

3. **Cron agent crash after pipeline but before delivery**: Pipeline completed,
   push_log.json updated, but agent crashed before outputting final response →
   no delivery occurred. Watchdog detects marker absence and redelivers.

## Relationship to archive_resend.py

`archive_resend.py` is the manual resend tool — requires human trigger.
`delivery_watchdog.py` is the automatic resend tool — runs on cron.

Both read from the same archive (`archive/{date}/{slot}.md`) and both create/update
delivery markers after successful delivery.
