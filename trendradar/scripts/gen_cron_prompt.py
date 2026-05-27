#!/usr/bin/env python3
"""
gen_cron_prompt.py — Generate canonical cron prompt from pipeline_orchestrator.py --list-steps.

Single source of truth: pipeline steps are defined in pipeline_orchestrator.py's
list_pipeline_steps() function. This script calls --list-steps and formats the
output as a markdown cron prompt suitable for news-secretary SKILL.md.

Usage:
  python3 scripts/gen_cron_prompt.py > references/cron-prompt-generated.md

The generated file should be referenced by the news-secretary SKILL.md instead
of maintaining inline prompt text separately.
"""

import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
SCRIPTS_DIR = Path(__file__).resolve().parent
PYTHON = "/usr/local/bin/python3.14t"
ORCHESTRATOR = SCRIPTS_DIR / "pipeline_orchestrator.py"


def get_pipeline_steps():
    """Call pipeline_orchestrator.py --list-steps and return parsed JSON."""
    result = subprocess.run(
        [PYTHON, str(ORCHESTRATOR), "--list-steps"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        print(f"Error: orchestrator --list-steps failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)


def generate_cron_prompt(steps: dict) -> str:
    """Format pipeline steps as a cron prompt markdown document."""
    version = steps.get("version", "unknown")
    python_bin = steps.get("python", PYTHON)
    step_list = steps.get("steps", [])

    lines = []
    lines.append(f"<!-- auto-generated: {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')} CST -->")
    lines.append(f"<!-- source: pipeline_orchestrator.py v{version} --list-steps -->")
    lines.append("")
    lines.append(f"# TrendRadar 日报 Cron Prompt (v{version} auto-generated)")
    lines.append("")
    lines.append("> ⚠️ This file is auto-generated from `pipeline_orchestrator.py --list-steps`.")
    lines.append("> Do not edit manually. Run `python3 scripts/gen_cron_prompt.py` to regenerate.")
    lines.append("")
    lines.append("## Environment")
    lines.append("")
    lines.append("```bash")
    lines.append("export PYTHON=/usr/local/bin/python3.14t")
    lines.append("export PYTHONPATH=/home/asus/.hermes")
    lines.append("export PYTHON_GIL=0")
    lines.append("```")
    lines.append("")
    lines.append("## Main Flow (Orchestrator)")
    lines.append("")
    lines.append("```bash")
    lines.append("# Step 0: Run orchestrator (single command)")
    lines.append("RESULT=$($PYTHON scripts/pipeline_orchestrator.py 2>&1)")
    lines.append("```")
    lines.append("")
    lines.append("Parse JSON result:")
    lines.append("- `status: \"silent\"` → return [SILENT]")
    lines.append("- `status: \"error\"` → output errors, try fallback")
    lines.append("- `status: \"ok\"` → output `briefing` field as final response (auto-delivery)")
    lines.append("")
    lines.append("## Pipeline Steps (for reference)")
    lines.append("")
    lines.append(f"Pipeline v{version}, Python: `{python_bin}`")
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
    lines.append("$PYTHON scripts/batch_fetch.py --push-id {PUSH_ID} &")
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
    lines.append("# 6. Output BRIEFING as final response (auto-delivery)")
    lines.append("```")
    lines.append("")
    lines.append("## Deep Analysis (evening only)")
    lines.append("")
    lines.append("Only when `push_id=evening` and `needs_deep_analysis=true`:")
    lines.append("")
    lines.append("1. Launch 3 Pro `delegate_task` sub-agents in parallel (trends/cross-domain/risks)")
    lines.append("2. Pipe each result through render_deep_analysis.py:")
    lines.append('   `echo "$ANALYSIS" | $PYTHON scripts/render_deep_analysis.py --topic "主题" --push-id evening --context`')
    lines.append("3. Output each formatted analysis as separate final response")
    lines.append("")
    lines.append("## Pre-flight")
    lines.append("")
    lines.append("- Read `references/PIPELINE.md` for format specs")
    lines.append("- Read `references/TRAPS.md` for known pitfalls")
    lines.append("- Empty line rules: items `\\n\\n\\n`, section headers `\\n\\n\\n`")
    lines.append("- Never use `send_message`, always use final response auto-delivery")
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
