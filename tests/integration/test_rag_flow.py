"""RAG 检索集成测试：aretrieve_evidence 端到端入口与返回结构。

纯本地 I/O，mock 底层检索/融合依赖，不联网、不碰真 Chroma/TEI。
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.documents import Document

from rag.retrieval.evidence import FusedEvidence, TextEvidence
from rag.retrieval.retriever import aretrieve_evidence


def _make_plan() -> Any:
    return type(
        "P",
        (),
        {
            "cat": "concept",
            "depth": type("D", (), {"depth": "standard"})(),
            "retrieval_layer": "vector",
            "route_type": "semantic",
            "k": 5,
            "sub_queries": ["进程调度"],
            "decompose_ms": 2.0,
        },
    )()


def _make_evidence() -> TextEvidence:
    return TextEvidence(
        evidence_id="ev-1",
        content="进程调度是操作系统的核心功能",
        source="os.md",
        score=0.95,
    )


@pytest.mark.asyncio
async def test_rag_flow_returns_fused_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    """aretrieve_evidence 能正常返回 FusedEvidence，结构完整。"""

    async def fake_assemble_fused(*args, **kwargs) -> FusedEvidence:
        return FusedEvidence(
            text_evidences=[_make_evidence()],
            final_context="进程调度是操作系统的核心功能",
            sources=["os.md"],
            used_token_budget=100,
            diversity_score=0.5,
        )

    async def fake_lookup_cached(*args, **kwargs) -> None:
        return None

    async def fake_run_retrieval(*args, **kwargs) -> tuple:
        return (
            [Document(page_content="进程调度是操作系统的核心功能", metadata={"source": "os.md"})],
            10.5,
            "",
            _make_plan(),
        )

    monkeypatch.setattr("rag.retrieval.retriever_io._assemble_fused", fake_assemble_fused)
    monkeypatch.setattr("rag.retrieval.retriever._lookup_cached", fake_lookup_cached)
    monkeypatch.setattr("rag.retrieval.retriever._run_retrieval", fake_run_retrieval)

    result = await aretrieve_evidence("什么是进程调度？", collection_name="os", k=5)

    assert isinstance(result, FusedEvidence)
    assert len(result.text_evidences) == 1
    assert "进程调度" in result.text_evidences[0].content
    assert result.final_context
