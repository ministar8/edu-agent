"""检索工具工厂：docstring 契约与 stem 约定。"""

from agents.tools import (
    aknowledge_search,
    asearch_question_templates,
    asearch_standard_answer,
    atext_search,
)


def test_search_tool_docstrings_mention_payload_contract():
    for t in (aknowledge_search, atext_search, asearch_standard_answer, asearch_question_templates):
        doc = t.description or ""
        assert "context" in doc, t.name
        assert "status=empty" in doc or "empty" in doc, t.name
        assert "不得编造" in doc, t.name


def test_search_tool_names():
    assert aknowledge_search.name == "knowledge_search"
    assert atext_search.name == "text_search"
    assert asearch_standard_answer.name == "search_standard_answer"
    assert asearch_question_templates.name == "search_question_templates"


def test_search_tool_args_schema():
    assert "query" in aknowledge_search.args


def test_grade_tool_stem_constraint_documented():
    from agents.tools import agrade_student_answer

    assert "题干" in (agrade_student_answer.description or "")
