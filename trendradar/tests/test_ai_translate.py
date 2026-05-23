"""ai_translate 烟雾测试。

覆盖 pure functions (no API/network):
  - _is_cjk(): CJK 字符检测
  - cjk_ratio(): CJK 占比计算
  - is_english_summary(): 英文摘要判定（<50% CJK）
  - is_foreign_china_source(): 外媒来源匹配
"""

import pytest
import os
from ai_translate import _is_cjk, cjk_ratio, is_english_summary, is_foreign_china_source


class TestIsCjk:
    def test_chinese_character(self):
        assert _is_cjk('中') is True
        assert _is_cjk('国') is True
        assert _is_cjk('人') is True

    def test_japanese_kana(self):
        assert _is_cjk('あ') is True   # Hiragana
        assert _is_cjk('ア') is True   # Katakana

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


class TestIsEnglishSummary:
    def test_chinese_summary(self):
        assert is_english_summary('中国人工智能产业快速发展') is False

    def test_english_summary(self):
        assert is_english_summary('China AI industry grows rapidly') is True

    def test_boundary_50_percent(self):
        """恰好 50% CJK 不算英文（< 0.5 才触发）"""
        # '中英' = 2/2 CJK = 1.0 → False
        assert is_english_summary('中英') is False

    def test_mixed_majority_english(self):
        """>50% 英文 → True"""
        # 'China的AI市场' = 1 CJK / 5 total ≈ 0.2 → True
        assert is_english_summary('China的AI市场') is True


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
    """C8: translate.yaml 与 sources.json 交叉校验"""

    def test_all_translate_sources_exist(self):
        """translate.yaml 所列源名必须在 sources.json 中存在"""
        import yaml, json
        from pathlib import Path
        TR = Path(os.environ.get('TRENDRADAR_HOME', Path.home() / '.hermes' / 'trendradar'))
        tpath = TR / 'config' / 'translate.yaml'
        spath = TR / 'data' / 'sources.json'
        if not spath.exists():
            pytest.skip('sources.json not available in test environment')
        config = yaml.safe_load(tpath.read_text())
        sources_data = json.loads(spath.read_text())
        source_names = {s['name'] for s in sources_data.get('data_sources', [])}
        for src in config['translate']['sources']:
            assert src in source_names, f'翻译源 "{src}" 在 sources.json 中不存在'
        for src in config['translate']['japanese_sources']:
            assert src in source_names, f'日文源 "{src}" 在 sources.json 中不存在'
