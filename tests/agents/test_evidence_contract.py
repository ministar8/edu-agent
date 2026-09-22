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


# ── 错误分级：三类失败不再被抹平成同一类（docs/ENGINEERING.md §1 P1）───────────────


@pytest.mark.asyncio
async def test_unavailable_dependency_is_warning_not_error(caplog):
    """依赖暂时不可用 → WARNING + 可重试文案，**不得**记为 ERROR。

    这是本次分级的核心断言：如果这里变成 ERROR，值班的人就无法从日志
    区分「TEI 抖了一下」和「代码有缺陷」，分级就白做了。
    """
    import logging

    from rag.errors import RetrievalUnavailable

    with caplog.at_level(logging.DEBUG, logger="agents.tools"):
        with patch(
            "agents.tools.aretrieve_evidence_with_retry",
            AsyncMock(side_effect=RetrievalUnavailable("TEI 502")),
        ):
            payload = await aknowledge_search.ainvoke({"query": "x"})

    assert payload["status"] == "error"
    assert payload["error_kind"] == "unavailable"
    assert "稍后重试" in payload["context"]
    levels = {r.levelno for r in caplog.records if r.name == "agents.tools"}
    assert logging.WARNING in levels
    assert logging.ERROR not in levels, "依赖不可用不应产生 ERROR 日志"


@pytest.mark.asyncio
async def test_network_timeout_is_classified_as_unavailable(caplog):
    """未标注类型的超时异常也要被正确归类（分类器兜底生效）。"""
    import logging

    with caplog.at_level(logging.DEBUG, logger="agents.tools"):
        with patch(
            "agents.tools.aretrieve_evidence_with_retry",
            AsyncMock(side_effect=TimeoutError("read timeout")),
        ):
            payload = await aknowledge_search.ainvoke({"query": "x"})

    assert payload["error_kind"] == "unavailable"
    levels = {r.levelno for r in caplog.records if r.name == "agents.tools"}
    assert logging.ERROR not in levels


@pytest.mark.asyncio
async def test_internal_defect_is_error_with_stacktrace(caplog):
    """代码缺陷 → ERROR + 堆栈。`logger.exception` 必须真的带上 traceback。"""
    import logging

    with caplog.at_level(logging.DEBUG, logger="agents.tools"):
        with patch(
            "agents.tools.aretrieve_evidence_with_retry",
            AsyncMock(side_effect=KeyError("final_context")),
        ):
            payload = await aknowledge_search.ainvoke({"query": "x"})

    assert payload["status"] == "error"
    assert payload["error_kind"] == "internal"
    errors = [r for r in caplog.records if r.name == "agents.tools" and r.levelno == logging.ERROR]
    assert errors, "内部缺陷必须记 ERROR"
    assert errors[0].exc_info is not None, "必须保留堆栈，否则无法定位"


@pytest.mark.asyncio
async def test_empty_result_is_not_an_error():
    """空结果是**正常结局**：status=empty，且不带任何 error 字段。

    这条钉住一个设计取舍：项目**不**为「知识库确实没有」设异常类型，
    它走正常返回路径 —— 否则「正常」与「故障」会共用同一条控制流。
    """
    fused = FusedEvidence(text_evidences=[], final_context="", sources=[])
    with patch(
        "agents.tools.aretrieve_evidence_with_retry",
        AsyncMock(return_value=(fused, _verifier())),
    ):
        payload = await aknowledge_search.ainvoke({"query": "x"})

    assert payload["status"] == "empty"
    assert payload["error"] is None
    assert payload["error_kind"] is None
