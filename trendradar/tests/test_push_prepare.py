"""Tests for push_prepare.py — empty input, curation pipeline."""

import pytest


class TestCountNewItems:
    def test_empty_curated(self):
        from push_prepare import count_new_items
        curated = {'top_headlines': [], 'tech': [], 'economy': [], 'gaming': []}
        result = count_new_items(curated, [])
        assert result == 0

    def test_no_fingerprints(self):
        from push_prepare import count_new_items
        curated = {
            'top_headlines': [{'title': 'Test title 1'}],
            'tech': [{'title': 'Test title 2'}],
            'economy': [],
            'gaming': [],
        }
        result = count_new_items(curated, [])
        assert result == 2

    def test_all_fingerprints_match(self):
        from push_prepare import count_new_items
        curated = {
            'top_headlines': [{'title': 'Already seen'}],
            'tech': [],
            'economy': [],
            'gaming': [],
        }
        result = count_new_items(curated, ['Already seen'])
        assert result == 0

    def test_partial_match(self):
        from push_prepare import count_new_items
        curated = {
            'top_headlines': [{'title': 'New item here'}, {'title': 'Old item here'}],
            'tech': [],
            'economy': [],
            'gaming': [],
        }
        result = count_new_items(curated, ['Old item here'])
        assert result == 1


class TestStripItem:
    def test_strip_removes_internal_fields(self):
        from push_prepare import strip_item
        item = {
            'title': 'Test', 'url': 'https://example.com',
            '_curator_scores': {'total': 5}, '_heat': {}, '_likely_domain': 'tech',
            '_drop': False, '_coverage_count': 1,
        }
        result = strip_item(item)
        assert 'title' in result
        assert 'url' in result
        assert '_curator_scores' not in result
        assert '_heat' not in result
        assert '_likely_domain' not in result
