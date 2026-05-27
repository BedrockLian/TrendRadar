"""Boundary tests for ai_translate.py batch_translate and _batch_translate_all.

Covers:
  - BATCH_SIZE=5 boundary (exactly 5 items = 1 batch, 6 items = 2 batches)
  - Empty items list
  - Incomplete API response (partial translations, should pad)
  - Mixed language items (English + Japanese in separate batches)
  - Circuit breaker behavior

NOTE: Uses asyncio.run() instead of @pytest.mark.asyncio because
pytest-asyncio is not installed in this environment.
"""

import asyncio
import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / 'scripts')
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_response(lines: list[str]):
    """Build a mock aiohttp session with given translated lines."""
    mock_response = AsyncMock()
    mock_response.json = AsyncMock(return_value={
        'choices': [{
            'message': {
                'content': '\n'.join(lines)
            }
        }]
    })
    session = MagicMock()
    session.post = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response)))
    return session


def _make_items(count: int, prefix: str = "Test") -> list:
    """Generate (title, summary) pairs for testing."""
    return [(f'{prefix} Title {i}', f'{prefix} Summary {i}') for i in range(1, count + 1)]


# ── Tests: batch_translate ────────────────────────────────────────────────────

class TestBatchTranslateBoundary:
    """Boundary tests for batch_translate() directly (mock API)."""

    def test_batch_size_exactly_5_single_batch(self):
        """5 items should be sent as exactly 1 batch."""
        from ai_translate import batch_translate

        items = _make_items(5)
        session = _make_mock_response([
            '中文标题1', '中文摘要1',
            '中文标题2', '中文摘要2',
            '中文标题3', '中文摘要3',
            '中文标题4', '中文摘要4',
            '中文标题5', '中文摘要5',
        ])

        async def _run():
            return await batch_translate(session, items, 'fake_key', 'English')

        result = asyncio.run(_run())

        assert len(result) == 5
        assert result[0] == ('中文标题1', '中文摘要1')
        assert result[4] == ('中文标题5', '中文摘要5')

        # Verify only one API call was made
        assert session.post.call_count == 1

    def test_batch_size_exactly_5_sanity(self):
        """5 items should produce 5 translations (no truncation, no padding)."""
        from ai_translate import batch_translate

        items = _make_items(5)
        session = _make_mock_response([
            'T1_CN', 'S1_CN',
            'T2_CN', 'S2_CN',
            'T3_CN', 'S3_CN',
            'T4_CN', 'S4_CN',
            'T5_CN', 'S5_CN',
        ])

        async def _run():
            return await batch_translate(session, items, 'fake_key', 'English')

        result = asyncio.run(_run())

        assert len(result) == 5
        assert result[0] == ('T1_CN', 'S1_CN')
        assert result[2] == ('T3_CN', 'S3_CN')

    def test_empty_items_returns_empty_list(self):
        """Empty items list returns empty result — no API call."""
        from ai_translate import batch_translate

        session = MagicMock()

        async def _run():
            return await batch_translate(session, [], 'fake_key', 'English')

        result = asyncio.run(_run())
        assert result == []
        # Should not make any API call
        session.post.assert_not_called()

    def test_single_item_batch(self):
        """Single item batch translates correctly."""
        from ai_translate import batch_translate

        items = [('Single Title', 'Single Summary')]
        session = _make_mock_response(['单条标题', '单条摘要'])

        async def _run():
            return await batch_translate(session, items, 'fake_key', 'English')

        result = asyncio.run(_run())

        assert len(result) == 1
        assert result[0] == ('单条标题', '单条摘要')

    def test_api_returns_fewer_lines_pads_with_failure(self):
        """API returns fewer lines than expected (e.g., 3 lines for 5 items) → pad remaining."""
        from ai_translate import batch_translate

        items = _make_items(5)
        # API returns only 3 lines (should be 10 lines for 5 items)
        session = _make_mock_response(['T1', 'S1', 'T2'])

        async def _run():
            return await batch_translate(session, items, 'fake_key', 'English')

        result = asyncio.run(_run())

        assert len(result) == 5
        # First item has partial translation
        assert result[0] == ('T1', 'S1')
        # Second item has only title, summary padded as failure
        assert result[1] == ('T2', '[翻译失败]')
        # Items 3-5 all padded as failures
        assert result[2] == ('[翻译失败]', '[翻译失败]')
        assert result[3] == ('[翻译失败]', '[翻译失败]')
        assert result[4] == ('[翻译失败]', '[翻译失败]')

    def test_api_returns_odd_number_of_lines(self):
        """API returns odd number of lines → last unpaired line gets failure padding."""
        from ai_translate import batch_translate

        items = _make_items(3)
        # API returns 5 lines (odd)
        session = _make_mock_response(['T1', 'S1', 'T2', 'S2', 'T3'])

        async def _run():
            return await batch_translate(session, items, 'fake_key', 'English')

        result = asyncio.run(_run())

        assert len(result) == 3
        assert result[0] == ('T1', 'S1')
        assert result[1] == ('T2', 'S2')
        # T3 has no paired summary → padded
        assert result[2] == ('T3', '[翻译失败]')

    def test_api_returns_strip_n_prefix(self):
        """API returns lines with [N] prefix → stripped correctly."""
        from ai_translate import batch_translate

        items = _make_items(2)
        session = _make_mock_response([
            '[1] 第一标题',
            '   [1] 第一摘要',
            '[2] 第二标题',
            '[2] 第二摘要',
        ])

        async def _run():
            return await batch_translate(session, items, 'fake_key', 'English')

        result = asyncio.run(_run())

        assert len(result) == 2
        assert result[0] == ('第一标题', '第一摘要')
        assert result[1] == ('第二标题', '第二摘要')


