"""Focused end-to-end contract tests for the Codex task protocol."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def test_pipeline_steps_have_no_platform_delivery_stage():
    from trendradar.pipeline.pipeline_orchestrator import list_pipeline_steps

    steps = list_pipeline_steps()
    names = [step["name"] for step in steps["steps"]]
    assert names == [
        "slot_detect",
        "push_prepare",
        "track_events",
        "ai_translate",
        "render_markdown",
        "record_fingerprints",
    ]
    assert all("fragment" not in json.dumps(step, ensure_ascii=False).lower() for step in steps["steps"])


def test_version_check_finds_current_dependencies():
    from trendradar.pipeline.pipeline_orchestrator import verify_version

    result = verify_version()
    assert result == {"ok": True, "errors": []}


def test_budget_snapshot_marks_slow_runs():
    from trendradar.runtime.output_protocol import budget_snapshot

    assert budget_snapshot(1.25, 180)["within_budget"] is True
    slow = budget_snapshot(181, 180)
    assert slow["within_budget"] is False
    assert slow["remaining_seconds"] == -1.0


def test_plan_contains_six_codex_jobs():
    plan = json.loads((ROOT / "src" / "trendradar" / "config" / "plan.json").read_text(encoding="utf-8"))
    assert plan["timezone"] == "Asia/Shanghai"
    assert plan["performance_budget_seconds"] == 180
    assert len(plan["jobs"]) == 6


def test_execution_lock_blocks_second_owner(tmp_path, monkeypatch):
    import trendradar.runtime.execution_lock as module

    monkeypatch.setattr(module, "LOCK_DIR", tmp_path)
    first = module.ExecutionLock("test")
    second = module.ExecutionLock("test")
    assert first.acquire() is True
    assert second.acquire() is False
    first.release()
    assert second.acquire() is True
    second.release()
