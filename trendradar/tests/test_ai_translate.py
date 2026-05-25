"""ai_translate 烟雾测试。

覆盖 pure functions (no API/network):
  - _is_cjk(): CJK 字符检测
  - cjk_ratio(): CJK 占比计算
  - needs_translation(): 是否需要翻译（英文/日文→True，纯中文→False）
  - is_foreign_china_source(): 外媒来源匹配
"""

import pytest
import os
from ai_translate import _is_cjk, cjk_ratio, needs_translation, is_foreign_china_source


class TestIsCjk:
    def test_chinese_character(self):
        assert _is_cjk('中') is True
        assert _is_cjk('国') is True
        assert _is_cjk('人') is True

    def test_japanese_kana(self):
        assert _is_cjk('あ') is False   # Hiragana — not CJK
        assert _is_cjk('ア') is False   # Katakana — not CJK

    def test_english_ascii(self):
        assert _is_cjk('A') is False
        assert _is_cjk('z') is False
        assert _is_cjk('1') is False

    def test_punctuation(self):
        assert _is_cjk('。') is True   # CJK full-width
        assert _is_cjk('.') is False   # ASCII
        assert _is_cjk('，') is True   # CJK comma


class TestCjkRatio:
    def test_pure_chinese(self):
        assert cjk_ratio('你好世界') == 1.0

    def test_pure_english(self):
        assert cjk_ratio('Hello World') == 0.0

    def test_mixed_content(self):
        """混合内容：2 中文 (你好) + 6 English (ABCXYZ) = 2/8 = 0.25"""
        r = cjk_ratio('ABC你好XYZ')
        assert 0.2 < r < 0.3

    def test_empty_string(self):
        assert cjk_ratio('') == 0.0

    def test_whitespace_only(self):
        assert cjk_ratio('   \n\t  ') == 0.0

    def test_chinese_with_spaces(self):
        """空格不计入分母"""
        assert cjk_ratio('你好 世界') == 1.0


class TestNeedsTranslation:
    def test_chinese_summary(self):
        assert needs_translation('中国人工智能产业快速发展') is False

    def test_english_summary(self):
        assert needs_translation('China AI industry grows rapidly') is True

    def test_boundary_50_percent(self):
        # '中英' = 2/2 CJK = 1.0 -> False
        assert needs_translation('中英') is False

    def test_mixed_majority_english(self):
        # 'China的AI市场' = 1 CJK / 5 total -> True
        assert needs_translation('China的AI市场') is True

    def test_japanese_with_kanji(self):
        assert needs_translation('茂木外相 イラン外相と電話会談') is True


class TestIsForeignChinaSource:
    def test_bbc(self):
        assert is_foreign_china_source('BBC News') is True
        assert is_foreign_china_source('bbc 商务') is True

    def test_reuters(self):
        assert is_foreign_china_source('Reuters') is True
        assert is_foreign_china_source('路透社') is True

    def test_nytimes(self):
        assert is_foreign_china_source('NYTimes') is True

    def test_guardian(self):
        assert is_foreign_china_source('The Guardian') is True

    def test_scmp(self):
        assert is_foreign_china_source('SCMP') is True

    def test_domestic_source(self):
        assert is_foreign_china_source('36氪') is False
        assert is_foreign_china_source('新华网') is False
        assert is_foreign_china_source('澎湃新闻') is False

    def test_case_insensitive(self):
        assert is_foreign_china_source('BBC') is True
        assert is_foreign_china_source('bbc') is True
        assert is_foreign_china_source('Bbc') is True

    def test_partial_match(self):
        """关键字出现在字符串中即可匹配"""
        assert is_foreign_china_source('BBC 科技频道') is True


class TestTranslateConfigConsistency:
    """C8: sources.json 语言字段完整性"""

    def test_all_sources_have_language(self):
        """所有 source 条目必须有 language 字段"""
        import json
        from pathlib import Path
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
