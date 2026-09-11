"""rag/fusion.py 纯函数测试：内容去重键与按 token 截断。"""

from core.settings import settings
from rag.evidence import TextEvidence
from rag.fusion import _content_key, _truncate_profile, _truncate_to_tokens
from rag.rag_utils import estimate_tokens


def _ev(content: str, collection: str = "os", source: str = "s.md", **metadata) -> TextEvidence:
    return TextEvidence(
        evidence_id="e1",
        content=content,
        collection=collection,
        source=source,
        metadata=metadata,
    )


class TestContentKey:
    def test_prefers_content_hash(self):
        assert _content_key(_ev("内容", collection="os", content_hash="abc")) == "os:abc"

    def test_falls_back_to_source_and_prefix(self):
        assert _content_key(_ev("内容片段", collection="ds", source="a.md")) == "ds:a.md:内容片段"

    def test_blank_hash_falls_back(self):
        assert _content_key(_ev("内容", collection="ds", content_hash="   ")).startswith("ds:")

    def test_stable_for_same_hash(self):
        a = _content_key(_ev("内容A", collection="os", content_hash="h"))
        b = _content_key(_ev("内容B", collection="os", content_hash="h"))
        assert a == b


class TestTruncateToTokens:
    def test_short_text_untouched(self):
        assert _truncate_to_tokens("短文本", 100) == "短文本"

    def test_non_positive_budget_returns_empty(self):
        text = "一段很长的中文内容" * 50
        assert _truncate_to_tokens(text, 0) == ""
        assert _truncate_to_tokens(text, -1) == ""

    def test_long_text_truncated_with_marker(self):
        out = _truncate_to_tokens("中" * 2000, 100)
        assert out.endswith("\n[...truncated]")
        assert len(out) < 2000

    def test_truncated_result_respects_budget(self):
        out = _truncate_to_tokens("中" * 2000, 100)
        # 截断标记本身有少量 token 开销，留出余量
        assert estimate_tokens(out) <= 200


class TestTruncateProfile:
    """覆盖 settings.MAX_STUDENT_PROFILE_TOKENS 缺失导致的休眠 AttributeError。"""

    def test_empty_returns_empty(self):
        assert _truncate_profile("") == ""

    def test_under_budget_untouched(self):
        profile = "该生数据结构基础较弱，需加强练习。"
        assert _truncate_profile(profile) == profile

    def test_over_budget_is_truncated(self):
        profile = "该生数据结构与算法基础较弱，需要加强练习。" * 200
        out = _truncate_profile(profile)

        assert out.endswith("\n[...truncated]")
        assert len(out) < len(profile)
        assert estimate_tokens(out) <= settings.MAX_STUDENT_PROFILE_TOKENS + 50