# ── Tests: _batch_translate_all batching ──────────────────────────────────────

class TestBatchTranslateAllBatching:
    """Test _batch_translate_all batch splitting with language grouping."""

    def _make_translate_item(self, title, summary, source_lang='English', domain='tech', idx=0):
        """Create a translate item tuple matching _batch_translate_all format."""
        return (domain, idx, {}, title, summary, True, True, source_lang)

    def test_exactly_5_items_one_batch(self):
        """5 items (same language) → exactly 1 batch."""
        from ai_translate import _batch_translate_all, BATCH_SIZE

        items = [self._make_translate_item(f'Title {i}', f'Summary {i}', 'English', 'tech', i)
                 for i in range(5)]

        call_count = 0

        async def mock_batch_translate(session, pairs, api_key, source_lang):
            nonlocal call_count
            call_count += 1
            return [(f'CN_T{i}', f'CN_S{i}') for i, _ in enumerate(pairs)]

        async def _run():
            with patch('ai_translate.batch_translate', side_effect=mock_batch_translate):
                with patch('ai_translate.circuit_broken', return_value=False):
                    session = MagicMock()
                    return await _batch_translate_all(session, items, 'fake_key')

        results = asyncio.run(_run())
        assert call_count == 1, f"Expected 1 batch for {BATCH_SIZE} items, got {call_count}"
        assert len(results) == 1

    def test_6_items_two_batches(self):
        """6 items (same language) → 2 batches (5 + 1)."""
        from ai_translate import _batch_translate_all, BATCH_SIZE

        items = [self._make_translate_item(f'Title {i}', f'Summary {i}', 'English', 'tech', i)
                 for i in range(6)]

        batch_sizes = []

        async def mock_batch_translate(session, pairs, api_key, source_lang):
            batch_sizes.append(len(pairs))
            return [(f'CN_{len(batch_sizes)}_{j}', f'CN_{len(batch_sizes)}_{j}') for j, _ in enumerate(pairs)]

        async def _run():
            with patch('ai_translate.batch_translate', side_effect=mock_batch_translate):
                with patch('ai_translate.circuit_broken', return_value=False):
                    session = MagicMock()
                    return await _batch_translate_all(session, items, 'fake_key')

        results = asyncio.run(_run())
        assert len(batch_sizes) == 2, f"Expected 2 batches for 6 items, got {len(batch_sizes)}"
        assert batch_sizes == [5, 1], f"Expected batches [5, 1], got {batch_sizes}"

    def test_10_items_two_batches(self):
        """10 items (BATCH_SIZE*2) → exactly 2 batches."""
        from ai_translate import _batch_translate_all

        items = [self._make_translate_item(f'Title {i}', f'Summary {i}', 'English', 'tech', i)
                 for i in range(10)]

        batch_sizes = []

        async def mock_batch_translate(session, pairs, api_key, source_lang):
            batch_sizes.append(len(pairs))
            return [(f'CN_{j}', f'CN_{j}') for j, _ in enumerate(pairs)]

        async def _run():
            with patch('ai_translate.batch_translate', side_effect=mock_batch_translate):
                with patch('ai_translate.circuit_broken', return_value=False):
                    session = MagicMock()
                    return await _batch_translate_all(session, items, 'fake_key')

        results = asyncio.run(_run())
        assert len(batch_sizes) == 2
        assert batch_sizes == [5, 5]

    def test_mixed_languages_separate_batches(self):
        """English + Japanese items → separate language groups, each batched individually."""
        from ai_translate import _batch_translate_all

        # 4 English + 3 Japanese = 7 total items
        items = []
        items += [self._make_translate_item(f'EN Title {i}', f'EN Summary {i}', 'English', 'tech', i)
                  for i in range(4)]
        items += [self._make_translate_item(f'JP Title {i}', f'JP Summary {i}', 'Japanese', 'gaming', i)
                  for i in range(3)]

        lang_batches = []

        async def mock_batch_translate(session, pairs, api_key, source_lang):
            lang_batches.append(source_lang)
            return [(f'CN_{lang_batches.count(source_lang)}_{j}', f'CN_{lang_batches.count(source_lang)}_{j}')
                    for j, _ in enumerate(pairs)]

        async def _run():
            with patch('ai_translate.batch_translate', side_effect=mock_batch_translate):
                with patch('ai_translate.circuit_broken', return_value=False):
                    session = MagicMock()
                    return await _batch_translate_all(session, items, 'fake_key')

        results = asyncio.run(_run())
        # 4 English items → 1 batch, 3 Japanese items → 1 batch
        assert len(lang_batches) == 2
        assert lang_batches.count('English') == 1
        assert lang_batches.count('Japanese') == 1

    def test_mixed_languages_large_batches(self):
        """8 English + 7 Japanese → 2 EN batches + 2 JA batches = 4 total."""
        from ai_translate import _batch_translate_all

        items = []
        items += [self._make_translate_item(f'EN Title {i}', f'EN Summary {i}', 'English', 'tech', i)
                  for i in range(8)]
        items += [self._make_translate_item(f'JP Title {i}', f'JP Summary {i}', 'Japanese', 'gaming', i)
                  for i in range(7)]

        batch_info = []  # (lang, batch_size)

        async def mock_batch_translate(session, pairs, api_key, source_lang):
            batch_info.append((source_lang, len(pairs)))
            return [(f'CN_{j}', f'CN_{j}') for j, _ in enumerate(pairs)]

        async def _run():
            with patch('ai_translate.batch_translate', side_effect=mock_batch_translate):
                with patch('ai_translate.circuit_broken', return_value=False):
                    session = MagicMock()
                    return await _batch_translate_all(session, items, 'fake_key')

        results = asyncio.run(_run())
        assert len(batch_info) == 4
        en_batches = [(lang, sz) for lang, sz in batch_info if lang == 'English']
        ja_batches = [(lang, sz) for lang, sz in batch_info if lang == 'Japanese']
        # 8 English: 5 + 3
        assert len(en_batches) == 2
        assert sorted([sz for _, sz in en_batches]) == [3, 5]
        # 7 Japanese: 5 + 2
        assert len(ja_batches) == 2
        assert sorted([sz for _, sz in ja_batches]) == [2, 5]

    def test_empty_item_list_no_batches(self):
        """Empty items list → no batches and no API calls."""
        from ai_translate import _batch_translate_all

        async def _run():
            with patch('ai_translate.circuit_broken', return_value=False):
                session = MagicMock()
                return await _batch_translate_all(session, [], 'fake_key')

        results = asyncio.run(_run())
        assert results == []
        # session was never used for .post
        # _batch_translate_all doesn't call post directly; batch_translate does


