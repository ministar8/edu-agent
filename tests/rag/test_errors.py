"""检索域异常层级与分类：`rag.errors`。

这一层是「三类失败被抹平成同一类」的修复基础 —— 在此之前，
TEI 超时、连接被拒、`KeyError` 全都以通用 `RuntimeError` 向上传播，
到边界处只剩一句「检索失败：…」，日志里的 ERROR 无法判断严重程度。

因此测试要钉住两件事：
1. **分类规则本身**（纯函数，可穷举）
2. **调用点确实抛出了正确的类型** —— 否则分类器只是摆设（判断规则：有测试 ≠ 在用）
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from rag.errors import (
    RagError,
    RagInternalError,
    RetrievalUnavailable,
    classify_retrieval_error,
)


class TestHierarchy:
    """层级关系：捕获 `RagError` 应当能拿到所有检索域失败。"""

    def test_all_are_rag_errors(self):
        assert issubclass(RetrievalUnavailable, RagError)
        assert issubclass(RagInternalError, RagError)

    def test_rag_error_is_exception(self):
        assert issubclass(RagError, Exception)

    def test_unavailable_and_internal_are_disjoint(self):
        """两者必须是兄弟而非继承关系 —— 否则 `isinstance` 判断会互相误伤。"""
        assert not issubclass(RetrievalUnavailable, RagInternalError)
        assert not issubclass(RagInternalError, RetrievalUnavailable)


class TestClassifyRetrievalError:
    """分类规则：网络/超时 → 可重试；其余 → 内部缺陷。"""

    def test_rag_error_passes_through_unchanged(self):
        """已经是 RagError 的原样返回 —— 保留调用点给出的更精确语义。"""
        original = RetrievalUnavailable("TEI 502")
        assert classify_retrieval_error(original) is original

    def test_internal_error_passes_through_unchanged(self):
        original = RagInternalError("契约破坏")
        assert classify_retrieval_error(original) is original

    @pytest.mark.parametrize(
        "exc",
        [
            httpx.TimeoutException("timed out"),
            httpx.ConnectError("connection refused"),
            httpx.ReadTimeout("read timeout"),
            TimeoutError("builtin timeout"),
            ConnectionError("network unreachable"),
        ],
        ids=["httpx-timeout", "httpx-connect", "httpx-read-timeout", "builtin-timeout", "conn"],
    )
    def test_network_and_timeout_are_unavailable(self, exc):
        assert isinstance(classify_retrieval_error(exc), RetrievalUnavailable)

    def test_http_status_error_is_unavailable(self):
        """4xx/5xx 也归「依赖不可用」：服务答复了，但没给出可用的向量。"""
        request = httpx.Request("POST", "http://localhost:11435/embeddings")
        response = httpx.Response(503, request=request)
        exc = httpx.HTTPStatusError("503", request=request, response=response)
        assert isinstance(classify_retrieval_error(exc), RetrievalUnavailable)

    @pytest.mark.parametrize(
        "exc",
        [RuntimeError("boom"), KeyError("data"), ValueError("bad"), TypeError("nope")],
        ids=["runtime", "key", "value", "type"],
    )
    def test_other_exceptions_are_internal(self, exc):
        """宁可误报为缺陷，也不要漏报 —— 漏报会让真缺陷永远只表现为「答得不对」。"""
        assert isinstance(classify_retrieval_error(exc), RagInternalError)

    def test_message_is_preserved(self):
        """原始信息必须保留，否则日志里就丢掉了定位线索。"""
        err = classify_retrieval_error(RuntimeError("hnsw segment reader 缺失"))
        assert "hnsw segment reader" in str(err)

    def test_classified_error_keeps_catchable_as_rag_error(self):
        """分类后必须能被 `except RagError` 统一捕获（这是本层级的用途）。"""
        with pytest.raises(RagError):
            raise classify_retrieval_error(KeyError("x"))


class TestChromaClassification:
    """Chroma 异常：只把**真正暂时性**的归为可重试。

    ★ 这里的反向断言才是重点：`InternalError` 在本项目里对应
    「HNSW 段文件未落盘」，实测**重试与重开 client 都无效，只有 `rebuild=True` 能修**
    （见 `tests/rag/test_ingest_readiness.py` 的实测结论）。
    把它误归为「可重试」会让值班的人反复重跑入库，而问题永远不会自愈。
    """

    def test_rate_limit_is_unavailable(self):
        from chromadb.errors import RateLimitError

        err = classify_retrieval_error(RateLimitError("429 too many requests"))
        assert isinstance(err, RetrievalUnavailable)

    def test_quota_error_is_unavailable(self):
        from chromadb.errors import QuotaError

        assert isinstance(
            classify_retrieval_error(QuotaError("quota exceeded")), RetrievalUnavailable
        )

    def test_chroma_internal_error_is_not_unavailable(self):
        """★ 核心反向断言：持久故障不得被归为「可重试」。"""
        from chromadb.errors import InternalError

        err = classify_retrieval_error(
            InternalError("Error creating hnsw segment reader: Nothing found on disk")
        )
        assert isinstance(err, RagInternalError)
        assert not isinstance(err, RetrievalUnavailable)

    @pytest.mark.parametrize(
        "exc_name",
        ["InvalidArgumentError", "InvalidDimensionException", "DuplicateIDError"],
    )
    def test_chroma_client_errors_are_internal(self, exc_name):
        """调用方用错 API 属代码缺陷，不是「依赖挂了」。"""
        import chromadb.errors as ce

        exc = getattr(ce, exc_name)("boom")
        assert isinstance(classify_retrieval_error(exc), RagInternalError)


class TestEmbeddingCallSiteRaisesTypedErrors:
    """调用点契约：`embeddings.py` 必须抛出正确的类型。

    ★ 这一组是**反向验证的靶子** —— 如果只测分类器，把 `embeddings.py` 里的
    `RetrievalUnavailable` 改回 `RuntimeError` 测试仍然全绿，那分类器就白做了。
    """

    @staticmethod
    def _resp(status_code: int, payload: dict | None = None) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = payload or {}
        return resp

    def test_http_error_raises_unavailable(self):
        from rag.embeddings import OpenAICompatibleEmbeddings

        emb = OpenAICompatibleEmbeddings()
        with patch("rag.embeddings.httpx.post", return_value=self._resp(500)):
            with pytest.raises(RetrievalUnavailable):
                emb._embed_single("什么是虚拟内存")

    def test_nan_raises_internal(self):
        """NaN 不是暂时性故障（重试无用），必须归为内部缺陷而不是不可用。"""
        from rag.embeddings import OpenAICompatibleEmbeddings

        emb = OpenAICompatibleEmbeddings()
        payload = {"data": [{"embedding": [float("nan"), 0.1]}]}
        with patch("rag.embeddings.httpx.post", return_value=self._resp(200, payload)):
            with pytest.raises(RagInternalError):
                emb._embed_single("什么是虚拟内存")

    def test_success_returns_vector(self):
        """对照组：正常路径不受影响，避免「把好路径也改坏」。"""
        from rag.embeddings import OpenAICompatibleEmbeddings

        emb = OpenAICompatibleEmbeddings()
        payload = {"data": [{"embedding": [0.1, 0.2]}]}
        with patch("rag.embeddings.httpx.post", return_value=self._resp(200, payload)):
            assert emb._embed_single("x") == [0.1, 0.2]

    @pytest.mark.asyncio
    async def test_async_http_error_raises_unavailable(self):
        from rag.embeddings import OpenAICompatibleEmbeddings

        emb = OpenAICompatibleEmbeddings()
        client = MagicMock()
        client.post = _async_return(self._resp(503))
        with pytest.raises(RetrievalUnavailable):
            await emb._aembed_single("什么是虚拟内存", client=client)

    @pytest.mark.asyncio
    async def test_async_nan_raises_internal(self):
        from rag.embeddings import OpenAICompatibleEmbeddings

        emb = OpenAICompatibleEmbeddings()
        client = MagicMock()
        client.post = _async_return(self._resp(200, {"data": [{"embedding": [float("nan"), 1.0]}]}))
        with pytest.raises(RagInternalError):
            await emb._aembed_single("x", client=client)


def _async_return(value):
    """把同步 mock 返回值包成可 await 的协程函数。"""

    async def _inner(*_args, **_kwargs):
        return value

    return _inner
