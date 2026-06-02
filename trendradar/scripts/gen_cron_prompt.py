1|from trendradar.scripts.common import CST
2|#!/usr/bin/env python3
3|"""
4|gen_cron_prompt.py — Generate canonical cron prompt from pipeline_orchestrator.py SSOT.
5|
6|Single source of truth: pipeline steps are defined in pipeline_orchestrator.py's
7|list_pipeline_steps() function. This script imports it directly (no subprocess)
8|and formats the output as a markdown cron prompt.
9|
10|Usage:
11|  python3 scripts/gen_cron_prompt.py > references/cron-prompt-generated.md
12|
13|The generated file should be referenced by the news-secretary SKILL.md instead
14|of maintaining inline prompt text separately.
15|"""
16|
17|import json
18|import os
19|import sys
20|from pathlib import Path
21|from datetime import datetime, timezone, timedelta
22|
23|SCRIPTS_DIR = Path(__file__).resolve().parent
24|
25|# Dynamic PYTHON path — matches pipeline_orchestrator.py behavior
26|PYTHON = os.environ.get("PYTHON", sys.executable)
27|
28|# Resolve paths dynamically
29|TRENDRADAR_HOME = Path(os.environ.get(
30|    'TRENDRADAR_HOME',
31|    Path.home() / '.hermes' / 'trendradar'
32|))
33|
34|HERMES_HOME = TRENDRADAR_HOME.parent  # ~/.hermes
35|PYTHONPATH = str(HERMES_HOME)  # settings.py TRENDRADAR_HOME.parent
36|
37|
38|def get_pipeline_steps():
39|    """Import list_pipeline_steps directly — no subprocess needed."""
40|    sys.path.insert(0, str(SCRIPTS_DIR))
41|    from pipeline_orchestrator import list_pipeline_steps, __version__
42|    steps = list_pipeline_steps()
43|    steps["version"] = __version__
44|    steps["python"] = PYTHON
45|    return steps
46|
47|
48|def generate_cron_prompt(steps: dict) -> str:
49|    """Format pipeline steps as a cron prompt markdown document."""
50|    version = steps.get("version", "unknown")
51|    import platform
52|    host = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))
53|    step_list = steps.get("steps", [])
54|
55|    # Resolve TRENDRADAR_HOME for generated content
56|    tr_home_path = str(TRENDRADAR_HOME)
57|
58|    lines = []
59|    lines.append(f"<!-- auto-generated: {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')} CST -->")
60|    lines.append(f"<!-- host: {host} | python: {PYTHON} -->")
61|    lines.append("")
62|    lines.append(f"# TrendRadar 日报 Cron Prompt (v{version})")
63|    lines.append("")
64|    lines.append("> Auto-generated from `pipeline_orchestrator.py --list-steps`.")
65|    lines.append("> Run `python3 scripts/gen_cron_prompt.py` to regenerate.")
66|    lines.append("")
67|    lines.append("## Environment")
68|    lines.append("")
69|    lines.append("```bash")
70|    lines.append(f'export PYTHON="{PYTHON}"')
71|    lines.append(f'export PYTHONPATH="{PYTHONPATH}"')
72|    lines.append(f'export TRENDRADAR_HOME="{tr_home_path}"')
73|    lines.append("export PYTHON_GIL=0")
74|    lines.append("```")
75|    lines.append("")
76|    lines.append("## Main Flow (Orchestrator)")
77|    lines.append("")
78|    lines.append("```bash")
79|    lines.append("# Single command — orchestrator handles the full pipeline")
80|    lines.append("RESULT=$($PYTHON scripts/pipeline_orchestrator.py 2>&1)")
81|    lines.append("```")
82|    lines.append("")
83|    lines.append("Parse JSON result:")
84|    lines.append("- `status: \"silent\"` → return [SILENT] and end")
85|    lines.append("- `status: \"error\"` → output errors, try fallback")
86|    lines.append("- `status: \"ok\"` → **DO NOT deliver fragments yourself**. The `slot_direct_push` cron job (no_agent, scheduled at 0 9,12,21) reads `archive/YYYY-MM-DD/{slot}.md`, splits via `split_fragments`, and calls `hermes send` for each fragment. Your job is only to:")
87|    lines.append("  1. Confirm `status: \"ok\"` in stdout")
88|    lines.append("  2. Output a short final response: \"已生成 {date} {slot} 简报（{fragment_count} 片），由 slot_direct_push 接管投递\"")
89|    lines.append("  3. End. Do NOT call `send_message`. Do NOT output fragment contents in your final response — auto-delivery to WeCom would 4KB-truncate the briefing.")
90|    lines.append("## Pipeline Steps (for reference)")
91|    lines.append("")
92|    lines.append(f"Pipeline v{version} | Python: `{PYTHON}`")
93|    lines.append("")
94|    lines.append("| # | Stage | Script | Description |")
95|    lines.append("|---|-------|--------|-------------|")
96|
97|    for step in step_list:
98|        num = step.get("number", "?")
99|        name = step.get("name", "?")
100|        if step.get("parallel"):
101|            scripts = ", ".join(step.get("scripts", []))
102|            desc = step.get("description", "")
103|            lines.append(f"| {num} | {name} ∥ | {scripts} | {desc} |")
104|        else:
105|            script = step.get("script", "?")
106|            desc = step.get("description", "")
107|            lines.append(f"| {num} | {name} | {script} | {desc} |")
108|
109|    lines.append("")
110|    lines.append("## Fallback (manual pipeline)")
111|    lines.append("")
112|    lines.append("If orchestrator fails, run steps manually:")
113|    lines.append("")
114|    lines.append("```bash")
115|    lines.append("# 0. Detect slot")
116|    lines.append("$PYTHON scripts/push_slot_detect.py")
117|    lines.append("")
118|    lines.append("# 1. Fetch + curate")
119|    lines.append("$PYTHON scripts/push_prepare.py --push-id {PUSH_ID} {DEDUP_FLAG}")
120|    lines.append("")
121|    lines.append("# 2. Parallel: translate + full-text fetch")
122|    lines.append("$PYTHON scripts/ai_translate.py --push-id {PUSH_ID} &")
124|    lines.append("wait")
125|    lines.append("")
126|    lines.append("# 3. Render")
127|    lines.append("BRIEFING=$($PYTHON scripts/render_markdown.py --push-id {PUSH_ID})")
128|    lines.append("")
129|    lines.append("# 4. Check for content")
130|    lines.append("# If NEW_COUNT=0 → [SILENT]")
131|    lines.append("")
132|    lines.append("# 5. Record fingerprints")
133|    lines.append("$PYTHON scripts/record_fingerprints.py --push-id {PUSH_ID}")
134|    lines.append("")
135|    lines.append("# 6. (No manual delivery here — slot_direct_push cron job handles it server-side)")
136|    lines.append("```")
137|    lines.append("")
138|    lines.append("## Deep Analysis (evening only)")
139|    lines.append("")
140|    lines.append("Only when `push_id=evening` and `needs_deep_analysis=true`:")
141|    lines.append("")
142|    lines.append("1. Launch 3 Pro `delegate_task` sub-agents in parallel (trends/cross-domain/risks)")
143|    lines.append("2. Pipe each result through render_deep_analysis.py:")
144|    lines.append('   `echo "$ANALYSIS" | $PYTHON scripts/render_deep_analysis.py --topic "主题" --push-id evening --context`')
145|    lines.append("3. Output each formatted analysis as separate final response")
146|    lines.append("")
147|    lines.append("## Pre-flight")
148|    lines.append("")
149|    lines.append("- `TRENDRADAR_HOME`/references/PIPELINE.md — format specs")
150|    lines.append("- `TRENDRADAR_HOME`/references/TRAPS.md — known pitfalls")
151|    lines.append("- Empty line rules: items `\n\n\n`, section headers `\n\n\n`")
152|    lines.append("- **MUST NOT use `send_message` or output briefing in final response** — delivery is handled by slot_direct_push cron job (no_agent).")
153|    lines.append("- **MUST NOT add preamble/footer text** like '以下是...''好消息...' — your final response is logged as a status line, not delivered to WeCom.")
154|    lines.append("- `sanity_check.py` auto-scans before push")
155|    lines.append("")
156|
157|    return "\n".join(lines)
158|
159|
160|def main():
161|    steps = get_pipeline_steps()
162|    prompt = generate_cron_prompt(steps)
163|    print(prompt)
164|    return 0
165|
166|
167|if __name__ == "__main__":
168|    sys.exit(main())
169|