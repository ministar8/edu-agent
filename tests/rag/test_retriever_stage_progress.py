"""检索阶段进度回调（`on_stage`）的测试。

背景：SSE 的 `custom` 流管道（schema / 转换 / graph 转发）**早就建好且有测试**
（见 `tests/service/test_custom_stream.py`），但生产代码里**从没调用过
`CustomData.dispatch`** —— 于是前端只能显示「正在检索知识库… Ns」，
明明后端知道自己在哪一步。

本文件钉住新接上的那一环：`rag/` 通过**可选回调**上报阶段，
由 `agents/tools.py` 把回调接到 stream writer（UI 关注点不渗进检索层）。

两个必须守住的契约：

1. **不传回调时检索行为完全不变** —— 门禁、离线评测、缓存预热都走这条路
2. **回调抛错绝不能影响检索结果** —— 进度是锦上添花，不是功能
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from rag import retriever as R

# 与 `aretrieve_documents` 里 _emit_stage 的调用顺序严格一致
ALL_STAGES = ["classify", "plan", "decompose", "recall", "dedup", "rerank", "hyde", "expand"]


def _stub_all_stages(monkeypatch) -> None:
    """把 8 个阶段与收尾函数换成轻量桩，**只验证编排层的上报顺序**。

    真跑一遍阶段需要 Chroma / TEI，那会把「上报顺序」这个纯编排问题绑到外部依赖上；
    各阶段自身的行为已由 `test_retriever_stages.py` 覆盖。
    """
    plan = SimpleNamespace(
        depth=SimpleNamespace(depth="standard", k=5, skip_rerank=False, skip_decompose=False),
        k=5,
        use_rerank=False,
        effective_threshold=0.0,
        coarse_k=5,
        retrieval_layer="L2",
        route_type="T",
    )

    async def fake_classify(query, cat):
        return ["t"], cat

    def fake_plan(*_args, **_kwargs):
        return plan

    async def fake_decompose(*_args, **_kwargs):
        return ["q"], False

    async def fake_recall(_req):
        return []

    async def fake_dedup(*_args, **_kwargs):
        return [], 0, 0

    async def fake_rerank(*_args, **_kwargs):
        return [], False, 0.0

    async def fake_hyde(*_args, **_kwargs):
        return SimpleNamespace(
            docs=[], triggered=False, added_count=0, error="", rerank_used=False, elapsed_ms=0.0
        )

    async def fake_expand(*_args, **_kwargs):
        return SimpleNamespace(docs=[], elapsed_ms=0.0)

    monkeypatch.setattr(R, "_stage_classify_query", fake_classify)
    monkeypatch.setattr(R, "_stage_resolve_plan", fake_plan)
    monkeypatch.setattr(R, "_stage_decompose_query", fake_decompose)
    monkeypatch.setattr(R, "_stage_recall_and_merge", fake_recall)
    monkeypatch.setattr(R, "_stage_dedup_and_threshold", fake_dedup)
    monkeypatch.setattr(R, "_stage_rerank", fake_rerank)
    monkeypatch.setattr(R, "_stage_hyde", fake_hyde)
    monkeypatch.setattr(R, "_stage_expand_windows", fake_expand)
    monkeypatch.setattr(R, "_finalize_retrieval", lambda filtered, **_kwargs: filtered)


class TestEmitStage:
    def test_noop_without_callback(self):
        R._emit_stage(None, "classify")  # 不应抛错

    def test_forwards_stage_id(self):
        seen: list[str] = []
        R._emit_stage(seen.append, "rerank")
        assert seen == ["rerank"]

    def test_swallows_callback_errors(self):
        """进度上报失败绝不能让检索挂掉 —— 这是本功能的安全底线。"""

        def boom(_stage: str) -> None:
            raise ValueError("进度上报炸了")

        R._emit_stage(boom, "classify")  # 不应抛错


class TestStageSequence:
    @pytest.mark.asyncio
    async def test_emits_all_stages_in_order(self, monkeypatch):
        _stub_all_stages(monkeypatch)
        seen: list[str] = []
        await R.aretrieve_documents("q", on_stage=seen.append)
        assert seen == ALL_STAGES

    @pytest.mark.asyncio
    async def test_no_callback_still_returns_docs(self, monkeypatch):
        """不传回调时行为不变 —— 门禁与离线评测依赖这条路径。"""
        _stub_all_stages(monkeypatch)
        docs = await R.aretrieve_documents("q")
        assert isinstance(docs, list)

    @pytest.mark.asyncio
    async def test_broken_callback_does_not_break_retrieval(self, monkeypatch):
        _stub_all_stages(monkeypatch)

        def boom(_stage: str) -> None:
            raise RuntimeError("炸")

        docs = await R.aretrieve_documents("q", on_stage=boom)
        assert isinstance(docs, list)


class TestSinkIsGuarded:
    """`agents/tools.py` 的注入点必须在非流式上下文里安全退化。"""

    def test_sink_returns_none_without_graph_context(self):
        """没有 runnable 上下文时 `get_stream_writer()` 会抛 RuntimeError，
        此时必须返回 None（检索链走 no-op），而不是把异常抛给检索。"""
        from agents.tools import _stage_sink

        assert _stage_sink() is None
