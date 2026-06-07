from __future__ import annotations

import logging
import math
import time
from typing import List

import httpx

from langchain_core.embeddings import Embeddings
from pydantic import BaseModel

from app.config import settings
from app.rag.metrics import metrics

logger = logging.getLogger(__name__)

# 单批请求数量（本地 Ollama / 远程 API 均适用）
BATCH_SIZE = 64  # bge-m3 on local Ollama handles 64-128 easily; 64 = ~2.5x fewer round trips vs 25
# 单条文本最大字符数（bge-m3 8192 tokens，中文约 1-2 token/字，保守取 3000）
MAX_TEXT_LENGTH = 3000
_sparse_probe_cache: dict[str, object] | None = None


def _embedding_timeout() -> httpx.Timeout:
    total = float(settings.EMBEDDING_TIMEOUT or 60)
    return httpx.Timeout(total, connect=min(5.0, total), read=total, write=total, pool=min(5.0, total))


def _embedding_limits() -> httpx.Limits:
    return httpx.Limits(max_connections=50, max_keepalive_connections=10)


class OpenAICompatibleEmbeddings(BaseModel, Embeddings):
    """OpenAI 兼容 Embedding（支持 Ollama / DashScope / 任何 OpenAI 格式 API，自动分批）"""

    api_key: str = ""
    base_url: str = "http://localhost:11434/v1"
    model: str = "bge-m3"

    model_config = {"arbitrary_types_allowed": True}

    def _build_headers(self) -> dict[str, str]:
        """构建请求头：本地服务（Ollama）无需 Authorization"""
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self.api_key and self.api_key not in ("ollama", ""):
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _has_nan(vec: List[float]) -> bool:
        """检测向量中是否包含 NaN"""
        return any(math.isnan(v) for v in vec)

    def _embed_single(self, text: str) -> List[float]:
        """单条文本 embedding（用于批量失败时的逐条回退）"""
        s = str(text).strip() or " "
        resp = httpx.post(
            f"{self.base_url}/embeddings",
            headers=self._build_headers(),
            json={"model": self.model, "input": [s[:MAX_TEXT_LENGTH]]},
            timeout=_embedding_timeout(),
        )
        if resp.status_code != 200:
            logger.warning("Single embedding failed (%d), using zero vector", resp.status_code)
            return [0.0] * 1024
        data = resp.json()
        vec = data["data"][0]["embedding"]
        if self._has_nan(vec):
            logger.warning("NaN in single embedding, using zero vector for: %s", s[:80])
            return [0.0] * 1024
        return vec

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """单批次调用 Embedding API（同步，OpenAI /v1/embeddings 格式）

        当批量请求失败或返回 NaN 时，自动逐条回退重试。
        """
        # 截断超长文本 + 过滤空文本，防止 400 错误
        truncated = []
        truncated_count = 0
        original_lengths: list[int] = []
        for t in texts:
            s = str(t).strip()
            if not s:
                s = " "  # 空文本用空格占位，避免 API 拒绝
            original_lengths.append(len(s))
            if len(s) > MAX_TEXT_LENGTH:
                truncated_count += 1
            truncated.append(s[:MAX_TEXT_LENGTH])

        with metrics.timer("embedding_batch", stage="embeddings", tags={"model": self.model, "mode": "sync"}) as mt:
            mt.update({
                "batch_size": len(texts),
                "avg_text_chars": round(sum(original_lengths) / len(original_lengths), 3) if original_lengths else 0.0,
                "max_text_chars": max(original_lengths) if original_lengths else 0,
                "truncated_count": truncated_count,
            })
            try:
                resp = httpx.post(
                    f"{self.base_url}/embeddings",
                    headers=self._build_headers(),
                    json={"model": self.model, "input": truncated},
                    timeout=_embedding_timeout(),
                )
                resp.raise_for_status()
                data = resp.json()
                sorted_data = sorted(data["data"], key=lambda x: x["index"])
                mt.set("embeddings_count", len(sorted_data))
                results = [item["embedding"] for item in sorted_data]
            except Exception as e:
                logger.warning("Batch embedding failed: %s, falling back to single", e)
                results = [self._embed_single(t) for t in truncated]
                mt.set("embeddings_count", len(results))
                return results

            # 检查 NaN，逐条回退
            nan_indices = [i for i, v in enumerate(results) if self._has_nan(v)]
            if nan_indices:
                logger.warning("NaN detected in %d/%d embeddings, retrying individually", len(nan_indices), len(results))
                for i in nan_indices:
                    results[i] = self._embed_single(truncated[i])

            return results

    async def _aembed_single(self, text: str, client: httpx.AsyncClient | None = None) -> List[float]:
        """单条文本 embedding（异步，用于批量失败时的逐条回退）"""
        if client is None:
            async with httpx.AsyncClient(timeout=_embedding_timeout(), limits=_embedding_limits()) as scoped_client:
                return await self._aembed_single(text, client=scoped_client)
        s = str(text).strip() or " "
        resp = await client.post(
            f"{self.base_url}/embeddings",
            headers=self._build_headers(),
            json={"model": self.model, "input": [s[:MAX_TEXT_LENGTH]]},
        )
        if resp.status_code != 200:
            logger.warning("Async single embedding failed (%d), using zero vector", resp.status_code)
            return [0.0] * 1024
        data = resp.json()
        vec = data["data"][0]["embedding"]
        if self._has_nan(vec):
            logger.warning("NaN in async single embedding, using zero vector for: %s", s[:80])
            return [0.0] * 1024
        return vec

    async def _aembed_batch(self, texts: List[str], client: httpx.AsyncClient | None = None) -> List[List[float]]:
        """单批次调用 Embedding API（异步，OpenAI /v1/embeddings 格式）

        当批量请求失败或返回 NaN 时，自动逐条回退重试。
        """
        if client is None:
            async with httpx.AsyncClient(timeout=_embedding_timeout(), limits=_embedding_limits()) as scoped_client:
                return await self._aembed_batch(texts, client=scoped_client)
        truncated = []
        truncated_count = 0
        original_lengths: list[int] = []
        for t in texts:
            s = str(t).strip()
            if not s:
                s = " "
            original_lengths.append(len(s))
            if len(s) > MAX_TEXT_LENGTH:
                truncated_count += 1
            truncated.append(s[:MAX_TEXT_LENGTH])

        with metrics.timer("embedding_batch", stage="embeddings", tags={"model": self.model, "mode": "async"}) as mt:
            mt.update({
                "batch_size": len(texts),
                "avg_text_chars": round(sum(original_lengths) / len(original_lengths), 3) if original_lengths else 0.0,
                "max_text_chars": max(original_lengths) if original_lengths else 0,
                "truncated_count": truncated_count,
            })
            try:
                resp = await client.post(
                    f"{self.base_url}/embeddings",
                    headers=self._build_headers(),
                    json={"model": self.model, "input": truncated},
                )
                resp.raise_for_status()
                data = resp.json()
                sorted_data = sorted(data["data"], key=lambda x: x["index"])
                mt.set("embeddings_count", len(sorted_data))
                results = [item["embedding"] for item in sorted_data]
            except Exception as e:
                logger.warning("Async batch embedding failed: %s, falling back to single", e)
                results = []
                for t in truncated:
                    results.append(await self._aembed_single(t, client=client))
                mt.set("embeddings_count", len(results))
                return results

            # 检查 NaN，逐条回退
            nan_indices = [i for i, v in enumerate(results) if self._has_nan(v)]
            if nan_indices:
                logger.warning("NaN detected in %d/%d async embeddings, retrying individually", len(nan_indices), len(results))
                for i in nan_indices:
                    results[i] = await self._aembed_single(truncated[i], client=client)

            return results

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """分批 Embedding，每批 BATCH_SIZE 条（同步，并发请求）"""
        if not texts:
            return []

        start = time.perf_counter()
        batches = [texts[i:i + BATCH_SIZE] for i in range(0, len(texts), BATCH_SIZE)]

        if len(batches) <= 1:
            all_embeddings = self._embed_batch(texts)
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            results: dict[int, list] = {}
            with ThreadPoolExecutor(max_workers=min(len(batches), 4)) as pool:
                futures = {pool.submit(self._embed_batch, batch): idx
                           for idx, batch in enumerate(batches)}
                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        results[idx] = future.result()
                    except Exception as e:
                        logger.warning("Batch %d failed: %s", idx, e)
                        results[idx] = [[0.0] * 1024] * len(batches[idx])
            all_embeddings = []
            for i in range(len(batches)):
                all_embeddings.extend(results.get(i, []))

        metrics.emit(
            event="embed_documents",
            stage="embeddings",
            duration_ms=round((time.perf_counter() - start) * 1000, 3),
            tags={"model": self.model, "mode": "sync"},
            values={
                "total_texts": len(texts),
                "total_batches": len(batches),
                "embedding_count": len(all_embeddings),
            },
        )

        return all_embeddings

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """分批 Embedding，每批 BATCH_SIZE 条（异步，并发请求）"""
        if not texts:
            return []

        start = time.perf_counter()
        batches = [texts[i:i + BATCH_SIZE] for i in range(0, len(texts), BATCH_SIZE)]

        async with httpx.AsyncClient(timeout=_embedding_timeout(), limits=_embedding_limits()) as client:
            if len(batches) <= 1:
                all_embeddings = await self._aembed_batch(texts, client=client)
            else:
                import asyncio
                tasks = [self._aembed_batch(batch, client=client) for batch in batches]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                all_embeddings = []
                for i, result in enumerate(batch_results):
                    if isinstance(result, Exception):
                        logger.warning("Async batch %d failed: %s", i, result)
                        all_embeddings.extend([[0.0] * 1024] * len(batches[i]))
                    else:
                        all_embeddings.extend(result)

        metrics.emit(
            event="embed_documents",
            stage="embeddings",
            duration_ms=round((time.perf_counter() - start) * 1000, 3),
            tags={"model": self.model, "mode": "async"},
            values={
                "total_texts": len(texts),
                "total_batches": len(batches),
                "embedding_count": len(all_embeddings),
            },
        )

        return all_embeddings

    def embed_query(self, text: str) -> List[float]:
        result = self.embed_documents([str(text)])
        return result[0]

    async def aembed_query(self, text: str) -> List[float]:
        result = await self.aembed_documents([str(text)])
        return result[0]


