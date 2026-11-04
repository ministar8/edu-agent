"""query embedding 缓存（减少重复 TEI 调用）。

背景：同一条 route query 会被多条向量路由各 embed 一次；156 条消融里
这是 TEI 压力的主要来源，也是偶发超时的诱因。缓存只覆盖 query，
不覆盖 documents（后者基本唯一，缓存无收益）。

反向验证：去掉 `embed_query`/`aembed_query` 里的缓存检查，前两条用例失败。
"""

from __future__ import annotations

import asyncio

import pytest

from rag.common.embeddings import (
    OpenAICompatibleEmbeddings,
    clear_query_cache,
    query_cache_stats,
)


def _embedder(model: str = "m", base_url: str = "http://test") -> OpenAICompatibleEmbeddings:
    return OpenAICompatibleEmbeddings(api_key="", base_url=base_url, model=model)


def test_sync_query_cache_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_query_cache()
    calls: list[int] = []

    def fake_embed_documents(self, texts):  # noqa: ANN001
        calls.append(len(texts))
        return [[float(len(t))] for t in texts]

    monkeypatch.setattr(OpenAICompatibleEmbeddings, "embed_documents", fake_embed_documents)
    e = _embedder()
    assert e.embed_query("栈") == [1.0]
    assert e.embed_query("栈") == [1.0]
    assert len(calls) == 1
    assert query_cache_stats()["size"] == 1


def test_async_query_cache_hits(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_query_cache()
    calls: list[int] = []

    async def fake_aembed_documents(self, texts):  # noqa: ANN001
        calls.append(len(texts))
        return [[1.0] for _ in texts]

    monkeypatch.setattr(OpenAICompatibleEmbeddings, "aembed_documents", fake_aembed_documents)
    e = _embedder()
    assert asyncio.run(e.aembed_query("q")) == [1.0]
    assert asyncio.run(e.aembed_query("q")) == [1.0]
    assert len(calls) == 1


def test_cache_key_separates_model_and_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_query_cache()
    calls: list[tuple[str, str]] = []

    def fake_embed_documents(self, texts):  # noqa: ANN001
        calls.append((self.base_url, self.model))
        return [[1.0] for _ in texts]

    monkeypatch.setattr(OpenAICompatibleEmbeddings, "embed_documents", fake_embed_documents)
    _embedder(model="a").embed_query("q")
    _embedder(model="b").embed_query("q")
    _embedder(model="a", base_url="http://other").embed_query("q")
    assert len(calls) == 3


def test_returned_vector_is_a_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_query_cache()

    def fake_embed_documents(self, texts):  # noqa: ANN001
        return [[1.0, 2.0] for _ in texts]

    monkeypatch.setattr(OpenAICompatibleEmbeddings, "embed_documents", fake_embed_documents)
    e = _embedder()
    first = e.embed_query("q")
    first[0] = 99.0
    assert e.embed_query("q") == [1.0, 2.0]
