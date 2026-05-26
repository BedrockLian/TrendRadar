"""sanity_check 拦截器测试。

覆盖：
  - check_banned_phrases(): 禁语扫描
  - check_html_residue(): HTML 残留检测
  - apply_sensitive_filter(): 敏感词脱敏
  - check_dead_links(): 死链检测（mock）
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent / 'scripts')
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


class TestCheckBannedPhrases:
    """check_banned_phrases() — 禁语扫描"""

    def test_detects_ai_language_model(self):
        from sanity_check import check_banned_phrases
        text = "As an AI language model, I cannot..."
        hits = check_banned_phrases(text)
        assert len(hits) > 0
        assert any('AI language model' in h for h in hits)

    def test_detects_here_is_report(self):
        from sanity_check import check_banned_phrases
        text = "Here is your report for today"
        hits = check_banned_phrases(text)
        assert len(hits) > 0

    def test_detects_certainly(self):
        from sanity_check import check_banned_phrases
        text = "Certainly! Let me generate..."
        hits = check_banned_phrases(text)
        assert len(hits) > 0

    def test_clean_text_no_hits(self):
        from sanity_check import check_banned_phrases
        text = "中国发布新一代AI芯片突破性进展"
        hits = check_banned_phrases(text)
        assert len(hits) == 0

    def test_case_insensitive(self):
        from sanity_check import check_banned_phrases
        text = "AS AN AI LANGUAGE MODEL"
        hits = check_banned_phrases(text)
        assert len(hits) > 0


class TestCheckHtmlResidue:
    """check_html_residue() — HTML 残留检测"""

    def test_detects_br_tag(self):
        from sanity_check import check_html_residue
        text = "第一行<br>第二行"
        hits = check_html_residue(text)
        assert len(hits) > 0
        assert any('<br>' in h for h in hits)

    def test_detects_div_tag(self):
        from sanity_check import check_html_residue
        text = "<div>内容</div>"
        hits = check_html_residue(text)
        assert len(hits) >= 2

    def test_detects_code_block(self):
        from sanity_check import check_html_residue
        text = "```python\nprint('hello')\n```"
        hits = check_html_residue(text)
        assert len(hits) > 0
        assert any('代码块' in h for h in hits)

    def test_clean_markdown_no_hits(self):
        from sanity_check import check_html_residue
        text = "### 标题\n\n**加粗** [链接](https://example.com)"
        hits = check_html_residue(text)
        assert len(hits) == 0


class TestApplySensitiveFilter:
    """apply_sensitive_filter() — 敏感词脱敏"""

    def test_foreign_china_taiwan_filter(self):
        from sanity_check import apply_sensitive_filter
        text = "台湾宣布新政策"
        filtered, changes = apply_sensitive_filter(text, 'foreign_china')
        assert '台湾' in filtered or '台湾地区' in filtered
        if changes:
            assert len(changes) > 0

    def test_other_domain_no_filter(self):
        from sanity_check import apply_sensitive_filter
        text = "台湾宣布新政策"
        filtered, changes = apply_sensitive_filter(text, 'tech')
        assert filtered == text
        assert len(changes) == 0

    def test_no_sensitive_words_no_change(self):
        from sanity_check import apply_sensitive_filter
        text = "科技创新推动经济发展"
        filtered, changes = apply_sensitive_filter(text, 'foreign_china')
        assert filtered == text
        assert len(changes) == 0


class TestCheckDeadLinks:
    """check_dead_links() — 死链检测（mock）"""

    def test_no_urls_returns_empty(self):
        from sanity_check import check_dead_links
        text = "没有链接的文本"
        dead = check_dead_links(text)
        assert dead == []

    def test_extract_urls_from_markdown(self):
        from sanity_check import _extract_urls
        text = "[链接1](https://example.com) [链接2](https://bbc.com)"
        urls = _extract_urls(text, limit=5)
        assert len(urls) == 2
        assert 'https://example.com' in urls
        assert 'https://bbc.com' in urls

    def test_limit_urls_count(self):
        from sanity_check import _extract_urls
        text = "[1](https://a.com) [2](https://b.com) [3](https://c.com) [4](https://d.com)"
        urls = _extract_urls(text, limit=2)
        assert len(urls) == 2

    @patch('sanity_check.urllib.request.urlopen')
    def test_404_detected_as_dead(self, mock_urlopen):
        from sanity_check import check_dead_links
        import urllib.error
        mock_urlopen.side_effect = urllib.error.HTTPError(
            'https://example.com', 404, 'Not Found', {}, None
        )
        text = "[链接](https://example.com)"
        dead = check_dead_links(text, timeout=1)
        assert len(dead) > 0
        assert '404' in dead[0]

    @patch('sanity_check.urllib.request.urlopen')
    def test_200_not_dead(self, mock_urlopen):
        from sanity_check import check_dead_links
        mock_urlopen.return_value = MagicMock()
        text = "[链接](https://example.com)"
        dead = check_dead_links(text, timeout=1)
        assert len(dead) == 0
