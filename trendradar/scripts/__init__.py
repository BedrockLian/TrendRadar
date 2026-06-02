"""Pipeline scripts — fetch, curate, translate, render, push.

Run any script as `python3 -m trendradar.scripts.<name>`. All scripts share
`TRENDRADAR_HOME` resolution from `file_utils.py` (defaults to
`~/.hermes/trendradar`) and PyYAML + stdlib + DeepSeek-via-OpenAI-compat.

Key scripts (entry points used by cron or manual ops):

| Script                  | Purpose                                  | Cron    |
|-------------------------|------------------------------------------|---------|
| push_prepare.py         | fetch RSS + curate for one slot          | LLM     |
| ai_translate.py         | translate/expand foreign + short CN items | LLM   |
| render_markdown.py      | archive markdown output                  | LLM     |
| render_deep_analysis.py | format Pro/flash deep analysis for WeCom | LLM     |
| fragment_push.py        | UTF-8 byte-aware fragment splitter       | LLM     |
| pipeline_orchestrator.py| one-shot all-stage orchestrator          | LLM     |
| fetch_feeds.py          | raw RSS fetch (no curation)              | LLM     |
| record_fingerprints.py  | dedup fingerprint store                   | LLM     |
| track_events.py         | cross-cycle event tracking                | LLM     |
| heat_tracker.py         | sustained-heat scoring                    | LLM     |
| scorer.py               | 5-domain scoring                          | LLM     |
| classifier.py           | domain classification                     | LLM     |
| render_markdown.py      | archive markdown                          | LLM     |
| sanity_check.py         | pre-publish interceptor (banned phrases / dead links) | LLM |
| push_slot_detect.py     | decide morning/noon/evening               | LLM     |
| fragment_push.py        | splitter                                  | LLM     |
| archive_resend.py       | safe resend from archive                  | manual  |
| gen_cron_prompt.py      | generate the canonical cron prompt from pipeline_orchestrator SSOT | manual |
| common.py / settings.py | shared utilities                          | —       |
"""
