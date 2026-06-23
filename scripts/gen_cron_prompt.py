from trendradar.scripts.common import CST
#!/usr/bin/env python3
"""
gen_cron_prompt.py — Generate canonical cron prompt from pipeline_orchestrator.py SSOT.

Single source of truth: pipeline steps are defined in pipeline_orchestrator.py's
list_pipeline_steps() function. This script imports it directly (no subprocess)
and formats the output as a markdown cron prompt.

Usage:
  python3 scripts/gen_cron_prompt.py > references/cron-prompt-generated.md

The generated file should be referenced by the news-secretary SKILL.md instead
of maintaining inline prompt text separately.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

SCRIPTS_DIR = Path(__file__).resolve().parent

# Dynamic PYTHON path — matches pipeline_orchestrator.py behavior
PYTHON = os.environ.get("PYTHON", sys.executable)

# TRENDRADAR_HOME SSOT (审计 P1-5, 2026-06-20):
# 统一从 paths.py 取，但保留 ENV 注入路径能力（gen_cron_prompt 自己负责注入）
import os as _os
if not _os.environ.get('TRENDRADAR_HOME'):
    _os.environ['TRENDRADAR_HOME'] = str(Path.home() / '.hermes' / 'trendradar')
from trendradar.scripts.paths import TRENDRADAR_HOME, HERMES_HOME

PYTHONPATH = str(TRENDRADAR_HOME)


def get_pipeline_steps():
    """Import list_pipeline_steps directly — no subprocess needed."""
    sys.path.insert(0, str(SCRIPTS_DIR))
    from pipeline_orchestrator import list_pipeline_steps, __version__
    steps = list_pipeline_steps()
    steps["version"] = __version__
    steps["python"] = PYTHON
    return steps


def generate_cron_prompt(steps: dict) -> str:
    """Format pipeline steps as a cron prompt markdown document."""
    version = steps.get("version", "unknown")
    import platform
    host = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
    step_list = steps.get("steps", [])

    # Resolve TRENDRADAR_HOME for generated content
    tr_home_path = str(TRENDRADAR_HOME)

    lines = []
    lines.append(f"<!-- auto-generated: {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')} CST -->")
    lines.append(f"<!-- host: {host} | python: {PYTHON} -->")
    lines.append("")
    lines.append(f"# TrendRadar 日报 Cron Prompt (v{version})")
    lines.append("")
    lines.append("> Auto-generated from `pipeline_orchestrator.py --list-steps`.")
    lines.append("> Run `python3 scripts/gen_cron_prompt.py` to regenerate.")
    lines.append("")
    lines.append("## Environment")
    lines.append("")
    lines.append("```bash")
    lines.append(f'export PYTHON="{PYTHON}"')
    lines.append(f'export PYTHONPATH="{PYTHONPATH}"')
    lines.append(f'export TRENDRADAR_HOME="{tr_home_path}"')
    lines.append("```")
    lines.append("")
    lines.append("## Main Flow (Orchestrator)")
    lines.append("")
    lines.append("```bash")
    lines.append("# Single command — orchestrator handles the full pipeline")
    lines.append("RESULT=$($PYTHON scripts/pipeline_orchestrator.py 2>&1)")
    lines.append("```")
    lines.append("")
    lines.append("Parse JSON result:")
    lines.append("- `status: \"silent\"` → return [SILENT] and end")
    lines.append("- `status: \"error\"` → output errors, try fallback")
    lines.append("- `status: \"ok\"` → **DO NOT deliver fragments yourself**. The `slot_direct_push` cron job (no_agent, scheduled at 0 9,12,21) reads `archive/YYYY-MM-DD/{slot}.md`, splits via `split_fragments`, and calls `hermes send` for each fragment. Your job is only to:")
    lines.append("  1. Confirm `status: \"ok\"` in stdout")
    lines.append("  2. Output a short final response: \"已生成 {date} {slot} 简报（{fragment_count} 片），由 slot_direct_push 接管投递\"")
    lines.append("  3. End. Do NOT call `send_message`. Do NOT output fragment contents in your final response — auto-delivery to WeCom would 4KB-truncate the briefing.")
    lines.append("## Pipeline Steps (for reference)")
    lines.append("")
    lines.append(f"Pipeline v{version} | Python: `{PYTHON}`")
    lines.append("")
    lines.append("| # | Stage | Script | Description |")
    lines.append("|---|-------|--------|-------------|")

    for step in step_list:
        num = step.get("number", "?")
        name = step.get("name", "?")
        if step.get("parallel"):
            scripts = ", ".join(step.get("scripts", []))
            desc = step.get("description", "")
            lines.append(f"| {num} | {name} ∥ | {scripts} | {desc} |")
        else:
            script = step.get("script", "?")
            desc = step.get("description", "")
            lines.append(f"| {num} | {name} | {script} | {desc} |")

    lines.append("")
    lines.append("## Fallback (manual pipeline)")
    lines.append("")
    lines.append("If orchestrator fails, run steps manually:")
    lines.append("")
    lines.append("```bash")
    lines.append("# 0. Detect slot")
    lines.append("$PYTHON scripts/push_slot_detect.py")
    lines.append("")
    lines.append("# 1. Fetch + curate")
    lines.append("$PYTHON scripts/push_prepare.py --push-id {PUSH_ID} {DEDUP_FLAG}")
    lines.append("")
    lines.append("# 2. Parallel: translate + full-text fetch")
    lines.append("$PYTHON scripts/ai_translate.py --push-id {PUSH_ID} &")
    lines.append("wait")
    lines.append("")
    lines.append("# 3. Render")
    lines.append("BRIEFING=$($PYTHON scripts/render_markdown.py --push-id {PUSH_ID})")
    lines.append("")
    lines.append("# 4. Check for content")
    lines.append("# If NEW_COUNT=0 → [SILENT]")
    lines.append("")
    lines.append("# 5. Record fingerprints")
    lines.append("$PYTHON scripts/record_fingerprints.py --push-id {PUSH_ID}")
    lines.append("")
    lines.append("# 6. (No manual delivery here — slot_direct_push cron job handles it server-side)")
    lines.append("```")
    lines.append("")
    lines.append("## Deep Analysis (evening only)")
    lines.append("")
    lines.append("Only when `push_id=evening` and `needs_deep_analysis=true`:")
    lines.append("")
    lines.append("1. Launch 3 flash `delegate_task` sub-agents in parallel (trends/cross-domain/risks, deepseek-v4-flash)")
    lines.append("2. Pipe each result through render_deep_analysis.py:")
    lines.append('   `echo "$ANALYSIS" | $PYTHON scripts/render_deep_analysis.py --topic "主题" --push-id evening --context`')
    lines.append("3. Output each formatted analysis as separate final response")
    lines.append("")
    lines.append("## Pre-flight")
    lines.append("")
    lines.append("- `TRENDRADAR_HOME`/references/PIPELINE.md — format specs")
    lines.append("- `TRENDRADAR_HOME`/references/TRAPS.md — known pitfalls")
    lines.append("- Empty line rules: items `\n\n\n`, section headers `\n\n\n`")
    lines.append("- **MUST NOT use `send_message` or output briefing in final response** — delivery is handled by slot_direct_push cron job (no_agent).")
    lines.append("- **MUST NOT add preamble/footer text** like '以下是...''好消息...' — your final response is logged as a status line, not delivered to WeCom.")
    lines.append("- `sanity_check.py` auto-scans before push")
    lines.append("")

    return "\n".join(lines)


def main():
    steps = get_pipeline_steps()
    prompt = generate_cron_prompt(steps)
    print(prompt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
