"""render_markdown 格式契约测试。

覆盖：
  - _format_item(): title_cn fallback、摘要截断、链接格式
  - _generate_section(): 板块标题、空行规则
  - _detect_emoji(): 热度/追踪 emoji 检测
  - _shorten(): 文本截断（句号边界）
"""

import pytest
import sys
from pathlib import Path

SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / 'scripts')
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


class TestFormatItem:
    """_format_item() — 单条目格式化"""

    def test_title_cn_priority(self):
        from render_markdown import _format_item
        item = {
            'title': 'English Title',
            'title_cn': '中文标题',
            'summary': 'English summary',
            'summary_cn': '中文摘要',
            'url': 'https://example.com',
            'source_platform': 'BBC',
        }
        result = _format_item(1, item, 'morning')
        assert '中文标题' in result
        assert '中文摘要' in result
        assert 'English Title' not in result

    def test_title_fallback_when_cn_empty(self):
        from render_markdown import _format_item
        item = {
            'title': 'English Title',
            'title_cn': '',
            'summary': 'English summary',
            'summary_cn': '',
            'url': 'https://example.com',
            'source_platform': 'Reuters',
        }
        result = _format_item(1, item, 'morning')
        assert 'English Title' in result
        assert 'English summary' in result

    @pytest.mark.smoke
    def test_link_format(self):
        from render_markdown import _format_item
        item = {
            'title': 'Test',
            'summary': 'Test summary',
            'url': 'https://bbc.com/news',
            'source_platform': 'BBC',
        }
        result = _format_item(1, item, 'morning')
        assert '[【BBC】](https://bbc.com/news)' in result

    def test_no_summary_line_when_empty(self):
        from render_markdown import _format_item
        item = {
            'title': 'Test Title',
            'summary': '',
            'url': 'https://example.com',
            'source_platform': 'Test',
        }
        result = _format_item(1, item, 'morning')
        lines = result.split('\n\n')
        assert len(lines) == 2

    def test_emoji_new_by_default(self):
        from render_markdown import _format_item
        item = {
            'title': 'Test',
            'summary': 'Test',
            'url': '',
            'source_platform': 'Test',
        }
        result = _format_item(1, item, 'morning')
        assert '🆕' in result


class TestGenerateSection:
    """_generate_section() — 板块生成"""

    def test_empty_items_shows_placeholder(self):
        from render_markdown import _generate_section
        result = _generate_section('tech', [], 'morning')
        assert '暂无内容' in result
        # Current label is '💻 科学/技术' (per config/domains.py)
        assert '💻' in result
        assert '科学' in result

    def test_items_separated_by_double_blank_lines(self):
        from render_markdown import _generate_section
        items = [
            {'title': 'Item 1', 'summary': 'Summary 1', 'url': '', 'source_platform': 'A'},
            {'title': 'Item 2', 'summary': 'Summary 2', 'url': '', 'source_platform': 'B'},
        ]
        result = _generate_section('tech', items, 'morning')
        assert '\n\n\n' in result
        assert 'Item 1' in result
        assert 'Item 2' in result


class TestDetectEmoji:
    """_detect_emoji() — emoji 检测"""

    def test_heat_dict_with_appearances(self):
        from render_markdown import _detect_emoji
        heat = {'appearances': 3, 'heat_score': 0.5}
        assert _detect_emoji(heat, 'morning') == '🔥'

    def test_heat_dict_high_score(self):
        from render_markdown import _detect_emoji
        heat = {'appearances': 1, 'heat_score': 0.9}
        assert _detect_emoji(heat, 'morning') == '🔥'

    def test_heat_int_high(self):
        from render_markdown import _detect_emoji
        assert _detect_emoji(3, 'morning') == '🔥'

    def test_no_heat_returns_new(self):
        from render_markdown import _detect_emoji
        assert _detect_emoji(None, 'morning') == '🆕'
        assert _detect_emoji(0, 'morning') == '🆕'

    def test_evening_recap_returns_loop(self):
        from render_markdown import _detect_emoji
        assert _detect_emoji(None, 'evening', 'hot_recap') == '🔄'


class TestShorten:
    """_shorten() — 文本截断"""

    def test_short_text_unchanged(self):
        from render_markdown import _shorten
        text = '短文本'
        assert _shorten(text, 100) == '短文本'

    def test_long_text_truncated_at_sentence(self):
        from render_markdown import _shorten
        text = '第一句话。第二句话。第三句话。' * 10
        result = _shorten(text, 50)
        assert len(result) <= 55
        assert result.endswith('。') or result.endswith('…')

    def test_preserves_sentence_boundary(self):
        from render_markdown import _shorten
        text = '这是第一句完整的句子。这是第二句完整的句子。这是第三句。'
        result = _shorten(text, 30)
        assert '。' in result
