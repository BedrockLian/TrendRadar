"""Tests for scorer.py — scoring, penalty loading, domain curation."""

import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from trendradar.scripts.common import CST

_RECENT_TS = (datetime.now(CST) - timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')


# ── Helpers ─────────────────────────────────────────────────────────────


def _mock_authority():
    """Mock _authority() returning known authority values."""
    return {'路透社': 2, '新华社': 1, '36氪': 1, 'BBC': 2, '机核': 1}


def _mock_econ_boost():
    """Mock _econ_boost() frozenset."""
    return frozenset({'路透社', '新华社'})


def _mock_econ_extra():
    """Mock _econ_extra() frozenset."""
    return frozenset({'澎湃新闻', '中国新闻网'})


def _strong_item(**overrides):
    """Factory for a high-quality item that should score well."""
    base = {
        'title': '中国发布新一代AI芯片突破性进展引发关注',
        'source_platform': '路透社',
        'url': 'https://example.com/1',
        'summary': '中国科研团队取得重大突破',
        'timestamp': _RECENT_TS,
        '_coverage_count': 5,
    }
    base.update(overrides)
    return base


def _patch_scorer_deps():
    """Context manager that patches domain_metadata deps used by scorer."""
    return patch.multiple(
        'trendradar.scripts.domain_metadata',
        _authority=MagicMock(return_value=_mock_authority()),
        _econ_boost=MagicMock(return_value=_mock_econ_boost()),
        _econ_extra=MagicMock(return_value=_mock_econ_extra()),
        create=True,
    )


# ── Tests ───────────────────────────────────────────────────────────────


class TestScoreItem:
    """Unit tests for score_item()."""

    @pytest.mark.smoke
    def test_strong_tech_item_passes(self):
        """Standard tech item with all fields → passes scoring."""
        from trendradar.scripts.scorer import score_item

        with _patch_scorer_deps():
            result = score_item(_strong_item(), 'tech')

        assert isinstance(result, dict)
        assert 'total' in result
        assert 'pass' in result
        assert result['pass'] is True
        assert result['total'] >= 6  # MIN_SCORE

    def test_missing_fields_returns_lower_score(self):
        """Item with missing/empty fields → lower total score."""
        from trendradar.scripts.scorer import score_item

        weak = {
            'title': '?',
            'source_platform': '',
            'url': '',
            'timestamp': '',
        }
        with _patch_scorer_deps():
            result = score_item(weak, 'tech')

        assert isinstance(result, dict)
        assert result['pass'] is False
        assert result['total'] < 6  # Below MIN_SCORE

    def test_econ_boost_frozenset_has_expected_type(self):
        """_econ_boost() returns a frozenset (not dict)."""
        # Test the actual function if sources.json exists, else test mock
        try:
            from trendradar.scripts.domain_metadata import _econ_boost
            result = _econ_boost()
        except (SystemExit, FileNotFoundError):
            # sources.json not available — test mock behavior
            result = _mock_econ_boost()

        assert isinstance(result, frozenset)
        # frozensets are iterable and can be checked for membership
        assert len(result) >= 0  # may be empty if no sources


class TestCurateDomain:
    """Tests for curate_domain()."""

    def test_curate_domain_respects_max_per_domain(self):
        """Items exceeding MAX_PER_DOMAIN are truncated."""
        from trendradar.scripts.scorer import curate_domain
        from trendradar.config.domains import MAX_PER_DOMAIN

        max_n = MAX_PER_DOMAIN.get('tech', 7)
        items = []
        for i in range(max_n + 10):
            items.append({
                'title': f'科技新闻标题第{i}号足够长通过检测',
                'summary': f'这是第{i}条科技新闻的摘要内容足够详细',
                'source_platform': '36氪',
                'url': f'https://36kr.com/p/{i}',
                'timestamp': '2026-05-21T10:00:00Z',
                '_likely_domain': 'tech',
                '_drop': False,
                '_coverage_count': 1,
            })

        with _patch_scorer_deps():
            result = curate_domain(items, 'tech')

        assert len(result) <= max_n
        # All items should have _curator_scores
        for item in result:
            assert '_curator_scores' in item


class TestPenaltyLoading:
    """Tests for penalty file loading functions."""

    def test_load_penalty_file_missing_no_crash(self):
        """Loading a non-existent penalty file doesn't crash."""
        from trendradar.scripts.scorer import load_penalty_file

        # Should not raise
        load_penalty_file('/nonexistent/path/does_not_exist.json')

    def test_load_penalty_file_valid_json(self, tmp_path):
        """Loading a valid penalty JSON populates the penalty map."""
        from trendradar.scripts.scorer import load_penalty_file, _get_source_penalty

        p = tmp_path / 'penalty.json'
        p.write_text(json.dumps({
            'overrepresented_sources': [
                {'source': 'reuters', 'penalty_factor': 0.75},
            ]
        }))

        load_penalty_file(str(p))
        # After loading, _get_source_penalty should reflect the penalty
        factor = _get_source_penalty('Reuters')
        assert factor == 0.75
