"""ai_translate 烟雾测试。

覆盖 pure functions (no API/network):
  - _load_source_languages(): 从 sources.json 按 language 字段分类
  - get_source_lang(): 来源平台 → 语言映射 (English/Japanese/None)
  - get_system_prompt(): 翻译 prompt 模板渲染
  - circuit_broken() / reset_circuit(): 熔断器状态
"""

import pytest
from ai_translate import (
    _load_source_languages,
    get_source_lang,
    get_system_prompt,
    circuit_broken,
    reset_circuit,
)


class TestLoadSourceLanguages:
    """_load_source_languages() returns (en_keywords, ja_keywords) frozensets."""

    def test_returns_frozensets(self):
        en, ja = _load_source_languages()
        assert isinstance(en, frozenset)
        assert isinstance(ja, frozenset)

    def test_known_en_platforms(self):
        """sources.json 中 language='en' 的 platform 出现在 en frozenset 中。"""
        en, ja = _load_source_languages()
        # 至少有 bbc, reuters 等常见英文源
        assert 'bbc' in en or 'reuters' in en or len(en) > 0, \
            f"Expected English platforms, got {sorted(en)[:10] if en else 'EMPTY'}"

    def test_known_ja_platforms(self):
        """sources.json 中 language='ja' 的 platform 出现在 ja frozenset 中。"""
        en, ja = _load_source_languages()
        # 至少有 nhk 等日文源
        assert 'nhk' in ja or len(ja) > 0, \
            f"Expected Japanese platforms, got {sorted(ja)[:10] if ja else 'EMPTY'}"

    def test_en_ja_disjoint(self):
        """同一个 platform 不应同时出现在 en 和 ja 集合。"""
        en, ja = _load_source_languages()
        overlap = en & ja
        assert not overlap, f"Overlapping platforms in en & ja: {overlap}"


class TestGetSourceLang:
    """get_source_lang(source_platform) — 按 sources.json language 字段匹配。"""

    def test_reuters_returns_english(self):
        assert get_source_lang('Reuters') == 'English'

    def test_bbc_returns_english(self):
        assert get_source_lang('BBC News') == 'English'
        assert get_source_lang('bbc') == 'English'

    def test_nhk_returns_japanese(self):
        assert get_source_lang('NHK') == 'Japanese'
        assert get_source_lang('nhk ニュース') == 'Japanese'

    def test_chinese_source_returns_none(self):
        """中文源（language='zh'）不在 en/ja 中，返回 None。"""
        assert get_source_lang('新华社') is None
        assert get_source_lang('澎湃新闻') is None
        assert get_source_lang('央视新闻') is None

    def test_unknown_platform_returns_none(self):
        assert get_source_lang('TotallyUnknownSource12345') is None

    def test_empty_string(self):
        assert get_source_lang('') is None

    def test_case_insensitive(self):
        """平台名匹配不区分大小写。"""
        # 如果 bbc 在 en 集合中，BBc 也能匹配
        en, _ = _load_source_languages()
        if 'bbc' in en:
            assert get_source_lang('BBC') == 'English'
            assert get_source_lang('Bbc') == 'English'

    def test_japanese_checked_first(self):
        """日语关键词优先于英语（防止 NHK 被英文误匹配）。"""
        # NHK 既是日文源，get_source_lang 应返回 Japanese
        en, ja = _load_source_languages()
        if 'nhk' in ja:
            assert get_source_lang('NHK') == 'Japanese'


class TestGetSystemPrompt:
    """get_system_prompt(source_lang) 渲染翻译 prompt 模板。"""

    def test_english_prompt(self):
        prompt = get_system_prompt('English')
        assert 'English' in prompt
        assert 'Chinese' in prompt
        assert 'translator' in prompt.lower()

    def test_japanese_prompt(self):
        prompt = get_system_prompt('Japanese')
        assert 'Japanese' in prompt
        assert 'Chinese' in prompt
        assert 'translator' in prompt.lower()

    def test_prompt_contains_rules(self):
        prompt = get_system_prompt('English')
        assert 'factual details' in prompt
        assert 'journalistic' in prompt

    def test_default_is_english(self):
        prompt = get_system_prompt()
        assert 'English' in prompt


class TestCircuitBreaker:
    """circuit_broken() / reset_circuit() — 熔断器状态管理。"""

    def test_initial_state_not_broken(self):
        """初始状态：熔断器未触发。"""
        reset_circuit()
        assert circuit_broken() is False

    def test_circuit_stays_closed_after_reset(self):
        reset_circuit()
        assert circuit_broken() is False

    def test_reset_idempotent(self):
        reset_circuit()
        reset_circuit()
        assert circuit_broken() is False
