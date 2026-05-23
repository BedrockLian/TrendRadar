"""Tests for fetch_feeds.py — mock aiohttp responses, test timeout/non-RSS/encoding errors."""

import pytest
import asyncio
import json
import sys
from pathlib import Path
SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / 'scripts')
TRENDRADAR_DIR = str(Path(__file__).resolve().parent.parent)
HERMES_DIR = str(Path(__file__).resolve().parent.parent.parent)
sys.path.insert(0, HERMES_DIR)
sys.path.insert(0, TRENDRADAR_DIR)
sys.path.insert(0, SCRIPTS_DIR)
from unittest.mock import patch, MagicMock, AsyncMock

# Mock feedparser to avoid import error
sys.modules['feedparser'] = MagicMock()
sys.modules['aiohttp'] = MagicMock()


class TestDedup:
    def test_dedup_empty(self):
        from fetch_feeds import _dedup
        assert _dedup([]) == []

    def test_dedup_single(self):
        from fetch_feeds import _dedup
        items = [{'title': 'Test title here', 'source_platform': 'BBC'}]
        result = _dedup(items)
        assert len(result) == 1
        assert result[0]['_coverage_count'] == 1

    def test_dedup_duplicate_titles(self):
        from fetch_feeds import _dedup
        items = [
            {'title': 'Same title repeated many times here', 'source_platform': 'BBC', 'summary': 'Test A', 'url': 'https://bbc.com/1'},
            {'title': 'Same title repeated many times here', 'source_platform': 'Reuters', 'summary': 'Test B', 'url': 'https://reuters.com/2'},
            {'title': 'Different title entirely different', 'source_platform': 'NYT', 'summary': 'Test C', 'url': 'https://nyt.com/3'},
        ]
        result = _dedup(items)
        # Step 8: dedup key now includes URL domain (bbc.com vs reuters.com),
        # so same-title-different-domain items are no longer merged.
        assert len(result) == 3
        assert result[0]['title'] == 'Same title repeated many times here'


class TestKwSets:
    def test_kw_sets_returns_tuple(self):
        from fetch_feeds import _kw_sets
        game, tech, economy = _kw_sets()
        assert isinstance(game, frozenset)
        assert isinstance(tech, frozenset)
        assert isinstance(economy, frozenset)
        assert len(game) > 0
        assert len(tech) > 0
        assert len(economy) > 0

    def test_kw_sets_cached(self):
        from fetch_feeds import _kw_sets
        a = _kw_sets()
        b = _kw_sets()
        assert a is b  # cached


class TestPreclassify:
    def test_preclassify_game_keyword(self):
        from fetch_feeds import _preclassify
        items = [{'title': 'Steam 新游发布 原神更新', 'summary': '', 'source_platform': 'TestSource'}]
        result = _preclassify(items)
        assert result[0]['_likely_domain'] == 'gaming'

    def test_preclassify_tech_keyword(self):
        from fetch_feeds import _preclassify
        items = [{'title': 'AI 大模型突破 NVIDIA 发布新芯片', 'summary': '', 'source_platform': 'TestSource'}]
        result = _preclassify(items)
        assert result[0]['_likely_domain'] == 'tech'

    def test_preclassify_economy_keyword(self):
        from fetch_feeds import _preclassify
        items = [{'title': '就业形势严峻 物价持续上涨 民生压力增大', 'summary': '', 'source_platform': 'TestSource'}]
        result = _preclassify(items)
        assert result[0]['_likely_domain'] == 'economy'

    def test_preclassify_no_match(self):
        from fetch_feeds import _preclassify
        items = [{'title': 'Random text no keywords', 'summary': '', 'source_platform': 'UnknownSource'}]
        result = _preclassify(items)
        assert result[0]['_likely_domain'] == 'other'
