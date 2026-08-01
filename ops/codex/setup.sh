#!/usr/bin/env sh
set -eu
PROJECT_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$PROJECT_ROOT"
PYTHON=${PYTHON:-python3}
"$PYTHON" -m pip install -e './[dev]'
"$PYTHON" -m trendradar.pipeline.pipeline_orchestrator --check-version
"$PYTHON" ops/codex/health_check.py
