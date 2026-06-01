"""ai_translate 烟雾测试。

覆盖 pure functions (no API/network):
  - get_source_lang(): 来源平台语言检测
  - _load_source_languages(): sources.json 加载
  - batch_translate(): mock API 翻译
  - 熔断器状态机
"""

import pytest
import os
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / 'scripts')
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


class TestGetSourceLang:
    """get_source_lang() — 来源平台语言检测"""

    @pytest.mark.smoke
    def test_english_bbc(self):
        from ai_translate import get_source_lang
        assert get_source_lang('BBC 商务') == 'English'
        assert get_source_lang('bbc 科技') == 'English'

    def test_english_reuters(self):
        from ai_translate import get_source_lang
        assert get_source_lang('Reuters') == 'English'
        assert get_source_lang('路透社·商业') == 'English'

    def test_japanese_nhk(self):
        from ai_translate import get_source_lang
        assert get_source_lang('NHK') == 'Japanese'
        assert get_source_lang('nhk ビジネス') == 'Japanese'

    def test_japanese_4gamer(self):
        from ai_translate import get_source_lang
        assert get_source_lang('4Gamer') == 'Japanese'

    def test_chinese_source_returns_none(self):
        from ai_translate import get_source_lang
        assert get_source_lang('新华社') is None
        assert get_source_lang('澎湃新闻') is None
        assert get_source_lang('36氪') is None

    def test_case_insensitive(self):
        from ai_translate import get_source_lang
        assert get_source_lang('bbc') == 'English'
        assert get_source_lang('BBC') == 'English'
        assert get_source_lang('Bbc') == 'English'

    def test_partial_match(self):
        from ai_translate import get_source_lang
        assert get_source_lang('BBC 科技频道') == 'English'
        assert get_source_lang('NHK World') == 'Japanese'


class TestLoadSourceLanguages:
    """_load_source_languages() — sources.json 加载"""

    def test_returns_frozensets(self):
        from ai_translate import _load_source_languages
        en, ja = _load_source_languages()
        assert isinstance(en, frozenset)
        assert isinstance(ja, frozenset)

    def test_english_sources_loaded(self):
        from ai_translate import _load_source_languages
        en, ja = _load_source_languages()
        if en:
            assert any('bbc' in kw.lower() or 'reuters' in kw.lower() for kw in en)

    def test_japanese_sources_loaded(self):
        from ai_translate import _load_source_languages
        en, ja = _load_source_languages()
        if ja:
            assert any('nhk' in kw.lower() or '4gamer' in kw.lower() for kw in ja)

    def test_missing_sources_json_returns_empty(self):
        from ai_translate import _load_source_languages
        with patch('ai_translate._SOURCES_PATH', Path('/nonexistent/sources.json')):
            en, ja = _load_source_languages()
            assert en == frozenset()
            assert ja == frozenset()


class TestCircuitBreaker:
    """熔断器状态机"""

    def test_initial_state_not_broken(self):
        from ai_translate import circuit_broken, reset_circuit
        reset_circuit()
        assert circuit_broken() is False

    def test_broken_after_threshold(self):
        from ai_translate import circuit_broken, reset_circuit, CIRCUIT_BREAKER_THRESHOLD
        import ai_translate
        reset_circuit()
        ai_translate._translate_failures = CIRCUIT_BREAKER_THRESHOLD
        assert circuit_broken() is True

    def test_reset_clears_failures(self):
        from ai_translate import circuit_broken, reset_circuit
        import ai_translate
        ai_translate._translate_failures = 10
        reset_circuit()
        assert circuit_broken() is False


class TestBatchTranslate:
    """batch_translate() — mock API 翻译"""

    def test_empty_items_returns_empty(self):
        import asyncio
        
        async def _run():
            from ai_translate import batch_translate
            session = MagicMock()
            result = await batch_translate(session, [], 'fake_key', 'English')
            assert result == []

        
        asyncio.run(_run())
    def test_successful_translation(self):
        import asyncio
        
        async def _run():
            from ai_translate import batch_translate
            session = MagicMock()

            mock_response = AsyncMock()
            mock_response.json = AsyncMock(return_value={
            'choices': [{
            'message': {
            'content': '中文标题\n中文摘要'
            }
            }]
            })
            session.post = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response)))

            items = [('Test Title', 'Test Summary')]
            result = await batch_translate(session, items, 'fake_key', 'English')

            assert len(result) == 1
            assert result[0][0] == '中文标题'
            assert result[0][1] == '中文摘要'

        
        asyncio.run(_run())
    def test_malformed_api_response_pads_with_failure(self):
        import asyncio
        
        async def _run():
            from ai_translate import batch_translate
            session = MagicMock()

            mock_response = AsyncMock()
            mock_response.json = AsyncMock(return_value={
            'choices': [{
            'message': {
            'content': '只有标题'
            }
            }]
            })
            session.post = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_response)))

            items = [('Title 1', 'Summary 1'), ('Title 2', 'Summary 2')]
            result = await batch_translate(session, items, 'fake_key', 'English')

            assert len(result) == 2
            assert result[1] == ('[翻译失败]', '[翻译失败]')


        
        asyncio.run(_run())
class TestTranslateConfigConsistency:
    """C8: sources.json 语言字段完整性"""

    def test_all_sources_have_language(self):
        """所有 source 条目必须有 language 字段"""
        TR = Path(os.environ.get('TRENDRADAR_HOME', Path.home() / '.hermes' / 'trendradar'))
        spath = TR / 'data' / 'sources.json'
        if not spath.exists():
            pytest.skip('sources.json not available in test environment')
        sources_data = json.loads(spath.read_text())
        def _check(obj):
            if isinstance(obj, dict) and 'name' in obj and 'feed_url' in obj:
                assert 'language' in obj, f'source has no language field'
                assert obj['language'] in ('zh', 'en', 'ja'), f'source has invalid language: {obj["language"]}'
                return
            if isinstance(obj, dict):
                for v in obj.values():
                    _check(v)
            elif isinstance(obj, list):
                for item in obj:
                    _check(item)
        _check(sources_data)
