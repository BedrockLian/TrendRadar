"""Integration smoke tests for real Markdown and task-entry execution."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "trendradar"
CST = timezone(timedelta(hours=8))


@pytest.fixture
def runtime(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    today = datetime.now(CST).strftime("%Y%m%d")
    curated = {
        "top_headlines": [{
            "title": "测试标题",
            "summary": "测试摘要",
            "source_platform": "测试来源",
            "url": "https://example.com/test",
        }],
        "foreign_china": [],
        "tech": [],
        "economy": [],
        "gaming": [],
        "total": 1,
    }
    (data / f"curated_noon_{today}.json").write_text(json.dumps(curated, ensure_ascii=False), encoding="utf-8")
    return tmp_path


@pytest.mark.integration
def test_render_markdown_uses_codex_header(runtime):
    from trendradar.reporting import render_markdown

    render_markdown.DATA_DIR = runtime / "data"
    output = render_markdown.render_briefing("noon")
    assert "### TrendRadar 日报" in output
    assert "测试标题" in output


@pytest.mark.integration
def test_generated_plan_prompt_is_parseable():
    from trendradar.cli.gen_cron_prompt import generate_cron_prompt, get_pipeline_steps

    output = generate_cron_prompt(get_pipeline_steps())
    assert "TrendRadar Codex 计划任务" in output
    assert "trendradar-output-watchdog" in output
    assert "直接输出到当前聊天框" in output
    assert "不要用本地预览" in output


def test_production_chat_output_contract_is_documented():
    skill = (ROOT / "skills" / "trendradar" / "news-secretary" / "SKILL.md").read_text(encoding="utf-8")
    pipeline = (ROOT / "docs" / "PIPELINE.md").read_text(encoding="utf-8")

    assert "briefing" in skill
    assert "最终回复必须是 `briefing` 中的 Markdown 本体" in skill
    assert "不以本地预览、浏览器链接或 artifact 路径替代正文" in pipeline
