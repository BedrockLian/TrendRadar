#!/usr/bin/env python3
"""Run the TrendRadar briefing pipeline as one Codex-readable task.

The task owns fetching, curation, translation, rendering and fingerprinting.
It returns one JSON object; Codex decides how to present the resulting briefing.

用法:
  $PYTHON -m trendradar.pipeline.pipeline_orchestrator
  $PYTHON -m trendradar.pipeline.pipeline_orchestrator --push-id noon  # 强制指定时段

输出 (stdout): JSON 格式结果，包含:
  - status: "ok" | "silent" | "error"
  - push_id: 识别的时段
  - briefing: 完整渲染文本 (供 LLM 备用)
  - stats: {total_items, per_domain_counts, total_elapsed, budget}
  - errors: 失败阶段列表 (status=error 时)
  - needs_deep_analysis: 晚间是否需要深度分析
  - artifacts: 生成的可复用文件路径

日志输出到 stderr。
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from trendradar.runtime.common import CST, EXIT_CONFIG_ERROR
from trendradar.runtime.settings import get_logger, get_storage
from trendradar.runtime.execution_lock import ExecutionLock
from trendradar.runtime.output_protocol import (
    append_run_record,
    budget_snapshot,
    configure_utf8_stdio,
    performance_budget_seconds,
)
from trendradar.runtime.paths import OUTPUT_DIR, ensure_data_dirs

log = get_logger('orchestrator')

PYTHON = os.environ.get("PYTHON", sys.executable)
SCRIPTS_DIR = Path(__file__).resolve().parent
from trendradar.runtime.settings import get_data_dir

DATA_DIR = get_data_dir()

# Pipeline version — must stay in sync with corresponding SKILL.md version
__version__ = "3.0.0"  # Codex-only output protocol and runtime budget


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
                log.warning(f"清理失败: {p}")
    if removed:
        log.info(f"Cleaned up: {', '.join(removed)}")


def _write_push_log(push_id: str, result: dict, errors: list):
    """Write one run outcome for the output watchdog and health checks.

    Uses atomic_write_json (P1-16) to prevent corruption from
    concurrent multi-cron writes.
    """
    from trendradar.runtime.file_utils import atomic_write_json
    log_path = DATA_DIR / "push_log.json"
    try:
        if log_path.exists():
            entries = json.loads(log_path.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                entries = []
        else:
            entries = []

        entry = {
            "push_id": push_id,
            "run_id": result.get("stats", {}).get("run_id", ""),
            "timestamp": datetime.now(CST).isoformat(),
            "status": result.get("status", "unknown"),
            "error_count": len(errors),
            "errors": errors[:5] if errors else [],  # truncate
            "total_items": result.get("stats", {}).get("total_items", 0),
            "elapsed": result.get("stats", {}).get("total_elapsed", 0),
            "within_budget": result.get("stats", {}).get("budget", {}).get("within_budget"),
            "artifact_path": result.get("artifacts", {}).get("briefing_path", ""),
        }
        entries.append(entry)

        # Keep last 100 entries
        if len(entries) > 100:
            entries = entries[-100:]

        # P1-16: 用 atomic_write_json 替代手写 mkstemp + os.replace
        atomic_write_json(log_path, entries, indent=2)
    except Exception as e:
        log.warning(f"push_log write 失败: {e}")


def list_pipeline_steps() -> dict:
    """Return the canonical pipeline step definitions (SSOT for Agent consumption).

    v2.9: All stages now use direct function calls — no subprocess overhead.
    """
    return {
        "version": __version__,
        "python": PYTHON,
        "steps": [
            {"number": 0, "name": "slot_detect", "func": "detect_current_slot",
             "description": "Detect current push slot from timeline.yaml (direct call)"},
            {"number": 1, "name": "push_prepare", "script": "trendradar.pipeline.push_prepare",
             "description": "Fetch RSS feeds + curate top items (fetch + curate)"},
            {"number": 2, "name": "track_events", "script": "trendradar.reporting.track_events",
             "description": "Track event continuity (morning only)"},
            {"number": 3, "name": "ai_translate", "script": "trendradar.intelligence.ai_translate",
             "description": "Translate foreign articles to Chinese"},
            {"number": 4, "name": "render_markdown", "script": "trendradar.reporting.render_markdown",
             "description": "Render the curated items as canonical Markdown"},
            {"number": 5, "name": "record_fingerprints", "script": "trendradar.pipeline.record_fingerprints",
             "description": "Record item fingerprints for cross-slot dedup"},
        ],
    }


def verify_version() -> dict:
    """Lightweight self-check: verify all referenced scripts exist and are importable.

    Returns {ok: bool, errors: [str]}.
    """
    errors = []
    modules = [
        SCRIPTS_DIR / "push_slot_detect.py",
        SCRIPTS_DIR / "push_prepare.py",
        SCRIPTS_DIR.parent / "intelligence" / "ai_translate.py",
        SCRIPTS_DIR.parent / "reporting" / "render_markdown.py",
        SCRIPTS_DIR / "record_fingerprints.py",
    ]
    for module_path in modules:
        if not module_path.exists():
            errors.append(f"Missing pipeline module: {module_path}")
    return {"ok": len(errors) == 0, "errors": errors}


def version_check_and_exit() -> None:
    """Perform self-check on startup. Exit with EXIT_CONFIG_ERROR if scripts missing.

    Called when --check-version is passed, or as a pre-flight before main().
    """
    result = verify_version()
    if not result["ok"]:
        log.error(json.dumps({
            "status": "error",
            "exit_code": EXIT_CONFIG_ERROR,
            "reason": "version_check_failed",
            "errors": result["errors"],
        }, ensure_ascii=False))
        print(json.dumps({
            "status": "error",
            "exit_code": EXIT_CONFIG_ERROR,
            "reason": "version_check_failed",
            "errors": result["errors"],
        }, ensure_ascii=False), file=sys.stderr)
        sys.exit(EXIT_CONFIG_ERROR)


def run_stage(name: str, func, *args, **kwargs) -> dict:
    """Run a pipeline stage as a direct function call with timing.

    Args:
        name: Human-readable stage name for logging
        func: Callable to execute
        *args, **kwargs: Passed to func
    Returns:
        {'ok': bool, 'result': any, 'elapsed': float, 'error': str|None}
    """
    log.info(f"⏳ {name}...")
    t0 = time.monotonic()
    try:
        result = func(*args, **kwargs)
        elapsed = time.monotonic() - t0
        log.info(f"✅ {name} ({elapsed:.1f}s)")
        return {"ok": True, "result": result, "elapsed": elapsed, "error": None}
    except Exception as e:
        elapsed = time.monotonic() - t0
        log.error(f"❌ {name} ({elapsed:.1f}s): {e}", exc_info=True)
        return {"ok": False, "result": None, "elapsed": elapsed, "error": str(e)}


def _emit_error_result(
    *, push_id: str | None, errors: list[str], started_monotonic: float, budget_seconds: float,
    reason: str | None = None,
) -> int:
    """Emit the same machine-readable envelope for pre-render failures."""
    result = {
        "protocol_version": 1,
        "status": "error",
        "task": "daily-briefing",
        "push_id": push_id,
        "reason": reason or "pipeline_stage_failed",
        "errors": errors,
        "stats": {
            "total_elapsed": time.monotonic() - started_monotonic,
            "budget": budget_snapshot(time.monotonic() - started_monotonic, budget_seconds),
        },
    }
    append_run_record(result)
    print(json.dumps(result, ensure_ascii=False))
    return 1



def main():
    configure_utf8_stdio()
    import argparse
    parser = argparse.ArgumentParser(description="TrendRadar briefing pipeline")
    parser.add_argument("--push-id", choices=['morning', 'noon', 'evening'],
                        help="强制指定时段，跳过自动检测")
    parser.add_argument("--skip-fetch", action="store_true", help="跳过 fetch（使用已有缓存）")
    parser.add_argument("--output", choices=["json", "text"], default="json", help="输出格式")
    parser.add_argument("--list-steps", action="store_true",
                        help="输出管道步骤定义（SSOT，供 Agent 动态读取）")
    parser.add_argument("--check-version", action="store_true",
                        help="启动前自检：校验所有依赖脚本是否存在")
    parser.add_argument("--budget-seconds", type=float, default=None,
                        help="全链路预算，默认 180 秒")
    args = parser.parse_args()

    # ── Special modes (no pipeline execution) ──────────────────
    if args.list_steps:
        print(json.dumps(list_pipeline_steps(), ensure_ascii=False, indent=2))
        return 0

    if args.check_version:
        version_check_and_exit()
        print(json.dumps({"status": "ok", "version": __version__}, ensure_ascii=False))
        return 0

    ensure_data_dirs()
    started_at = datetime.now().astimezone().isoformat()
    started_monotonic = time.monotonic()
    budget_seconds = args.budget_seconds or performance_budget_seconds()
    lock = ExecutionLock("briefing-pipeline", stale_after=max(300, int(budget_seconds * 2)))
    if not lock.acquire():
        record = {
            "protocol_version": 1,
            "status": "busy",
            "task": "daily-briefing",
            "reason": "another pipeline run is active",
        }
        print(json.dumps(record, ensure_ascii=False))
        return 2

    import atexit
    atexit.register(lock.release)

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
        log.warning(f"DB migration skipped: {e}", exc_info=True)
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
        from trendradar.pipeline.push_slot_detect import detect_current_slot
        slot = detect_current_slot()
        if slot is None:
            _cleanup_silent("unknown")
            print(json.dumps({
                "protocol_version": 1,
                "status": "silent",
                "task": "daily-briefing",
                "reason": "NO_SLOT: outside push window",
                "stats": {"budget": budget_snapshot(time.monotonic() - started_monotonic, budget_seconds)},
            }, ensure_ascii=False))
            return 0
        push_id = slot["push_id"]
        dedup_flag = slot["dedup_flag"]

    stats["push_id"] = push_id

    # ── Stage 1: push_prepare (fetch + curate) ─────────────────
    from trendradar.pipeline.push_prepare import run_curation
    prep = run_stage(f"push_prepare ({push_id})", run_curation, push_id, args.skip_fetch)
    stats["stages"]["push_prepare"] = prep["elapsed"]

    # ── _proxy_health: 从共享 raw 缓存提取 fetch 失败源 + 代理 URL ─
    try:
        from trendradar.pipeline.push_prepare import get_raw_today  # Sprint 3: 共享内存缓存
        _raw = get_raw_today()
        _failed = _raw.get("failed_sources", [])
        stats["proxy_health"] = {
            "proxy_url": _raw.get("proxy_url", ""),
            "failed_sources": _failed,
            "failed_count": len(_failed),
            "fetched_items": len(_raw.get("items", [])),
        }
        if _failed:
            log.warning(f"⚠️ {len(_failed)} 源 fetch 失败: {_failed[:5]}{'...' if len(_failed) > 5 else ''}")
    except Exception as _e:
        log.debug(f"proxy_health 提取失败（非阻塞）: {_e}")

    if not prep["ok"]:
        errors.append(f"push_prepare: {prep['error']}")
        return _emit_error_result(
            push_id=push_id, errors=errors,
            started_monotonic=started_monotonic, budget_seconds=budget_seconds,
        )

    # ── Stage 2: track_events (morning only) ───────────────────
    if push_id == "morning":
        from trendradar.reporting import track_events as _te
        curated_path = DATA_DIR / f"curated_morning_{datetime.now(CST).strftime('%Y%m%d')}.json"
        if curated_path.exists():
            def _track():
                today_items = _te.load_curated(str(curated_path))
                yesterday_path = _te.find_yesterday_morning()
                if not yesterday_path or not Path(yesterday_path).exists():
                    return None
                yesterday_items = _te.load_curated(yesterday_path)
                return _te.compare(today_items, yesterday_items)

            te = run_stage(f"track_events ({push_id})", _track)
            stats["stages"]["track_events"] = te["elapsed"]
            if not te["ok"]:
                errors.append(f"track_events: {te['error']}")

    # ── Stage 3: ai_translate ──────────────────────────────────
    import asyncio as _asyncio

    def _run_translate():
        from trendradar.intelligence.ai_translate import process_curated
        remaining = budget_seconds - (time.monotonic() - started_monotonic)
        if remaining <= 0:
            raise TimeoutError("performance budget exhausted before translation")
        return _asyncio.run(
            _asyncio.wait_for(process_curated(push_id), timeout=max(1, remaining))
        )

    translate_result = run_stage(f"ai_translate ({push_id})", _run_translate)
    stats["stages"]["ai_translate"] = translate_result["elapsed"]

    # P1-13: 把 LLM 统计透传到 stats
    if translate_result.get("ok") and isinstance(translate_result.get("result"), dict):
        llm_stats = translate_result["result"].get("_llm_stats")
        if llm_stats:
            stats["llm_stats"] = llm_stats
            log.info(
                f"📊 LLM 统计: {llm_stats['api_call_count']} API calls, "
                f"~{llm_stats['estimated_tokens']} tokens, "
                f"{llm_stats['translated_count']} items translated"
            )

    if not translate_result["ok"]:
        err = translate_result.get("error", "")
        if "no content" in str(err).lower() or "no api key" in str(err).lower():
            log.info(f"ai_translate skipped (no content / no API key) — continuing")
        else:
            errors.append(f"ai_translate: {str(err)[:200]}")

    # ── Stage 4: Render ────────────────────────────────────────
    from trendradar.reporting.render_markdown import render_briefing
    render = run_stage(f"render_markdown ({push_id})", render_briefing, push_id)
    stats["stages"]["render_markdown"] = render["elapsed"]

    if not render["ok"]:
        errors.append(f"render_markdown: {render['error'][:200]}")
        return _emit_error_result(
            push_id=push_id, errors=errors,
            started_monotonic=started_monotonic, budget_seconds=budget_seconds,
        )

    briefing = render["result"]
    if not briefing:
        errors.append("render_markdown: empty output")
        return _emit_error_result(
            push_id=push_id, errors=errors,
            started_monotonic=started_monotonic, budget_seconds=budget_seconds,
        )

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
                    log.warning(f"清理失败: {f}")
        silent_result = {
            "protocol_version": 1,
            "status": "silent",
            "task": "daily-briefing",
            "started_at": started_at,
            "finished_at": datetime.now().astimezone().isoformat(),
            "reason": "no new items",
            "push_id": push_id,
            "stats": {
                "total_elapsed": time.monotonic() - started_monotonic,
                "budget": budget_snapshot(time.monotonic() - started_monotonic, budget_seconds),
            },
        }
        append_run_record(silent_result)
        print(json.dumps(silent_result, ensure_ascii=False))
        return 0

    # ── Stage 4.5: sanity_check ────────────────────────────────
    from trendradar.reporting.sanity_check import (
        check_banned_phrases, check_html_residue, strip_orchestrator_preamble,
    )
    clean_briefing = strip_orchestrator_preamble(briefing)
    banned = check_banned_phrases(clean_briefing)
    if banned:
        errors.append(f"sanity_check: 禁语命中 {banned}")
        log.error(f"禁语: {banned}")
        # FATAL — reject push
        return _emit_error_result(
            push_id=push_id, errors=errors,
            started_monotonic=started_monotonic, budget_seconds=budget_seconds,
            reason=f"banned_phrase_detected: {banned}",
        )
    residue = check_html_residue(clean_briefing)
    if residue:
        log.warning(f"HTML残留: {residue}")
        # Not fatal, but logged
    stats["stages"]["sanity_check"] = True

    # ── Stage 5: record_fingerprints ───────────────────────────
    from trendradar.pipeline.record_fingerprints import record as record_fp
    record = run_stage(f"record_fingerprints ({push_id})", record_fp, push_id)
    stats["stages"]["record_fingerprints"] = record["elapsed"]
    if not record["ok"]:
        errors.append(f"record_fingerprints: {record.get('error', '')[:200]}")

    # ── Read curated data for stats ────────────────────────────
    try:
        from trendradar.config.domains import DOMAINS
        curated_path = DATA_DIR / f"curated_{push_id}.json"
        if curated_path.exists():
            curated_data = json.loads(curated_path.read_text(encoding="utf-8"))
            stats["total_items"] = curated_data.get("total", sum(len(curated_data.get(d, [])) for d in DOMAINS))
            for d in DOMAINS:
                stats["per_domain"][d] = len(curated_data.get(d, []))
            stats["run_id"] = curated_data.get("run_id", "")
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.error(f"读取精选统计失败: {e}")

    # ── Build output ───────────────────────────────────────────
    total_elapsed = time.monotonic() - started_monotonic
    stats["total_elapsed"] = total_elapsed
    stats["budget"] = budget_snapshot(total_elapsed, budget_seconds)

    if not stats["budget"]["within_budget"]:
        errors.append(
            f"performance_budget_exceeded: {total_elapsed:.1f}s > {budget_seconds:.1f}s"
        )

    final_status = "ok" if not errors else ("partial" if len(errors) < 3 else "error")
    if not stats["budget"]["within_budget"]:
        final_status = "error"
    artifact_dir = OUTPUT_DIR / datetime.now(CST).strftime("%Y-%m-%d")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / f"{push_id}.md"
    artifact_path.write_text(briefing, encoding="utf-8")
    result = {
        "protocol_version": 1,
        "status": final_status,
        "task": "daily-briefing",
        "started_at": started_at,
        "finished_at": datetime.now().astimezone().isoformat(),
        "push_id": push_id,
        "briefing": briefing,
        "stats": stats,
        "errors": errors if errors else [],
        "needs_deep_analysis": push_id == "evening" and final_status != "error",
        "artifacts": {
            "briefing_path": str(artifact_path),
            "curated_path": str(DATA_DIR / f"curated_{push_id}_{datetime.now(CST).strftime('%Y%m%d')}.json"),
        },
    }

    # ── Record push outcome log (for delivery failure tracking) ─
    _write_push_log(push_id, result, errors)
    append_run_record(result)

    if args.output == "text":
        print(briefing)
    else:
        print(json.dumps(result, ensure_ascii=False))

    get_storage().close_db()
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
