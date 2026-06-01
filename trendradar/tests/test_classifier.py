"""Tests for classifier.py — _classify_items / classify_items domain routing."""

import pytest
from unittest.mock import patch


# ── Shared test item factory ────────────────────────────────────────────


def _item(title="", summary="", source_platform="", url=""):
    return {
        'title': title,
        'summary': summary,
        'source_platform': source_platform,
        'url': url or 'https://example.com/test',
    }


# ── Tests ───────────────────────────────────────────────────────────────


class TestClassifyItems:
    """Unit tests for classify_items() domain classification."""

    @pytest.mark.smoke
    def test_domestic_tech_headline_lands_in_tech(self):
        """Chinese tech headline with tech keywords → 'tech' domain."""
        from trendradar.scripts.classifier import classify_items

        items = [
            _item(
                title='中国发布新一代AI芯片突破性进展',
                summary='科研团队在半导体领域取得重大技术突破',
                source_platform='新华社',
            ),
        ]
        headline, remaining, foreign_china = classify_items(items)

        # Should NOT be a headline (no safety/politics keyword hit), NOT foreign_china
        assert len(headline) == 0
        assert len(foreign_china) == 0
        assert len(remaining) == 1
        assert remaining[0]['_likely_domain'] == 'tech'

    def test_foreign_china_keywords_maps_to_foreign_china(self):
        """Foreign source + China keywords → 'foreign_china' domain."""
        from trendradar.scripts.classifier import classify_items

        items = [
            _item(
                title='China semiconductor industry faces new US export controls',
                summary='Beijing considers retaliatory measures on chip ban',
                source_platform='BBC 中国',
            ),
        ]
        headline, remaining, foreign_china = classify_items(items)

        assert len(foreign_china) == 1
        assert foreign_china[0]['_likely_domain'] == 'foreign_china'
        assert len(headline) == 0
        assert len(remaining) == 0

    def test_gaming_keywords_maps_to_gaming(self):
        """Items with game keywords → 'gaming' domain."""
        from trendradar.scripts.classifier import classify_items

        items = [
            _item(
                title='原神新版本即将上线 Steam Deck 同步支持',
                summary='HoYoverse announced Genshin Impact version update',
                source_platform='机核',
            ),
        ]
        headline, remaining, foreign_china = classify_items(items)

        assert len(remaining) == 1
        assert remaining[0]['_likely_domain'] == 'gaming'
        assert len(foreign_china) == 0
        assert len(headline) == 0

    def test_economy_keywords_maps_to_economy(self):
        """Items with economy keywords → 'economy' domain."""
        from trendradar.scripts.classifier import classify_items

        items = [
            _item(
                title='青年失业率降至16.3% 就业形势持续回暖',
                summary='国家统计局公布最新就业情况，消费市场复苏明显',
                source_platform='新华社',
            ),
        ]
        headline, remaining, foreign_china = classify_items(items)

        # economy keywords (就业, 消费, 失业, etc.) should route to economy
        assert len(remaining) >= 1
        domains = [r.get('_likely_domain') for r in remaining]
        assert 'economy' in domains
        assert len(foreign_china) == 0

    def test_empty_items_returns_all_empty_lists(self):
        """Empty item list → three empty lists returned."""
        from trendradar.scripts.classifier import classify_items

        headline, remaining, foreign_china = classify_items([])

        assert headline == []
        assert remaining == []
        assert foreign_china == []