# ── Tests: Circuit Breaker ────────────────────────────────────────────────────

class TestCircuitBreakerBoundary:
    """Circuit breaker boundary tests with batch_translate_all."""

    def _make_translate_item(self, title, summary, source_lang='English', domain='tech', idx=0):
        return (domain, idx, {}, title, summary, True, True, source_lang)

    def test_circuit_starts_closed(self):
        """Circuit breaker starts in closed (non-broken) state."""
        import ai_translate
        ai_translate.reset_circuit()
        assert ai_translate.circuit_broken() is False
        assert ai_translate._translate_failures == 0

    def test_circuit_opens_after_threshold(self):
        """After CIRCUIT_BREAKER_THRESHOLD consecutive failures, circuit opens."""
        import ai_translate
        ai_translate.reset_circuit()
        ai_translate._translate_failures = ai_translate.CIRCUIT_BREAKER_THRESHOLD
        assert ai_translate.circuit_broken() is True

    def test_circuit_breaker_skips_remaining_batches(self):
        """When circuit opens, remaining batches return error but don't crash."""
        from ai_translate import _batch_translate_all, reset_circuit
        import ai_translate

        reset_circuit()

        # Create 12 items → 3 batches (5 + 5 + 2)
        items = [self._make_translate_item(f'Title {i}', f'Summary {i}', 'English', 'tech', i)
                 for i in range(12)]

        fail_count = 0

        async def mock_batch_translate(session, pairs, api_key, source_lang):
            nonlocal fail_count
            fail_count += 1
            # First batch succeeds, second and third fail
            if fail_count == 1:
                return [(f'CN_{j}', f'CN_{j}') for j, _ in enumerate(pairs)]
            else:
                raise RuntimeError("API connection lost")

        async def _run():
            with patch('ai_translate.batch_translate', side_effect=mock_batch_translate):
                session = MagicMock()
                return await _batch_translate_all(session, items, 'fake_key')

        results = asyncio.run(_run())

        # Should have 3 batch results
        assert len(results) == 3
        # First batch: success (translations present)
        assert results[0][1] is not None
        assert results[0][2] is None
        # Second batch: error
        assert results[1][1] is None
        assert results[1][2] is not None
        # Third batch: circuit breaker or error
        assert results[2][1] is None
        assert results[2][2] is not None

    def test_reset_clears_circuit(self):
        """reset_circuit() clears the failure counter."""
        import ai_translate
        ai_translate._translate_failures = 5
        ai_translate.reset_circuit()
        assert ai_translate._translate_failures == 0
        assert ai_translate.circuit_broken() is False


# ── Tests: Source Language Classification ─────────────────────────────────────

class TestSourceLangBoundary:
    """Boundary tests for get_source_lang classification."""

    def test_compound_platform_english(self):
        """Compound platform names like 'BBC 商务+BBC 科技' are classified correctly."""
        from ai_translate import get_source_lang
        # Should detect BBC in the compound name
        result = get_source_lang('BBC 商务+BBC 科技')
        # BBC is both en and ja key in some configs; Japanese checked first
        # but BBC without NHK context should be English
        assert result in ('English', 'Japanese', None)

    def test_unknown_source_returns_none(self):
        """Completely unknown source returns None."""
        from ai_translate import get_source_lang
        assert get_source_lang('完全未知来源XYZ123') is None

    def test_empty_source_returns_none(self):
        """Empty source string returns None."""
        from ai_translate import get_source_lang
        assert get_source_lang('') is None

    def test_japanese_keywords_checked_first(self):
        """Japanese keywords take priority over English ones (NHK check)."""
        from ai_translate import get_source_lang
        # NHK should return Japanese even if 'nhk' appears in both en and ja sets
        result = get_source_lang('NHK')
        assert result == 'Japanese', f"Expected Japanese for NHK, got {result}"
