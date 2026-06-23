"""TrendRadar test suite (pytest).

Covers pipeline stages, scoring edge cases, sanity-check, render
markdown format compliance, fragment splitter, etc. Run via
`cd trendradar && python3 -m pytest tests/ -v --tb=short`.

Smoke test subset (selected by default) is invoked by
`hermes-scripts/trendradar_maintenance.py::runtests()` to keep
the daily cron output short (~140 tests).
"""
