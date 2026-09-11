"""rag/rag_utils.py 纯函数测试（不依赖 TEI / Chroma）。"""

from rag.rag_utils import (
    detect_content_type,
    estimate_tokens,
    extract_query_terms,
    normalize_query_text,
)


class TestEstimateTokens:
    def test_empty_is_zero(self):
        assert estimate_tokens("") == 0

    def test_chinese_is_heavier_than_ascii(self):
        # 中文 1 字符 ≈ 1.5 token，ASCII 1 字符 ≈ 0.25 token
        assert estimate_tokens("中文") == 3
        assert estimate_tokens("中文") > estimate_tokens("abcd")

    def test_ascii(self):
        assert estimate_tokens("abcd") == 1


class TestNormalizeQueryText:
    def test_collapses_whitespace(self):
        assert normalize_query_text("  进程   调度\n\n算法  ") == "进程 调度 算法"

    def test_coerces_non_string(self):
        assert normalize_query_text(123) == "123"

    def test_blank(self):
        assert normalize_query_text("   ") == ""


class TestExtractQueryTerms:
    def test_blank_returns_empty(self):
        assert extract_query_terms("") == []
        assert extract_query_terms("   ") == []

    def test_respects_max_terms(self):
        assert len(extract_query_terms("进程调度算法与死锁避免策略", max_terms=2)) <= 2

    def test_no_case_insensitive_duplicates(self):
        terms = extract_query_terms("tcp TCP tcp")
        lowered = [t.lower() for t in terms]
        assert len(lowered) == len(set(lowered))

    def test_returns_strings(self):
        terms = extract_query_terms("操作系统的进程调度")
        assert terms
        assert all(isinstance(t, str) for t in terms)


class TestDetectContentType:
    def test_empty(self):
        assert detect_content_type("", {}) == "empty"
        assert detect_content_type("   ", {}) == "empty"

    def test_merged_qa_flag(self):
        assert detect_content_type("正文", {"chunk_role": "merged_qa"}) == "merged_qa"
        assert detect_content_type("正文", {"section.chunk_role": "merged_qa"}) == "merged_qa"

    def test_code_fence(self):
        assert detect_content_type("```python\nx = 1\n```", {}) == "code_mixed"

    def test_indented_code(self):
        assert detect_content_type("说明：\n    缩进代码块", {}) == "code_mixed"

    def test_table(self):
        text = "| 科目 | 分数 |\n| --- | --- |\n| 数学 | 150 |"
        assert detect_content_type(text, {}) == "table"

    def test_formula(self):
        assert detect_content_type("$$E = mc^2$$", {}) == "formula"

    def test_section_heading(self):
        assert detect_content_type("# 第一章\n正文", {}) == "section"

    def test_plain_text(self):
        assert detect_content_type("这是一段普通正文。", {}) == "text"
