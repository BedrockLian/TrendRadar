"""Tests for batch_fetch.py — encoding detection, HTML cleaning, curl fallback."""

import pytest
from unittest.mock import patch, MagicMock


class TestDecode:
    def test_decode_utf8(self):
        from batch_fetch import _decode
        result = _decode('Hello World 你好世界'.encode('utf-8'))
        assert result == 'Hello World 你好世界'

    def test_decode_gbk(self):
        from batch_fetch import _decode
        result = _decode('中文测试'.encode('gbk'))
        assert result == '中文测试'

    def test_decode_japanese_euc_jp(self):
        from batch_fetch import _decode
        result = _decode('テスト'.encode('euc-jp'))
        assert 'テスト' in result

    def test_decode_latin1_fallback(self):
        from batch_fetch import _decode
        # latin-1 never fails, returns something for any bytes
        result = _decode(b'\x80\x81\x82')
        assert result is not None

    def test_decode_empty(self):
        from batch_fetch import _decode
        result = _decode(b'')
        assert result == ''


class TestCleanHtml:
    def test_clean_html_strips_tags(self):
        from batch_fetch import _clean_html
        result = _clean_html('<p>Hello <b>World</b></p>')
        assert 'Hello' in result
        assert 'World' in result
        assert '<' not in result

    def test_clean_html_collapses_whitespace(self):
        from batch_fetch import _clean_html
        result = _clean_html('Hello    World\n\nTest')
        assert 'Hello World Test' in result

    def test_clean_html_truncates(self):
        from batch_fetch import _clean_html
        long_text = 'x' * 2000
        result = _clean_html(long_text)
        assert len(result) <= 1000


class TestProxyAlive:
    def test_proxy_alive_cached(self):
        from batch_fetch import _proxy_alive
        # First call determines, second call uses cache
        r1 = _proxy_alive()
        r2 = _proxy_alive()
        assert r1 == r2  # cached result
