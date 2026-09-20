"""同步检索桥接（`retrieve_documents`）的测试。

背景：`retrieve_documents` 曾有一份 448 行的同步副本，与 `aretrieve_documents` 逐段对应。
实测两者当前行为一致（15 条 query 的条数/集合/顺序全同），但双份实现迟早漂移，
且它唯一的调用方是 `warmup_query_cache`（入库后的缓存预热）。已改为委托，删除 448 行重复逻辑。

本文件钉住三件事：
1. **委托是真的**（不是又写了一份）—— 用 spy 断言参数原样透传、返回值原样返回；
2. **签名不许漂移** —— 委托一旦漏传参数就是静默丢功能，结构断言比行为断言更早发现；
3. **在运行中的事件循环里调用要给出可读错误**，而不是 `asyncio.run` 的晦涩报错。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from pathlib import Path

import pytest
from langchain_core.documents import Document

from rag import retriever as R

_skip_gate = pytest.mark.skipif(
    os.environ.get("RUN_RETRIEVAL_GATE") != "1",
    reason="端到端等价性需显式开启：设置 RUN_RETRIEVAL_GATE=1（需建临时索引，约 35s）",
)


class TestSyncBridgeDelegates:
    def test_calls_async_impl_with_same_positional_args(self, monkeypatch):
        captured: list[tuple] = []
        sentinel = [Document(page_content="x", metadata={})]

        async def fake_async(*args, **kwargs):
            captured.append((args, kwargs))
            return sentinel

        monkeypatch.setattr(R, "aretrieve_documents", fake_async)
        out = R.retrieve_documents("q", "coll", 7, 0.5, False, {"a": 1}, None, None, ["s"])

        assert out is sentinel, "必须原样返回异步实现的结果，不能另做加工"
        # 第 10 个位置参数是 on_stage（阶段进度回调）；同步预热场景不传，恒为 None
        assert captured == [
            (("q", "coll", 7, 0.5, False, {"a": 1}, None, None, ["s"], None), {})
        ]

    def test_defaults_are_forwarded(self, monkeypatch):
        captured: list[tuple] = []

        async def fake_async(*args, **kwargs):
            captured.append((args, kwargs))
            return []

        monkeypatch.setattr(R, "aretrieve_documents", fake_async)
        R.retrieve_documents("q")
        args = captured[0][0]
        assert args[0] == "q"
        assert len(args) == 10, "10 个形参应全部透传，避免漏参导致静默丢功能"

    def test_async_impl_is_coroutine_function(self):
        assert asyncio.iscoroutinefunction(R.aretrieve_documents)
        assert not asyncio.iscoroutinefunction(R.retrieve_documents)

    def test_signatures_match(self):
        """结构守卫：签名一旦漂移，委托就会静默丢参数 —— 比行为断言更早发现。"""
        assert inspect.signature(R.retrieve_documents) == inspect.signature(R.aretrieve_documents)

    def test_does_not_keep_a_second_pipeline_copy(self):
        """防止后人"顺手"把流水线逻辑又抄回同步版。"""
        src = inspect.getsource(R.retrieve_documents)
        assert len(src.splitlines()) < 60, (
            f"retrieve_documents 又长到 {len(src.splitlines())} 行了 —— "
            "它应该是薄委托，不是第二份流水线"
        )
        for marker in ("_multi_route_search", "weighted_rrf_merge", "dedent", "stage_ms"):
            assert marker not in src, f"同步版不应再出现流水线细节: {marker}"


class TestSyncBridgeLoopGuard:
    def test_raises_readable_error_inside_running_loop(self):
        async def call_it():
            return R.retrieve_documents("q")

        with pytest.raises(RuntimeError, match="不能在已运行的事件循环中调用"):
            asyncio.run(call_it())

    def test_error_message_points_to_the_async_alternative(self):
        async def call_it():
            return R.retrieve_documents("q")

        with pytest.raises(RuntimeError, match="await aretrieve_documents"):
            asyncio.run(call_it())

    def test_works_outside_event_loop(self, monkeypatch):
        async def fake_async(*args, **kwargs):
            return [Document(page_content="ok", metadata={})]

        monkeypatch.setattr(R, "aretrieve_documents", fake_async)
        out = R.retrieve_documents("q")
        assert len(out) == 1
        assert out[0].page_content == "ok"


@_skip_gate
class TestSyncAsyncEquivalence:
    """端到端等价性：真实索引上，同步与异步路径必须给出完全相同的文档序列。

    这是"删除 448 行副本"这个改动唯一的正确性依据 —— 单测只能证明"委托调用了异步实现"，
    证明不了"两条路径的最终产出一致"。
    """

    def test_sync_and_async_agree_on_real_queries(self):
        import shutil
        import tempfile

        from evaluation.retrieval_gate import (
            build_index,
            configure_for_gate,
            load_golden_queries,
            wait_for_index_ready,
        )

        tmp_dir = tempfile.mkdtemp(prefix="sync_bridge_")
        try:
            configure_for_gate(tmp_dir)
            counts = build_index()
            assert sum(counts.values()) > 0, "索引为空"
            wait_for_index_ready(sorted(counts))

            queries = [q for q, _ in load_golden_queries("evals/sample_408.jsonl", limit=12)]
            baseline_path = Path("evals/retrieval_baseline.json")
            assert baseline_path.exists()
            json.loads(baseline_path.read_text(encoding="utf-8"))  # 基线可读

            for query in queries:
                sync_docs = R.retrieve_documents(query, k=5, use_rerank=False)
                async_docs = asyncio.run(R.aretrieve_documents(query, k=5, use_rerank=False))
                assert [d.page_content for d in sync_docs] == [
                    d.page_content for d in async_docs
                ], f"同步/异步结果不一致: {query}"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)
