#!/bin/bash
# TrendRadar 管道诊断脚本（v5.2.0）
# 用法: bash scripts/diag_pipeline.sh
set -euo pipefail

PID=$(pgrep -f "push_prepare\|batch_fetch\|fetch_feeds\|curate_and_push" 2>/dev/null || true)
if [ -n "$PID" ]; then
    echo "=== Pipeline 进程树 ==="
    pstree -p "$PID" 2>/dev/null || ps -ef | grep -E "push_prepare|batch_fetch|fetch_feeds|curate_and_push" | grep -v grep
else
    echo "当前无运行中的管道进程"
fi

echo ""
echo "=== 压缩缓存文件 ==="
TR_HOME="${TRENDRADAR_HOME:-$HOME/.hermes/trendradar}"
ls -lh "$TR_HOME/cache/"*.zst 2>/dev/null || echo "(无 .zst 压缩文件)"
echo ""
echo "=== JSON 缓存文件 ==="
ls -lh "$TR_HOME/cache/"*.json 2>/dev/null | head -10 || echo "(无 JSON 缓存文件)"
