"""TrendRadar Python package.

Modules under this package form the core of the TrendRadar pipeline:
- `pipeline/`:   Daily briefing orchestration and pipeline stages
- `sources/`:    RSS source adapters
- `intelligence/`: Classification, scoring, heat, and translation
- `reporting/`:  Markdown, reports, audits, and event tracking
- `runtime/`:    Paths, storage, logging, locking, and shared utilities
- `cli/`:        Human- and Codex-facing commands
- `config/`:     YAML / JSON / Python config (sources, interests, domains, etc.)
- `migrations/`: SQLite schema migrations

Repository-level tests live in `tests/`; architecture and operations docs live
in `docs/`; Codex task entrypoints live in `ops/codex/`.
"""
