#!/usr/bin/env bash
# sync_repo.sh —手动触发:把运行时 trendradar/里的代码改动同步到本地 git仓库,
# commit, 然后 push 到 GitHub。
#
# 用法:
# bash sync_repo.sh # sync + commit + push
# bash sync_repo.sh --sync # 只 robocopy代码
# bash sync_repo.sh --commit # sync + commit, 不 push
# bash sync_repo.sh --push # sync + commit + push
# bash sync_repo.sh --dry-run #全部 dry-run
# bash sync_repo.sh --status # 看状态
#
#排除运行时数据: data/ cache/ archive/ logs/ .env *.db *.json.zst *.marker
# 
# 设计:
# -运行时 = $HERMES_HOME/trendradar/
# - 本地仓库 = $HERMES_HOME/repo trendradar/
# - Push冲突保护: fetch +落后检测
# - Push重试3次(30s/60s/120s)

set -e

RUNTIME="$HERMES_HOME/trendradar"
REPO="$HERMES_HOME/repo trendradar"
STATE_DIR="$REPO/.sync_state"
LAST_SYNC_FILE="$STATE_DIR/last_sync.txt"
LAST_COMMIT_FILE="$STATE_DIR/last_commit.txt"
SYNC_HELPER="$REPO/sync_files.py"

EXCLUDES=(
        *.broken
        *.swp
__pycache__
*.pyc
*.bak
.pytest_cache
.git
data
cache
archive
logs
output
mail_queue
.env
.env.local
*.db
*.db.backup
*.db-shm
*.db-wal
*.json.zst
*.marker
)

if [ -z "$HERMES_HOME" ]; then
 echo "ERROR: HERMES_HOME 未设置"
 exit1
fi

ACTION="${1:-all}"
case "$ACTION" in
 --sync) DO_SYNC=1; DO_COMMIT=0; DO_PUSH=0 ;;
 --commit) DO_SYNC=1; DO_COMMIT=1; DO_PUSH=0 ;;
 --push|--all|"") DO_SYNC=1; DO_COMMIT=1; DO_PUSH=1 ;;
 --dry-run) DO_SYNC=1; DO_COMMIT=1; DO_PUSH=1; DRY_RUN=1 ;;
 --status) DO_STATUS=1 ;;
 -h|--help)
  sed -n "3,15p" "$0"
  exit0
 ;;
 *) echo "unknown action: $ACTION"; exit2 ;;
esac

mkdir -p "$STATE_DIR"

# === status ===
if [ -n "${DO_STATUS:-}" ]; then
 echo "=== RUNTIME: $RUNTIME ==="
 echo "=== REPO: $REPO ==="
 [ -f "$LAST_SYNC_FILE"] && cat "$LAST_SYNC_FILE" || echo "(never synced)"
 [ -f "$LAST_COMMIT_FILE"] && cat "$LAST_COMMIT_FILE" || echo "(never committed)"
 cd "$REPO" && git status -s | head -30
 cd "$REPO" && git fetch origin >/dev/null2>&1 || true
 cd "$REPO" && git rev-list --left-right --count main...origin/main 2>/dev/null || echo "(no upstream)"
 exit0
fi

# === sync (robocopy via Python wrapper) ===
if [ -n "${DO_SYNC:-}" ]; then
 echo "[sync] 运行时 → 本地仓库 (via robocopy)..."
 for sub in config scripts hermes-scripts prompts; do
  if [ -d "$RUNTIME/$sub" ]; then
   if [ -n "${DRY_RUN:-}" ]; then
    echo "(dry) would mirror $RUNTIME/$sub/ → $REPO/$sub/"
   else
    python "$SYNC_HELPER" --mirror "$RUNTIME/$sub" "$REPO/$sub" "${EXCLUDES[@]}" || true
   fi
  else
   echo "(skip) $sub/ 不存在"
  fi
 done
 if [ -d "$RUNTIME/trendradar" ]; then
  if [ -n "${DRY_RUN:-}" ]; then
   echo "(dry) would mirror $RUNTIME/trendradar/ → $REPO/trendradar/"
  else
   python "$SYNC_HELPER" --mirror "$RUNTIME/trendradar" "$REPO/trendradar" "${EXCLUDES[@]}" || true
  fi
 fi
 for f in scripts_sync.sh one-key-setup.sh LICENSE README.md SETUP.md .gitignore pyproject.toml requirements.txt requirements.lock requirements-dev.txt; do
  if [ -f "$RUNTIME/$f" ]; then
   if [ -n "${DRY_RUN:-}" ]; then
    echo "(dry) would copy $f"
   else
    cp "$RUNTIME/$f" "$REPO/$f" 2>&1 | head -3 || true
   fi
  fi
 done
 if [ -z "${DRY_RUN:-}" ]; then
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "$LAST_SYNC_FILE"
 fi
fi

# === git add + commit ===
if [ -n "${DO_COMMIT:-}" ]; then
 cd "$REPO"
 CHANGED=$(git status -s)
 if [ -z "$CHANGED" ]; then
  echo "[commit] 无改动,跳过"
  exit0
 fi
 CHANGED_FILES=$(echo "$CHANGED" | head -30 | awk "{print \$2}" | tr "
" "," | sed "s/,$//")
 CHANGED_COUNT=$(echo "$CHANGED" | wc -l)
 MSG="auto-sync: $(date -u +%Y-%m-%dT%H:%M:%SZ) | ${CHANGED_COUNT} files | ${CHANGED_FILES}"
 if [ -n "${DRY_RUN:-}" ]; then
  echo "[commit --dry-run] msg: $MSG"
  git add -A
  git diff --cached --stat | tail -20
  echo "(dry-run, 不真 commit)"
 else
  git add -A
  git commit -m "$MSG"2>&1 | head -20
  echo "$MSG" > "$LAST_COMMIT_FILE"
 fi
fi

# === push ===
if [ -n "${DO_PUSH:-}" ]; then
 cd "$REPO"
 echo "[push] 检查远端 ..."
 git fetch origin 2>&1 >/dev/null || true
 LOCAL=$(git rev-parse main 2>/dev/null || echo "0")
 REMOTE=$(git rev-parse origin/main 2>/dev/null || echo "0")
 if [ "$LOCAL" != "0" ] && [ "$REMOTE" != "0" ]; then
  BEHIND=$(git rev-list --count main..origin/main 2>/dev/null || echo 0)
  echo " behind: $BEHIND"
  if [ "$BEHIND" != "0" ]; then
   echo "[push] ERROR: 本地落后 origin/main $BEHIND 个 commit,拒绝 push"
   echo "[push] 手动: cd $REPO && git pull --rebase origin main && 再跑此脚本"
   exit3
  fi
 fi
 for i in 1 2 3; do
  echo "[push] 尝试 $i/3 ..."
  if [ -n "${DRY_RUN:-}" ]; then
   git push --dry-run origin main 2>&1 | tail -15
   break
  else
   if git push origin main 2>&1 | tail -10; then
    echo "[push] OK on attempt $i"
    break
   fi
  fi
  if [ "$i" -lt3 ]; then
   DELAY=$((30 * i * i))
   echo "[push] 失败, ${DELAY}s 后重试 ..."
   sleep "$DELAY"
  fi
 done
fi

echo "=== done ==="