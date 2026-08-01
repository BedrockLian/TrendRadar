"""Tests for the machine-readable RSS source scorecard."""

import json
from pathlib import Path

from ops.codex.source_audit import audit, freshness_score, render_markdown

ROOT = Path(__file__).resolve().parents[1]


def test_source_scorecard_covers_every_enabled_source():
    result = audit(live=False)
    config = json.loads((ROOT / "src" / "trendradar" / "config" / "sources.json").read_text(encoding="utf-8"))
    enabled = {source["id"] for source in config["data_sources"] if source.get("enabled", True)}
    actual = {row["source_id"] for row in result["rows"]}

    assert actual == enabled
    assert result["source_count"] == len(enabled)


def test_fallback_ids_point_to_configured_sources():
    result = audit(live=False)
    source_ids = {row["source_id"] for row in result["rows"]}

    for row in result["rows"]:
        assert set(row["fallback_ids"]).issubset(source_ids)


def test_freshness_score_is_bounded_and_monotonic():
    assert freshness_score(None, 24) == 0
    assert freshness_score(12, 24) == 5
    assert freshness_score(48, 24) == 4
    assert freshness_score(200, 24) == 1


def test_markdown_scorecard_contains_transport_and_decision():
    markdown = render_markdown(audit(live=False))

    assert "# TrendRadar RSS 来源评判表" in markdown
    assert "official" in markdown
    assert "news_aggregator" not in markdown
    assert "core" in markdown
    assert "CNA 亚洲" in markdown


def test_enabled_sources_exclude_uncontrolled_aggregators():
    result = audit(live=False)

    assert all(
        row["transport_kind"] not in {"news_aggregator", "third_party_mirror"}
        for row in result["rows"]
    )


def test_source_metadata_keeps_transport_and_identity_consistent():
    config = json.loads((ROOT / "src" / "trendradar" / "config" / "sources.json").read_text(encoding="utf-8"))
    by_id = {source["id"]: source for source in config["data_sources"]}

    assert by_id["reuters"]["transport_kind"] == "news_aggregator"
    assert by_id["reuters"]["fallback_ids"]
    assert by_id["zaobao_china"]["transport_kind"] == "third_party_mirror"
    assert by_id["bbc_china"]["language"] == "zh"
    assert by_id["nature_news"]["feed_url"].startswith("https://")
    assert by_id["zaobao_china"]["enabled"] is False
    assert by_id["zaobao_world"]["enabled"] is False
    assert by_id["reuters"]["enabled"] is False
    assert by_id["ap_news"]["enabled"] is False
    assert by_id["afp"]["enabled"] is False
    assert by_id["arxiv_ai"]["enabled"] is False
    assert by_id["techcrunch"]["enabled"] is False
    assert by_id["nintendo_life"]["enabled"] is False
    assert by_id["cna_asia"]["transport_kind"] == "official"
    assert by_id["cna_world"]["transport_kind"] == "official"
    assert by_id["pbs_newshour"]["transport_kind"] == "official"
    assert by_id["rest_world"]["transport_kind"] == "official"
    assert "mit_news" in by_id
    assert "ifanr" in by_id
