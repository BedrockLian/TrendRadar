# Double `scripts/` directory shadow trap (2026-06-03)

## TL;DR

TrendRadar has **two copies** of `scripts/` (and `config/`):

- **Legacy/outer**: `~/.hermes/trendradar/scripts/` — namespace package (no top-level `__init__.py`)
- **Nested/inner**: `~/.hermes/trendradar/trendradar/scripts/` — proper package (has `trendradar/__init__.py`)

Python's namespace package resolution (PEP 420) **always picks the outer/legacy copy** when you write `import trendradar.scripts.fetch_feeds`. **Any code you edit in the nested copy never runs at cron time** until you also copy it to the legacy copy.

The trap is sneaky: `importlib.util.find_spec('trendradar.scripts.fetch_feeds').origin` returns the **nested** (correct) path, but `from trendradar.scripts.fetch_feeds import fetch_all` actually loads the **legacy** path. **find_spec and actual import disagree on namespace packages.**

## Background

TrendRadar's repo has been reorganized multiple times. As of 2026-06-03:

```
~/.hermes/trendradar/                     ← TRENDRADAR_HOME (cron agent cwd)
├── LICENSE, README.md, SETUP.md, ...
├── __init__.py                           ← (does not exist → namespace package)
├── scripts/                              ← LEGACY copy (shadow wins)
│   ├── __init__.py                       ← 2KB docstring
│   ├── fetch_feeds.py                    ← OLD version with _get_parse_pool
│   ├── push_prepare.py                   ← OLD version with ThreadPoolExecutor
│   ├── pipeline_orchestrator.py          ← OLD version
│   ├── ... 30+ more files ...
│   └── config/...
│
└── trendradar/                           ← nested python package
    ├── __init__.py
    ├── scripts/                          ← NESTED copy (correct, but shadowed)
    │   ├── __init__.py
    │   ├── fetch_feeds.py                ← NEW (your edits)
    │   ├── push_prepare.py
    │   ├── pipeline_orchestrator.py
    │   └── ...
    └── config/, migrations/, tests/, ...

~/TrendRadar/                              ← git worktree (separate clone)
├── trendradar/scripts/...                ← yet another copy
```

The legacy `scripts/` and nested `trendradar/scripts/` should be **identical** content, but they drift over time. The `scripts_sync.sh` script exists to keep them in sync, but it's not auto-run.

## Why the trap fires

When `cron` runs `python3.14t trendradar/scripts/pipeline_orchestrator.py` from cwd `~/.hermes/trendradar`:

1. `sys.path[0]` = script's dir = `trendradar/scripts/` (relative → `/home/asus/.hermes/trendradar/trendradar/scripts/`)
2. `sys.path[1]` = cwd = `/home/asus/.hermes/trendradar/`
3. `sys.path[2]` = `$PYTHONPATH` = `/home/asus/.hermes/`

When orchestrator does `from trendradar.scripts.push_prepare import run_curation`:

- Python scans sys.path looking for `trendradar` package
- Finds `/home/asus/.hermes/trendradar/` (sys.path[1]) — **no `__init__.py`** → treated as **namespace package**
- Looks for `scripts` subpackage within namespace → finds `/home/asus/.hermes/trendradar/scripts/__init__.py` (LEGACY)
- **Imports the LEGACY `scripts/`** even though the script being run is from the nested `trendradar/scripts/`

The `importlib.util.find_spec()` function returns the NESTED (correct) path because it does a different kind of resolution, but actual `import` statement uses Python's package finder which honors namespace package rules. **This is the source of the "spec says X, runtime says Y" mismatch that wastes hours of debugging.**

## Symptoms

1. **`NameError: name '_get_parse_pool' is not defined`** even though the source clearly defines `_PARSE_POOL = Lazy(_make_parse_pool)` — your fixes don't take effect
2. **Logic changes "have no effect"**: you patch code, restart, same old behavior
3. **Tests pass, but cron fails**: pytest uses `sys.path[0]` = test dir, imports nested package correctly; cron uses different sys.path order, imports legacy
4. **Debug print statements never appear** even though you added them to "the" file

## 5-second diagnosis

```bash
cd ~/.hermes/trendradar
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
PYTHON_GIL=0 PYTHONPATH=/home/asus/.hermes /usr/local/bin/python3.14t -c "
import importlib.util
spec = importlib.util.find_spec('trendradar.scripts.fetch_feeds')
print('find_spec says:', spec.origin)
import trendradar.scripts.fetch_feeds as ff
print('actual load:  ', ff.__file__)
print('match?        ', spec.origin == ff.__file__)
"
```

**Expected output (healthy)**:
```
find_spec says: /home/asus/.hermes/trendradar/trendradar/scripts/fetch_feeds.py
actual load:   /home/asus/.hermes/trendradar/trendradar/scripts/fetch_feeds.py
match?         True
```

**Output when shadow trap is active**:
```
find_spec says: /home/asus/.hermes/trendradar/trendradar/scripts/fetch_feeds.py
actual load:   /home/asus/.hermes/trendradar/scripts/fetch_feeds.py   ← LEGACY!
match?         False
```

## Fix: 3 options

### Option 1: Sync the two copies (quickest)

