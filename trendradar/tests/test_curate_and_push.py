"""Tests for curate_and_push.py - keyword extraction, scoring, curation logic."""

import sys
from pathlib import Path

SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / 'scripts')
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import pytest
import json
from datetime import datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))
_RECENT_TS = (datetime.now(CST) - timedelta(hours=2)).strftime('%Y-%m-%dT%H:%M:%SZ')


class TestKw:
    """ALL_KEYWORDS — domain 关键词映射"""

    EXPECTED_DOMAINS = {'tech', 'economy', 'gaming', 'foreign_china',
                        'top_headlines', 'junk', 'safety', 'politics'}

    def _kw(self):
        from trendradar.config.keywords import ALL_KEYWORDS
        return ALL_KEYWORDS

    def test_all_domains_present(self):
        kw = self._kw()
        assert 'tech' in kw
        assert 'economy' in kw
        assert 'game' in kw or 'gaming' in kw

    def test_all_values_are_frozenset(self):
        kw = self._kw()
        for domain, kws in kw.items():
            assert isinstance(kws, frozenset), f'{domain} keywords is not frozenset'

    def test_no_empty_strings(self):
        kw = self._kw()
        for domain, kws in kw.items():
            assert '' not in kws, f'{domain} contains empty keyword'

    def test_min_keyword_counts(self):
        kw = self._kw()
        assert len(kw.get('tech', frozenset())) >= 10
        assert len(kw.get('economy', frozenset())) >= 10
        assert len(kw.get('game', frozenset())) >= 5

    def test_game_domain_covers_hoYoverse(self):
        kw = self._kw()
        game_kw = kw.get('game', frozenset())
        assert '米哈游' in game_kw
        assert 'HoYoverse' in game_kw
        assert '原神' in game_kw


class TestScore:
    """_score() — 条目质量评分"""

    STRONG_ITEM = {
        'title': '中国发布新一代AI芯片突破性进展',
        'source_platform': '路透社',
        'url': 'https://example.com/1',
        'timestamp': _RECENT_TS,
        '_coverage_count': 5,
    }

    WEAK_ITEM = {
        'title': '?',
        'source_platform': 'Unknown',
        'url': '',
        'timestamp': '',
    }

    def _score(self, item, domain='tech'):
        from curate_and_push import _score as fn
        return fn(item, domain)

    def _min_score(self):
        from curate_and_push import MIN_SCORE
        return MIN_SCORE

    def test_strong_item_passes(self):
        s = self._score(self.STRONG_ITEM, 'tech')
        assert s['pass'] is True
        assert s['total'] >= self._min_score()

    def test_weak_item_fails(self):
        s = self._score(self.WEAK_ITEM, 'tech')
        assert s['pass'] is False
        assert s['total'] < self._min_score()

    def test_economy_domain_boost(self):
        from curate_and_push import _econ_boost
        boost_sources = _econ_boost()
        if boost_sources:
            econ_src = next(iter(boost_sources))
            item = {**self.STRONG_ITEM, 'source_platform': econ_src}
            s = self._score(item, 'economy')
            assert s['pass'] is True

    def test_old_article_no_recency(self):
        old = {
            'title': '旧闻标题足够长来通过清晰度检测',
            'source_platform': '路透社',
            'url': 'https://example.com/old',
            'timestamp': (datetime.now(CST) - timedelta(hours=48)).strftime('%Y-%m-%dT%H:%M:%SZ'),
        }
        s = self._score(old, 'tech')
        assert isinstance(s['total'], int)
        assert isinstance(s['pass'], bool)


class TestCurateDomain:
    """_curate_domain() — 单 domain 精选"""

    def _curate_domain(self, items, domain):
        from curate_and_push import _curate_domain as fn
        return fn(items, domain)

    def _max_per_domain(self):
        from curate_and_push import MAX_PER_DOMAIN
        return MAX_PER_DOMAIN

    def test_filters_empty_summary(self):
        items = [
            {'title': '无摘要条目应被过滤掉', 'summary': '',
             'source_platform': '新华网', 'url': 'https://xinhua.com/1',
             'timestamp': _RECENT_TS,
             '_likely_domain': 'tech', '_drop': False},
            {'title': '合格条目标题足够长通过评分', 'summary': '这是一条有摘要的新闻内容',
             'source_platform': '路透社', 'url': 'https://reuters.com/1',
             'timestamp': _RECENT_TS,
             '_likely_domain': 'tech', '_drop': False},
        ]
        result = self._curate_domain(items, 'tech')
        titles = [i['title'] for i in result]
        assert '无摘要条目应被过滤掉' not in titles
        assert '合格条目标题足够长通过评分' in titles

    def test_respects_max_per_domain(self):
        max_n = self._max_per_domain().get('tech', 15)
        items = []
        for i in range(max_n + 10):
            items.append({
                'title': f'科技新闻标题第{i}号足够长通过',
                'summary': f'这是第{i}条科技新闻的摘要内容',
                'source_platform': '36氪',
                'url': f'https://36kr.com/p/{i}',
                'timestamp': '2026-05-21T10:00:00Z',
                '_likely_domain': 'tech',
                '_drop': False,
            })
        result = self._curate_domain(items, 'tech')
        assert len(result) <= max_n

    def test_filters_drop_items(self):
        items = [
            {'title': '正常条目标题够长', 'summary': '正常摘要',
             'source_platform': '36氪', '_likely_domain': 'tech', '_drop': True},
            {'title': '另一个正常条目标题也够', 'summary': '另一个摘要',
             'source_platform': '路透社', '_likely_domain': 'tech', '_drop': False},
        ]
        result = self._curate_domain(items, 'tech')
        titles = [i['title'] for i in result]
        assert '正常条目标题够长' not in titles
