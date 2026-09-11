"""检索对外契约：FusedEvidence → RetrievalResult → 工具载荷。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from agents.tools import (
    aknowledge_search,
    build_retrieval_result,
)
from rag.evidence import FusedEvidence, TextEvidence
from schema.evidence import EvidenceDoc, RetrievalResult


def _fused() -> FusedEvidence:
    return FusedEvidence(
        text_evidences=[
            TextEvidence(
                evidence_id="ev1",
                content="虚拟内存是…",
                source="os.md",
                score=0.9,
                rerank_score=0.88,
                section_path="ch3 > 3.1",
                chunk_id="chunk-1",
                knowledge_points=["虚拟内存"],
            )
        ],
        final_context="虚拟内存是…（正文）",
        sources=["os.md"],
    )


def _verifier(verdict: str = "pass", reasons: list[str] | None = None):
    return SimpleNamespace(verdict=SimpleNamespace(value=verdict), reasons=reasons or [])


def test_build_retrieval_result_ok():
    result = build_retrieval_result(
        query="什么是虚拟内存", fused=_fused(), verification=_verifier()
    )
    assert result.status == "ok"
    assert result.sources == ["os.md"]
    assert "虚拟内存" in result.context
    assert "来源: os.md" in result.context
    assert len(result.docs) == 1
    doc = result.docs[0]
    assert doc.chunk_id == "chunk-1"
    assert doc.section_path == "ch3 > 3.1"
    assert doc.rerank_score == pytest.approx(0.88)
    assert "虚拟内存" in doc.knowledge_points


def test_build_retrieval_result_empty():
    fused = FusedEvidence(text_evidences=[], final_context="", sources=[])
    result = build_retrieval_result(query="q", fused=fused, verification=_verifier())
    assert result.status == "empty"
    assert "未找到" in result.context


def test_as_tool_payload_roundtrip():
    payload = build_retrieval_result(
        query="q", fused=_fused(), verification=_verifier("warn", ["来源单一"])
    ).as_tool_payload()
    assert payload["status"] == "ok"
    assert payload["verification"] == "warn"
    assert payload["docs"][0]["chunk_id"] == "chunk-1"
    parsed = RetrievalResult.model_validate(payload)
    assert isinstance(parsed.docs[0], EvidenceDoc)


@pytest.mark.asyncio
async def test_knowledge_search_returns_dict_payload():
    fused = _fused()
    verification = _verifier()
    with patch(
        "agents.tools.aretrieve_evidence_with_retry",
        AsyncMock(return_value=(fused, verification)),
    ) as mock_ret:
        payload = await aknowledge_search.ainvoke({"query": "虚拟内存"})
    mock_ret.assert_awaited_once()
    assert isinstance(payload, dict)
    assert payload["status"] == "ok"
    assert payload["docs"][0]["source"] == "os.md"
    assert "虚拟内存" in payload["context"]


@pytest.mark.asyncio
async def test_knowledge_search_error_status():
    with patch(
        "agents.tools.aretrieve_evidence_with_retry",
        AsyncMock(side_effect=RuntimeError("TEI down")),
    ):
        payload = await aknowledge_search.ainvoke({"query": "x"})
    assert payload["status"] == "error"
    assert "TEI down" in payload["error"]
    assert "检索失败" in payload["context"]
