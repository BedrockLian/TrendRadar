"""TrendRadar config — runtime-tunable parameters.

Single source of truth for RSS source definitions, scoring weights,
domain ratios, batch sizes, proxy config, etc. Most files are loaded
by name in `scripts/settings.py`; add new config here and expose
via `settings.py` getter.

Files in this directory (touched at runtime, do NOT edit during cron run):

| File               | Format | Purpose                                  |
|--------------------|--------|------------------------------------------|
| sources.json       | JSON   | RSS source definitions (43 sources)      |
| ai_interests.yaml  | YAML   | Interest scoring preferences              |
| timeline.yaml      | YAML   | Push schedule (morning/noon/evening)     |
| keywords.py        | Python | Aho-Corasick keyword matcher             |
| domains.py         | Python | Domain ratios / per-domain caps          |
| scoring.py         | Python | Per-domain scoring weights               |
| fetching.py        | Python | Fetch concurrency / timeout              |
| heat_tracking.py   | Python | Sustained-heat thresholds                 |
| translation.py     | Python | ai_translate batch size / templates      |
| proxy.py           | Python | WSL proxy config (127.0.0.1:7890)        |
| delivery.py        | Python | WeCom delivery params                     |
| api.py             | Python | get_api_key() fallback chain              |
"""
