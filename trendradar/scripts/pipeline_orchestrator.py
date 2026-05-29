from trendradar.scripts.common import CST
#!/usr/bin/env python3
"""
pipeline_orchestrator.py — 一键运行 TrendRadar 推送全流程。

替代 LLM 手动执行 10 个步骤：
  检测时段 → 抓取+精选 → 事件追踪 → 并行(翻译+直连) → 渲染 → 分片 → 指纹记录

用法:
  $PYTHON scripts/pipeline_orchestrator.py
  $PYTHON scripts/pipeline_orchestrator.py --push-id noon  # 强制指定时段

输出 (stdout): JSON 格式结果，包含:
  - status: "ok" | "silent" | "error"
  - push_id: 识别的时段
  - fragments: 分片后的 WeCom 消息数组 (status=ok 时)
  - briefing: 完整渲染文本 (供 LLM 备用)
  - stats: {total_items, per_domain_counts}
  - errors: 失败阶段列表 (status=error 时)
  - needs_deep_analysis: 晚间是否需要深度分析
  - curated_path: 精选数据文件路径

日志输出到 stderr。
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from trendradar.scripts.exitcodes import EXIT_CONFIG_ERROR
from trendradar.scripts.settings import get_logger

log = get_logger('orchestrator')

CST = timezone(timedelta(hours=8))
PYTHON = os.environ.get("PYTHON", sys.executable)
PYTHON_GIL = os.environ.get("PYTHON_GIL", "0")
SCRIPTS_DIR = Path(__file__).resolve().parent
TREND_DIR = SCRIPTS_DIR.parent
DATA_DIR = TREND_DIR / "data"

# Ensure PYTHONPATH is set for subprocess, whitelist env vars (stop API key leak)
_ALLOWED_ENV = {
    'PYTHONPATH', 'PYTHON_GIL', 'TRENDRADAR_HOME', 'TRENDRADAR_LOG_LEVEL',
    'PATH', 'HOME', 'USER', 'LANG', 'LC_ALL', 'DEEPSEEK_API_KEY',
    'HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'no_proxy',
}
_ENV = {k: v for k, v in os.environ.items() if k in _ALLOWED_ENV}
_ENV["PYTHONPATH"] = str(TREND_DIR.parent)  # /home/asus/.hermes
_ENV["PYTHON_GIL"] = PYTHON_GIL

# Pipeline version — must stay in sync with corresponding SKILL.md version
__version__ = "2.8.0"


def _cleanup_silent(push_id: str):
    """Physically remove intermediate files for a silenced push.
    
    Prevents Agent from seeing stale fragment data and "画蛇添足".
    Called on NO_SLOT, empty briefing, or EXIT_NO_CONTENT conditions.
    """
    today = datetime.now(CST).strftime('%Y%m%d')
    patterns = [
        (DATA_DIR / f"curated_{push_id}.json"),
        (DATA_DIR / f"curated_{push_id}_{today}.json"),
    ]
    removed = []
    for p in patterns:
        if p.exists():
            try:
                p.unlink()
                removed.append(str(p.name))
            except OSError:
                pass
    if removed:
        log.info(f"Cleaned up: {', '.join(removed)}")


def _write_push_log(push_id: str, result: dict, errors: list):
    """Write push outcome to push_log.json for delivery failure tracking.
    
    Records: push_id, timestamp, status, fragment_count, error_count.
    Used by delivery_watchdog to detect partial-delivery failures.
    
    Uses atomic write (temp + os.replace) to prevent corruption from
    concurrent multi-cron writes.
    """
    import os as _os
    import tempfile as _tempfile
    log_path = DATA_DIR / "push_log.json"
    try:
        if log_path.exists():
            log = json.loads(log_path.read_text())
            if not isinstance(log, list):
                log = []
        else:
            log = []

        entry = {
            "push_id": push_id,
            "run_id": result.get("stats", {}).get("run_id", ""),
            "timestamp": datetime.now(CST).isoformat(),
            "status": result.get("status", "unknown"),
            "fragment_count": len(result.get("fragments", [])),
            "error_count": len(errors),
            "errors": errors[:5] if errors else [],  # truncate
            "total_items": result.get("stats", {}).get("total_items", 0),
            "elapsed": result.get("stats", {}).get("total_elapsed", 0),
        }
        log.append(entry)

        # Keep last 100 entries
        if len(log) > 100:
            log = log[-100:]

        log_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = _tempfile.mkstemp(dir=log_path.parent, prefix='.tmp_push_log_')
        try:
            with _os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(log, f, ensure_ascii=False, indent=2)
            _os.replace(tmp, log_path)
        except Exception:
            _os.unlink(tmp)
            raise
    except Exception as e:
        log.error(f"push_log write failed: {e}")


def _run(cmd: list, timeout: int = 300, capture: bool = True) -> dict:
    """Run a subprocess and return {ok, stdout, stderr, exit_code}."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=timeout,
            cwd=str(TREND_DIR),
            env=_ENV,
        )
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": f"Timeout after {timeout}s", "exit_code": -1}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e), "exit_code": -1}


