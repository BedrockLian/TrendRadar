"""Tests for heat_tracker.py — fingerprint, URL normalization, span calculation."""

import pytest
import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock


class TestMakeFingerprint:
    def test_same_title_same_fingerprint(self):
        from heat_tracker import make_fingerprint
        fp1 = make_fingerprint('Test Title Here', 'https://example.com/article/1')
        fp2 = make_fingerprint('Test Title Here', 'https://example.com/article/1')
        assert fp1 == fp2

    def test_different_url_different_fingerprint(self):
        from heat_tracker import make_fingerprint
        fp1 = make_fingerprint('Same Title', 'https://example.com/article/1')
        fp2 = make_fingerprint('Same Title', 'https://example.com/article/2')
        assert fp1 != fp2

    def test_case_insensitive(self):
        from heat_tracker import make_fingerprint
        fp1 = make_fingerprint('Test Title', 'https://example.com')
        fp2 = make_fingerprint('test title', 'https://example.com')
        assert fp1 == fp2

    def test_japanese_title(self):
        from heat_tracker import make_fingerprint
        fp = make_fingerprint('テスト記事タイトル', 'https://4gamer.net/games/123/')
        assert isinstance(fp, str)
        assert len(fp) == 16

    def test_empty_title(self):
        from heat_tracker import make_fingerprint
        fp = make_fingerprint('', '')
        assert isinstance(fp, str)
        assert len(fp) == 16


class TestCalcSpanHours:
    def test_same_timestamp(self):
        from heat_tracker import _calc_span_hours
        ts = '2026-05-22T10:00:00'
        assert _calc_span_hours(ts, ts) == 0.0

    def test_one_hour_diff(self):
        from heat_tracker import _calc_span_hours
        result = _calc_span_hours('2026-05-22T10:00:00', '2026-05-22T11:00:00')
        assert result == 1.0

    def test_invalid_timestamp(self):
        from heat_tracker import _calc_span_hours
        assert _calc_span_hours('invalid', '2026-05-22T10:00:00') == 0.0
        assert _calc_span_hours('2026-05-22T10:00:00', '') == 0.0


class TestGenFingerprints:
    @pytest.mark.smoke
    def test_empty_items(self):
        from heat_tracker import _gen_fingerprints
        result = _gen_fingerprints([], 'test_push', '2026-05-22T10:00:00')
        assert result == {}

    def test_basic_items(self):
        from heat_tracker import _gen_fingerprints
        items = [
            {'title': 'Test News Item', 'source_platform': 'BBC', '_coverage_count': 2, 'url': ''},
            {'title': 'Another Item', 'source_platform': 'Reuters', '_coverage_count': 1, 'url': ''},
        ]
        result = _gen_fingerprints(items, 'morning', '2026-05-22T10:00:00')
        assert len(result) == 2
        for fp, (item, signal) in result.items():
            assert signal['push_id'] == 'morning'
            assert 'platform' in signal
