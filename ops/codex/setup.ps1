param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Push-Location $ProjectRoot
try {
    & $Python -m pip install -e ".[dev]"
    & $Python -m trendradar.pipeline.pipeline_orchestrator --check-version
    & $Python ops\codex\health_check.py
} finally {
    Pop-Location
}