def detect_slot() -> dict:
    """Detect current push slot from timeline.yaml."""
    r = _run([PYTHON, str(SCRIPTS_DIR / "push_slot_detect.py")])
    if not r["ok"]:
        return {"slot": None, "error": r["stderr"]}

    result = {"slot": None, "dedup_flag": "", "extra": "", "filter": "keyword"}
    for line in r["stdout"].split("\n"):
        if "=" in line:
            k, v = line.split("=", 1)
            result[k.lower()] = v

    result["slot"] = result.get("push_id")
    return result


def detect_push_id() -> tuple:
    """Return (push_id, dedup_flag) or (None, error_msg)."""
    slot_info = detect_slot()
    push_id = slot_info.get("slot")
    if push_id == "NO_SLOT" or push_id is None:
        return None, f"NO_SLOT: current time not in push schedule. Detected: {slot_info}"
    dedup = slot_info.get("dedup_flag", "")
    return push_id, dedup


def list_pipeline_steps() -> dict:
    """Return the canonical pipeline step definitions (SSOT for Agent consumption).

    Instead of manually maintaining steps in SKILL.md, the Agent should call
    `pipeline_orchestrator.py --list-steps` at startup to discover available steps.

    Returns a JSON-serializable dict with step_number, name, command, and description.
    """
    return {
        "version": __version__,
        "python": PYTHON,
        "steps": [
            {"number": 0, "name": "slot_detect", "script": "push_slot_detect.py",
             "description": "Detect current push slot from timeline.yaml"},
            {"number": 1, "name": "push_prepare", "script": "push_prepare.py",
             "description": "Fetch RSS feeds + curate top items (fetch + curate)"},
            {"number": 2, "name": "track_events", "script": "track_events.py",
             "description": "Track event continuity (morning only)"},
            {"number": 3, "name": "parallel", "scripts": ["ai_translate.py", "batch_fetch.py"],
             "description": "Parallel: translate foreign articles + fetch full text",
             "parallel": True},
            {"number": 4, "name": "render_markdown", "script": "render_markdown.py",
             "description": "Render curated items to WeCom markdown"},
            {"number": 5, "name": "fragment_push", "script": "fragment_push.py",
             "description": "Split markdown into WeCom-safe byte-counted fragments"},
            {"number": 6, "name": "record_fingerprints", "script": "record_fingerprints.py",
             "description": "Record item fingerprints for cross-slot dedup"},
        ],
    }


def verify_version() -> dict:
    """Lightweight self-check: verify all referenced scripts exist and are importable.

    Returns {ok: bool, errors: [str]}.
    """
    errors = []
    scripts = [
        "push_slot_detect.py", "push_prepare.py", "ai_translate.py",
        "batch_fetch.py", "render_markdown.py", "fragment_push.py",
        "record_fingerprints.py",
    ]
    for script in scripts:
        p = SCRIPTS_DIR / script
        if not p.exists():
            errors.append(f"Missing script: {p}")
    return {"ok": len(errors) == 0, "errors": errors}


