"""评估体系与 RAG 实现的解耦接口（Protocol）

评估模块只依赖这些 Protocol，不直接 import app.rag.*。
具体 RAG 系统通过 adapters.py 中的适配器注入。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


# ════════════════════════════════════════════════════════
#  核心检索接口
# ════════════════════════════════════════════════════════

@runtime_checkable
class RetrieverProtocol(Protocol):
    """检索器抽象接口 — Layer 1 RAGAS 评估的唯一依赖"""

    def retrieve(
        self,
        query: str,
        collection_name: str,
        k: int = 5,
        use_rerank: bool = True,
    ) -> list[dict[str, Any]]:
        """检索相关文档

        Returns:
            [{"content": str, "metadata": dict}, ...]
        """
        ...


# ════════════════════════════════════════════════════════
#  诊断检索接口（Layer 2 需要更细粒度控制）
# ════════════════════════════════════════════════════════

@runtime_checkable
class DiagnosticRetrieverProtocol(RetrieverProtocol, Protocol):
    """可诊断的检索器 — 支持路由消融、reranker 开关、窗口控制"""

    #: 支持的路由名称列表
    route_names: list[str]

    def retrieve_diagnostic(
        self,
        query: str,
        collection_name: str,
        k: int = 5,
        *,
        enabled_routes: list[str] | None = None,
        disable_routes: list[str] | None = None,
        use_rerank: bool | None = None,
        window_size: int | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """带诊断控制的检索

        Returns:
            (documents, timing_info)
            documents: [{"content": str, "metadata": dict}, ...]
            timing_info: {"total_ms": float, "recall_ms": float, ...}
        """
        ...


# ════════════════════════════════════════════════════════
#  查询分解接口
# ════════════════════════════════════════════════════════

@runtime_checkable
class QueryDecomposerProtocol(Protocol):
    """查询分解器接口"""

    def should_decompose(self, query: str) -> bool:
        """判断查询是否应被分解"""
        ...

    def decompose(self, query: str) -> list[str]:
        """分解查询为子查询列表（含原始查询）"""
        ...

    def stats(self) -> dict[str, Any]:
        """获取运行时统计"""
        ...


# ════════════════════════════════════════════════════════
#  Embedding 接口
# ════════════════════════════════════════════════════════

@runtime_checkable
class EmbeddingProtocol(Protocol):
    """Embedding 模型接口 — RAGAS 内部计算需要"""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """将文本列表转为向量列表"""
        ...

    @property
    def langchain_embeddings(self) -> Any:
        """返回 langchain Embeddings 兼容对象（RAGAS 需要）"""
        ...