def get_embeddings() -> Embeddings:
    """返回 Embedding 模型（通过 OpenAI 兼容接口，支持本地 Ollama / 远程 API）"""
    return OpenAICompatibleEmbeddings(
        api_key=settings.EMBEDDING_API_KEY,
        base_url=settings.EMBEDDING_API_BASE,
        model=settings.EMBEDDING_MODEL,
    )


def probe_bge_m3_sparse_support(force: bool = False) -> dict[str, object]:
    global _sparse_probe_cache
    if _sparse_probe_cache is not None and not force:
        return dict(_sparse_probe_cache)

    probe = OpenAICompatibleEmbeddings(
        api_key=settings.EMBEDDING_API_KEY,
        base_url=settings.EMBEDDING_API_BASE,
        model=settings.EMBEDDING_MODEL,
    )
    payload = {
        "model": settings.EMBEDDING_MODEL,
        "input": ["进程调度算法"],
        "return_sparse": True,
        "return_colbert_vecs": True,
    }
    result: dict[str, object] = {
        "model": settings.EMBEDDING_MODEL,
        "base_url": settings.EMBEDDING_API_BASE,
        "available": False,
        "has_dense": False,
        "has_sparse": False,
        "has_colbert": False,
        "response_keys": [],
        "error": "",
    }
    try:
        resp = httpx.post(
            f"{settings.EMBEDDING_API_BASE}/embeddings",
            headers=probe._build_headers(),
            json=payload,
            timeout=_embedding_timeout(),
        )
        result["status_code"] = resp.status_code
        resp.raise_for_status()
        data = resp.json()
        item = (data.get("data") or [{}])[0]
        keys = sorted(item.keys())
        result["available"] = True
        result["response_keys"] = keys
        result["has_dense"] = "embedding" in item
        result["has_sparse"] = any(k in item for k in ("sparse_embedding", "sparse", "lexical_weights"))
        result["has_colbert"] = any(k in item for k in ("colbert_vecs", "colbert", "multi_vector"))
    except Exception as e:
        result["error"] = str(e)
    _sparse_probe_cache = result
    return dict(result)