def version_check_and_exit():
    """Perform self-check on startup. Exit with EXIT_CONFIG_ERROR if scripts missing.

    Called when --check-version is passed, or as a pre-flight before main().
    """
    result = verify_version()
    if not result["ok"]:
        print(json.dumps({
            "status": "error",
            "exit_code": EXIT_CONFIG_ERROR,
            "reason": "version_check_failed",
            "errors": result["errors"],
        }, ensure_ascii=False), file=sys.stderr)
        sys.exit(EXIT_CONFIG_ERROR)
    return result


def run_stage(name: str, cmd: list, timeout: int = 300) -> dict:
    """Run a pipeline stage with timing."""
    log.info(f"⏳ {name}...")
    t0 = time.time()
    result = _run(cmd, timeout=timeout)
    elapsed = time.time() - t0
    if result["ok"]:
        log.info(f"✅ {name} ({elapsed:.1f}s)")
    else:
        log.error(f"❌ {name} ({elapsed:.1f}s): {result['stderr'][:200]}")
    result["elapsed"] = elapsed
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TrendRadar 推送全流程编排器")
    parser.add_argument("--push-id", choices=['morning', 'noon', 'evening'],
                        help="强制指定时段，跳过自动检测")
    parser.add_argument("--skip-fetch", action="store_true", help="跳过 fetch（使用已有缓存）")
    parser.add_argument("--output", choices=["json", "text"], default="json", help="输出格式")
    parser.add_argument("--list-steps", action="store_true",
                        help="输出管道步骤定义（SSOT，供 Agent 动态读取）")
    parser.add_argument("--check-version", action="store_true",
                        help="启动前自检：校验所有依赖脚本是否存在")
    args = parser.parse_args()

    # ── Special modes (no pipeline execution) ──────────────────
    if args.list_steps:
        print(json.dumps(list_pipeline_steps(), ensure_ascii=False, indent=2))
        return 0

    if args.check_version:
        version_check_and_exit()
        print(json.dumps({"status": "ok", "version": __version__}, ensure_ascii=False))
        return 0

    # ── Step 0: Auto-migrate database ─────────────────────────
    # Ensure DB schema is up-to-date before any operation.
    # Prevents sqlite3.OperationalError from stale schema.
    try:
        from trendradar.migrations.runner import migrate
        db_path = DATA_DIR / "fingerprints.db"
        if db_path.exists():
            ver = migrate(db_path)
            if ver > 0:
                log.info(f"DB schema v{ver}")
    except Exception as e:
        log.warning(f"DB migration skipped: {e}")
        # Non-fatal — continue with existing schema

    errors = []
    stats = {
        "push_id": None,
        "total_items": 0,
        "per_domain": {},
        "stages": {},
    }

    # ── Stage 0: Detect slot ───────────────────────────────────
    if args.push_id:
        push_id = args.push_id
        dedup_flag = "--dedup" if push_id != "morning" else ""
    else:
        push_id, dedup_flag = detect_push_id()
        if push_id is None:
            _cleanup_silent(dedup_flag.split(":")[-1].strip() if ":" in dedup_flag else "unknown")
            print(json.dumps({
                "status": "silent",
                "reason": dedup_flag,
                "fragments": [],  # 显式空数组，防止 Agent 画蛇添足
            }, ensure_ascii=False))
            return 0

    stats["push_id"] = push_id

    # ── Stage 1: push_prepare (fetch + curate) ─────────────────
    prep_cmd = [PYTHON, str(SCRIPTS_DIR / "push_prepare.py"), "--push-id", push_id]
    if dedup_flag:
        prep_cmd.append(dedup_flag)
    if args.skip_fetch:
        prep_cmd.append("--skip-fetch")

    prep = run_stage(f"push_prepare ({push_id})", prep_cmd)
    stats["stages"]["push_prepare"] = prep["elapsed"]

    if not prep["ok"]:
        errors.append(f"push_prepare: {prep['stderr'][:300]}")
        print(json.dumps({"status": "error", "errors": errors, "push_id": push_id}, ensure_ascii=False))
        return 1

    # Parse NEW_COUNT from prep output (appears after the curated JSON)
    # Use regex to be robust against JSON mixed with other output
    import re as _re
    new_count = 0
    nc_match = _re.search(r'NEW_COUNT=(\d+)', prep["stdout"])
    if nc_match:
        new_count = int(nc_match.group(1))

    # ── Stage 2: track_events (morning only) ───────────────────
    if push_id == "morning":
        curated_path = DATA_DIR / f"curated_morning_{datetime.now(CST).strftime('%Y%m%d')}.json"
        if curated_path.exists():
            te_cmd = [PYTHON, str(SCRIPTS_DIR / "track_events.py"), "--today", str(curated_path)]
            te = run_stage(f"track_events ({push_id})", te_cmd)
            stats["stages"]["track_events"] = te["elapsed"]
            if not te["ok"]:
                errors.append(f"track_events: {te['stderr'][:200]}")

    # ── Stage 3: Parallel (ai_translate + batch_fetch) ─────────
    import concurrent.futures

    curated_now_path = DATA_DIR / f"curated_{push_id}.json"
    translate_cmd = [PYTHON, str(SCRIPTS_DIR / "ai_translate.py"), "--push-id", push_id]
    fetch_cmd = [PYTHON, str(SCRIPTS_DIR / "batch_fetch.py"), "--push-id", push_id]

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        fut_translate = executor.submit(run_stage, f"ai_translate ({push_id})", translate_cmd)
        fut_fetch = executor.submit(run_stage, f"batch_fetch ({push_id})", fetch_cmd, 180)

        translate_result = fut_translate.result()
        fetch_result = fut_fetch.result()

    stats["stages"]["ai_translate"] = translate_result["elapsed"]
    stats["stages"]["batch_fetch"] = fetch_result["elapsed"]

    # ai_translate returns EXIT_NO_CONTENT(2) when API key missing or nothing to translate
    # — these are not fatal, pipeline should continue with untranslated content
    if not translate_result["ok"] and translate_result.get("exit_code") != 2:
        errors.append(f"ai_translate: {translate_result['stderr'][:200]}")
    elif not translate_result["ok"]:
        log.info(f"ai_translate skipped (no content / no API key) — continuing")
    if not fetch_result["ok"]:
        errors.append(f"batch_fetch: {fetch_result['stderr'][:200]}")

    # ── Stage 4: Render ────────────────────────────────────────
    render_cmd = [PYTHON, str(SCRIPTS_DIR / "render_markdown.py"), "--push-id", push_id]
    render = run_stage(f"render_markdown ({push_id})", render_cmd)
    stats["stages"]["render_markdown"] = render["elapsed"]

    if not render["ok"]:
        errors.append(f"render_markdown: {render['stderr'][:200]}")
        print(json.dumps({"status": "error", "errors": errors, "push_id": push_id}, ensure_ascii=False))
        return 1

    briefing = render["stdout"]

    # Check for empty briefing (no items)
    if not briefing or "共 0 条" in briefing or "[SILENT]" in briefing:
        # Still run sanity check if any content was produced (defensive)
        if briefing and len(briefing) > 50:
            log.info(f"Empty briefing detected, running sanity check anyway")
        _cleanup_silent(push_id)
        # Also clean up any partial fetch/curate artifacts
        for pattern in [f"fetch_*{push_id}*.json", f"curated_{push_id}*.json"]:
            for f in DATA_DIR.glob(pattern):
                try:
                    f.unlink()
                except OSError:
                    pass
        print(json.dumps({
            "status": "silent",
            "reason": "no new items",
            "push_id": push_id,
            "fragments": [],  # 显式空数组，防止 Agent 画蛇添足
        }, ensure_ascii=False))
        return 0

    # ── Stage 4.5: sanity_check ────────────────────────────────
    from trendradar.scripts.sanity_check import (
        check_banned_phrases, check_html_residue, strip_orchestrator_preamble,
    )
    clean_briefing = strip_orchestrator_preamble(briefing)
    banned = check_banned_phrases(clean_briefing)
    if banned:
        errors.append(f"sanity_check: 禁语命中 {banned}")
        log.error(f"禁语: {banned}")
        # FATAL — reject push
        print(json.dumps({
            "status": "error",
            "reason": "banned_phrase_detected",
            "banned": banned,
        }, ensure_ascii=False))
        return 1
    residue = check_html_residue(clean_briefing)
    if residue:
        log.warning(f"HTML残留: {residue}")
        # Not fatal, but logged
    stats["stages"]["sanity_check"] = True

    # ── Stage 5: Fragment ──────────────────────────────────────
    fragment_cmd = [PYTHON, str(SCRIPTS_DIR / "fragment_push.py")]
    try:
        fragment = subprocess.run(
            fragment_cmd,
            input=briefing,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(TREND_DIR),
            env=_ENV,
        )
        frag_ok = fragment.returncode == 0
        fragments_json = fragment.stdout.strip() if frag_ok else "[]"
    except subprocess.TimeoutExpired:
        errors.append("fragment_push: Timeout after 30s")
        frag_ok = False
        fragments_json = "[]"
    except Exception as e:
        errors.append(f"fragment_push: {e}")
        frag_ok = False
        fragments_json = "[]"

    # Parse fragments — fragment_push now outputs ONLY JSON on stdout
    fragments = []
    try:
        # Strip any log-level prefix that may have leaked to stdout
        # fragment_push guarantees JSON on stdout and logs on stderr
        cleaned = fragments_json.strip()
        if cleaned.startswith("["):
            # Find the first complete JSON array
            depth = 0
            end = 0
            for i, c in enumerate(cleaned):
                if c == '[':
                    depth += 1
                elif c == ']':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end > 0:
                fragments = json.loads(cleaned[:end])
            else:
                fragments = json.loads(cleaned)
        else:
            # Fallback: if no JSON array, use as single fragment
            fragments = [briefing]
    except (json.JSONDecodeError, ValueError):
        fragments = [briefing]  # fallback: single fragment

    stats["stages"]["fragment_push"] = 0
    stats["fragment_count"] = len(fragments)

    # ── Stage 6: record_fingerprints ───────────────────────────
    record_cmd = [PYTHON, str(SCRIPTS_DIR / "record_fingerprints.py"), "--push-id", push_id]
    record = run_stage(f"record_fingerprints ({push_id})", record_cmd)
    stats["stages"]["record_fingerprints"] = record["elapsed"]
    if not record["ok"]:
        errors.append(f"record_fingerprints: {record['stderr'][:200]}")

    # ── Read curated data for stats ────────────────────────────
    try:
        curated_path = DATA_DIR / f"curated_{push_id}.json"
        if curated_path.exists():
            curated_data = json.loads(curated_path.read_text())
            domains = ["top_headlines", "foreign_china", "tech", "economy", "gaming"]
            stats["total_items"] = curated_data.get("total", sum(len(curated_data.get(d, [])) for d in domains))
            for d in domains:
                stats["per_domain"][d] = len(curated_data.get(d, []))
            stats["run_id"] = curated_data.get("run_id", "")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.error(f"读取精选统计失败: {e}")

    # ── Build output ───────────────────────────────────────────
    total_elapsed = sum(v for k, v in stats["stages"].items() if isinstance(v, (int, float)))
    stats["total_elapsed"] = total_elapsed

    final_status = "ok" if not errors else ("partial" if len(errors) < 3 else "error")
    result = {
        "status": final_status,
        "push_id": push_id,
        "fragments": fragments,
        "briefing": briefing,
        "stats": stats,
        "errors": errors if errors else [],
        "needs_deep_analysis": push_id == "evening" and final_status != "error",
        "curated_path": str(DATA_DIR / f"curated_{push_id}_{datetime.now(CST).strftime('%Y%m%d')}.json"),
    }

    # ── Record push outcome log (for delivery failure tracking) ─
    _write_push_log(push_id, result, errors)

    if args.output == "text":
        print(briefing)
    else:
        print(json.dumps(result, ensure_ascii=False))

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
