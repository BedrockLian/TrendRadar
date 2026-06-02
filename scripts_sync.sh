#!/usr/bin/env bash
# scripts_sync.sh — 双向同步根 config/scripts 真目录与内层 trendradar/config/scripts 包目录
#
# 为什么需要：根 config/ 和 scripts/ 是 git 跟踪的真目录（GitHub Web UI 显示真目录，
# 避免 symlink 被显示成一行 'config -> trendradar/config'）。Python import 用内层
# trendradar.config / trendradar.scripts。两边内容必须一致——改一边后跑此脚本同步。
#
# 双向：默认从内层（git 真相源）→ 外层（git 跟踪的真目录）。
#       加 --reverse 反向同步（外层 → 内层）。
#
# 用法：
#   bash scripts_sync.sh               # 内层 → 外层
#   bash scripts_sync.sh --reverse     # 外层 → 内层
#   bash scripts_sync.sh --check       # 干跑：只检查差异，不复制
#   bash scripts_sync.sh --watch       # 持续模式：5s 一次（cron 期间用）
#
# 排除：__pycache__/ *.pyc *.bak

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TR="$SCRIPT_DIR"
INNER_CONFIG="$TR/trendradar/config"
INNER_SCRIPTS="$TR/trendradar/scripts"
OUTER_CONFIG="$TR/config"
OUTER_SCRIPTS="$TR/scripts"

# 解析参数
DIRECTION="inner-to-outer"  # 默认
DRY_RUN=""
WATCH_MODE=""
case "${1:-}" in
    --reverse) DIRECTION="outer-to-inner" ;;
    --check)   DIRECTION="check"; DRY_RUN="echo" ;;
    --watch)   WATCH_MODE=1; DIRECTION="inner-to-outer" ;;
    --help|-h)
        sed -n '3,28p' "$0" | sed 's/^# \{0,1\}//'
        exit 0
        ;;
esac

# 同步函数（使用 rsync 如果可用，否则用 cp）
do_sync() {
    local src="$1" dst="$2"
    if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete --exclude='__pycache__' --exclude='*.pyc' \
              --exclude='*.bak' --exclude='config_real' --exclude='scripts_real' \
              "$src/" "$dst/"
    else
        # cp -r + 删目标多出文件
        for f in "$dst"/*; do
            [ -e "$f" ] || continue
            name=$(basename "$f")
            if [ ! -e "$src/$name" ]; then
                rm -rf "$f"
            fi
        done
        cp -r "$src"/* "$dst"/ 2>/dev/null || true
    fi
}

# 干跑检查
if [ "$DIRECTION" = "check" ]; then
    echo "=== 同步检查 (--check) ==="
    diff -rq "$INNER_CONFIG" "$OUTER_CONFIG" 2>&1 | grep -v "Only in.*__pycache__" | head -5
    diff -rq "$INNER_SCRIPTS" "$OUTER_SCRIPTS" 2>&1 | grep -v "Only in.*__pycache__" | head -5
    echo "✓ 检查完成"
    exit 0
fi

# 执行同步
sync_once() {
    if [ "$DIRECTION" = "inner-to-outer" ]; then
        do_sync "$INNER_CONFIG" "$OUTER_CONFIG"
        do_sync "$INNER_SCRIPTS" "$OUTER_SCRIPTS"
    else
        do_sync "$OUTER_CONFIG" "$INNER_CONFIG"
        do_sync "$OUTER_SCRIPTS" "$INNER_SCRIPTS"
    fi
}

if [ -n "$WATCH_MODE" ]; then
    while true; do
        sync_once
        sleep 5
    done
else
    sync_once
    echo "✓ 已同步: $DIRECTION"
fi