```bash
# After editing nested/inner copy:
cp /home/asus/.hermes/trendradar/trendradar/scripts/<file>.py \
   /home/asus/.hermes/trendradar/scripts/<file>.py

# Verify:
diff /home/asus/.hermes/trendradar/trendradar/scripts/<file>.py \
     /home/asus/.hermes/trendradar/scripts/<file>.py
# Should print nothing
```

### Option 2: Add `__init__.py` to outer root (cleanest long-term)

```bash
touch /home/asus/.hermes/trendradar/__init__.py
```

This makes `~/.hermes/trendradar/` an **explicit** package, which gets priority over the namespace package behavior. **But** the explicit package would have NO `scripts/` subpackage of its own, so Python falls through to the nested `trendradar/` dir's scripts. **After this fix, the nested copy is the one that loads.**

**Risks**:
- Any code that does `import trendradar.scripts.foo` from outside the trendradar dir and expects the legacy copy would now break
- The two copies might already be out of sync, so the fix would cause a "what changed?" surprise

**Recommend doing this only after Option 1 syncs them to a known-good state.**

### Option 3: Delete one copy (most invasive but cleanest)

```bash
# Pick ONE canonical location and keep only that
rm -rf /home/asus/.hermes/trendradar/scripts
rm -rf /home/asus/.hermes/trendradar/config
# Now nested is the only one
```

After this, all imports resolve to `~/.hermes/trendradar/trendradar/scripts/`. **But** cron prompts and LLM agent code paths that reference `scripts/foo.py` (relative to TRENDRADAR_HOME) would break. Need to update all cron prompts and skill references.

## What's currently in `scripts_sync.sh`

(As of 2026-06-02, before the trap was diagnosed)

```bash
#!/usr/bin/env bash
# scripts_sync.sh — keep root scripts/ and trendradar/scripts/ in sync
# Default direction: inner → outer (cron uses outer, so prep before cron)
# Usage:
#   scripts_sync.sh              # inner → outer
#   scripts_sync.sh --reverse    # outer → inner
#   scripts_sync.sh --check      # dry run

DIRECTION="inner-to-outer"
[ "$1" = "--reverse" ] && DIRECTION="outer-to-inner"
[ "$1" = "--check" ] && DIRECTION="check"

INNER=/home/asus/.hermes/trendradar/trendradar
OUTER=/home/asus/.hermes/trendradar

if [ "$DIRECTION" = "inner-to-outer" ]; then
  rsync -a --delete \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='*.bak' \
    "$INNER/scripts/" "$OUTER/scripts/"
elif [ "$DIRECTION" = "outer-to-inner" ]; then
  rsync -a --delete \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='*.bak' \
    "$OUTER/scripts/" "$INNER/scripts/"
else
  diff -r "$INNER/scripts/" "$OUTER/scripts/" 2>&1 | grep -v __pycache__ | head -20
fi
```

**This is a manual tool — not auto-run by cron or git hooks.** If you forget to run it after editing, the cron path silently loads stale code.

## Suggested improvements (not yet implemented)

1. **Add `__init__.py` to outer root** to make shadow resolution deterministic (Option 2)
2. **Replace legacy outer `scripts/` and `config/` with symlinks to nested** (defeats shadow but loses GitHub Web UI niceness)
3. **Add a cron preflight check**: `scripts_sync.sh --check` should exit 1 if drift detected, log a warning
4. **Modify cron prompts** to invoke `bash scripts_sync.sh` before `python3 pipeline_orchestrator.py` (defensive)
5. **Audit-fix-workflow.md** should mandate "after editing, run diagnosis command, verify find_spec == actual_load"

## Related traps

- **Concurrent fetches with PYTHON_GIL=0** → `InterpreterPoolExecutor` can't pickle → switch to `ThreadPoolExecutor` (default)
- **`Lazy(...)` wrapper vs function**: `_PARSE_POOL = Lazy(_make_parse_pool)` requires `_PARSE_POOL.get()` not `_PARSE_POOL()`
- **`ensure_raw_exists` cache trap**: 0-item raw file locks the cache for 4h; explicit `cache_valid = False` after `< 50` check
- **Empty `__init__.py` shows as 0-byte file in GitHub Web UI** — fill with docstring (already fixed)
- **Symlink `config -> trendradar/config`** in repo root: GitHub Web shows it as a one-line text file. Already replaced with real directory (commit 5c21d19)

## Repro recipe (start to finish in 30 sec)

```bash
# Edit the nested (correct) file
echo 'print("[NESTED VERSION]")' >> \
  /home/asus/.hermes/trendradar/trendradar/scripts/fetch_feeds.py

# Run cron path
PYTHON_GIL=0 PYTHONPATH=/home/asus/.hermes /usr/local/bin/python3.14t \
  -c "import trendradar.scripts.fetch_feeds as ff; print('loaded:', ff.__file__)"
# Should show: /home/asus/.hermes/trendradar/trendradar/scripts/fetch_feeds.py
# But you'll see: /home/asus/.hermes/trendradar/scripts/fetch_feeds.py
# (no [NESTED VERSION] print, because the legacy file was loaded, not the new one)

# Fix:
cp /home/asus/.hermes/trendradar/trendradar/scripts/fetch_feeds.py \
   /home/asus/.hermes/trendradar/scripts/fetch_feeds.py
# Now the [NESTED VERSION] print fires.
```
