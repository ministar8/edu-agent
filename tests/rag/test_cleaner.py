"""rag/cleaner.py 纯文本清洗函数测试（不依赖 TEI / Chroma）。"""

from rag.cleaner import _clean_markdown_text, _normalize_text, clean_text


class TestCleanText:
    def test_blank_returns_empty(self):
        assert clean_text("") == ""
        assert clean_text("   \n  ") == ""

    def test_removes_control_chars(self):
        assert clean_text("进\x00程") == "进程"

    def test_fullwidth_normalized_to_halfwidth(self):
        assert clean_text("ａｂｃ１２３") == "abc123"

    def test_collapses_excess_blank_lines(self):
        out = clean_text("第一段\n\n\n\n\n第二段")
        assert "第一段" in out
        assert "第二段" in out
        assert "\n\n\n" not in out

    def test_strips_surrounding_whitespace(self):
        assert clean_text("  正文  ") == "正文"


class TestNormalizeText:
    def test_blank_returns_empty(self):
        assert _normalize_text("") == ""
        assert _normalize_text("  \n ") == ""

    def test_nfkc_normalization(self):
        assert _normalize_text("ＡＢ") == "AB"

    def test_does_not_trim_content(self):
        assert _normalize_text("  a  ") == "  a  "

    def test_removes_control_chars(self):
        assert _normalize_text("a\x01b") == "ab"


class TestCleanMarkdownText:
    def test_blank_returns_empty(self):
        assert _clean_markdown_text("") == ""

    def test_caps_blank_runs_at_two(self):
        # _collapse_blank_lines 保留最多 2 个空行（即 "a\n\n\nb"），多余被丢弃
        assert _clean_markdown_text("a\n\n\n\n\nb") == "a\n\n\nb"
        assert _clean_markdown_text("a" + "\n" * 20 + "b") == "a\n\n\nb"

    def test_preserves_code_fence_body(self):
        out = _clean_markdown_text("```python\nprint(1)\n```")
        assert "print(1)" in out
        assert "```" in out

    def test_normalizes_fullwidth(self):
        assert "AB" in _clean_markdown_text("ＡＢ")
