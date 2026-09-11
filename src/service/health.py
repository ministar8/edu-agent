"""依赖健康探针：反映各外部依赖（Embedding / Reranker / ChromaDB / LangSmith）的可用性。

设计要点（对齐参考项目）：
- **永远返回 200**，各依赖状态放在 body 中。该端点同时被 Docker healthcheck 使用，
  依赖不可用不应让容器被判定为不健康。
- 各探测**并发执行**并带短超时，避免拖慢健康检查。
- 判活口径偏保守：仅"网络不可达"或"服务端 5xx"记 down。若用户把 X 换成非 TEI 的
  OpenAI 兼容端点，`/health` 可能返回 404 —— 那说明服务可达，不应误报为故障。
"""

import asyncio
import logging
import socket
import time
from pathlib import Path
from typing import Any

import httpx

from core.settings import settings

logger = logging.getLogger(__name__)

PROBE_TIMEOUT = 2.0
CHROMA_TCP_TIMEOUT = 0.25


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)


async def _probe_http(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    """GET 一个 URL 判活：网络错误或 5xx 记 down，其余（含 404/401）记 up。"""
    started = time.perf_counter()
    try:
        response = await client.get(url)
    except Exception as exc:
        return {"status": "down", "latency_ms": _elapsed_ms(started), "error": type(exc).__name__}
    if response.status_code >= 500:
        return {
            "status": "down",
            "latency_ms": _elapsed_ms(started),
            "error": f"HTTP {response.status_code}",
        }
    return {"status": "up", "latency_ms": _elapsed_ms(started)}


def _is_tcp_reachable(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=CHROMA_TCP_TIMEOUT):
            return True
    except OSError:
        return False


async def _probe_embedding(client: httpx.AsyncClient) -> dict[str, Any]:
    return await _probe_http(client, f"{settings.EMBEDDING_API_BASE}/health")


async def _probe_reranker(client: httpx.AsyncClient) -> dict[str, Any]:
    if not settings.RERANK_ENABLED:
        return {"status": "disabled"}
    return await _probe_http(client, f"{settings.RERANK_LOCAL_URL}/health")


async def _probe_chromadb() -> dict[str, Any]:
    """先探 Chroma server，不可达时退化为本地持久化目录检查。

    与 rag.vectorstore 选择客户端的方式保持一致（server 优先，否则用本地目录）。
    """
    started = time.perf_counter()
    target = f"{settings.CHROMA_HOST}:{settings.CHROMA_PORT}"
    if _is_tcp_reachable(settings.CHROMA_HOST, settings.CHROMA_PORT):
        return {
            "status": "up",
            "latency_ms": _elapsed_ms(started),
            "mode": "http",
            "target": target,
        }

    persist_dir = Path(settings.CHROMA_PERSIST_DIR)
    if persist_dir.exists():
        return {
            "status": "up",
            "latency_ms": _elapsed_ms(started),
            "mode": "persistent",
            "target": str(persist_dir),
        }
    return {
        "status": "down",
        "latency_ms": _elapsed_ms(started),
        "mode": "persistent",
        "target": str(persist_dir),
        "error": "持久化目录不存在",
    }


def _probe_langsmith() -> dict[str, Any]:
    """只报告配置状态，不发网络请求（避免为健康检查产生额外配额与延迟）。"""
    if not settings.LANGCHAIN_TRACING_V2:
        return {"status": "disabled"}
    if not settings.LANGCHAIN_API_KEY:
        return {"status": "misconfigured", "error": "缺少 LANGCHAIN_API_KEY"}
    return {"status": "enabled", "project": settings.LANGCHAIN_PROJECT}


async def collect_health() -> dict[str, Any]:
    """并发探测所有依赖，返回整体状态与逐项明细。"""
    async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as client:
        embedding, reranker, chromadb = await asyncio.gather(
            _probe_embedding(client),
            _probe_reranker(client),
            _probe_chromadb(),
        )

    dependencies: dict[str, dict[str, Any]] = {
        "embedding": embedding,
        "reranker": reranker,
        "chromadb": chromadb,
        "langsmith": _probe_langsmith(),
    }

    degraded = [name for name, info in dependencies.items() if info["status"] == "down"]
    if degraded:
        logger.warning("健康检查降级，依赖不可用: %s", ", ".join(degraded))

    return {
        "status": "degraded" if degraded else "ok",
        "degraded": degraded,
        "dependencies": dependencies,
    }
