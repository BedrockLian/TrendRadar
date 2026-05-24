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

CST = timezone(timedelta(hours=8))
PYTHON = os.environ.get("PYTHON", "/usr/local/bin/python3.14t")
PYTHON_GIL = os.environ.get("PYTHON_GIL", "0")
SCRIPTS_DIR = Path(__file__).resolve().parent
TREND_DIR = SCRIPTS_DIR.parent
DATA_DIR = TREND_DIR / "data"

# Ensure PYTHONPATH is set for subprocess
_ENV = os.environ.copy()
_ENV["PYTHONPATH"] = str(TREND_DIR.parent)  # /home/asus/.hermes
_ENV["PYTHON_GIL"] = PYTHON_GIL


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


def run_stage(name: str, cmd: list, timeout: int = 300) -> dict:
    """Run a pipeline stage with timing."""
    print(f"[{datetime.now(CST).strftime('%H:%M:%S')}] ⏳ {name}...", file=sys.stderr)
    t0 = time.time()
    result = _run(cmd, timeout=timeout)
    elapsed = time.time() - t0
    if result["ok"]:
        print(f"[{datetime.now(CST).strftime('%H:%M:%S')}] ✅ {name} ({elapsed:.1f}s)", file=sys.stderr)
    else:
        print(f"[{datetime.now(CST).strftime('%H:%M:%S')}] ❌ {name} ({elapsed:.1f}s): {result['stderr'][:200]}", file=sys.stderr)
    result["elapsed"] = elapsed
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="TrendRadar 推送全流程编排器")
    parser.add_argument("--push-id", help="强制指定时段 (morning/noon/evening)，跳过自动检测")
    parser.add_argument("--skip-fetch", action="store_true", help="跳过 fetch（使用已有缓存）")
    parser.add_argument("--output", choices=["json", "text"], default="json", help="输出格式")
    args = parser.parse_args()

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
            print(json.dumps({"status": "silent", "reason": dedup_flag}, ensure_ascii=False))
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
    new_count = 0
    for line in prep["stdout"].split("\n"):
        if line.startswith("NEW_COUNT="):
            new_count = int(line.split("=", 1)[1])

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

    if not translate_result["ok"]:
        errors.append(f"ai_translate: {translate_result['stderr'][:200]}")
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
        print(json.dumps({"status": "silent", "reason": "no new items", "push_id": push_id}, ensure_ascii=False))
        return 0

    # ── Stage 5: Fragment ──────────────────────────────────────
    fragment_cmd = [PYTHON, str(SCRIPTS_DIR / "fragment_push.py")]
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

    # Parse fragments, stripping log lines
    fragments = []
    try:
        # fragment_push writes JSON array on a single line, + log lines on stderr
        # But stdout may have multiple lines if logging leaks
        lines = fragments_json.split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                fragments = json.loads(line)
                break
    except json.JSONDecodeError:
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
    except Exception:
        pass

    # ── Build output ───────────────────────────────────────────
    total_elapsed = sum(v for k, v in stats["stages"].items() if isinstance(v, (int, float)))
    stats["total_elapsed"] = total_elapsed

    result = {
        "status": "ok",
        "push_id": push_id,
        "fragments": fragments,
        "briefing": briefing,
        "stats": stats,
        "errors": errors if errors else [],
        "needs_deep_analysis": push_id == "evening",
        "curated_path": str(DATA_DIR / f"curated_{push_id}_{datetime.now(CST).strftime('%Y%m%d')}.json"),
    }

    if args.output == "text":
        print(briefing)
    else:
        print(json.dumps(result, ensure_ascii=False))

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
