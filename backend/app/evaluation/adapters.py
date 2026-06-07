"""评估体系的 RAG 适配器 — 将具体 RAG 实现对接到 Protocol 接口

评估模块通过 protocols.py 的接口访问 RAG，此文件负责桥接。
换 RAG 引擎只需修改此文件，评估代码零改动。
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.documents import Document

from app.evaluation.protocols import (
    DiagnosticRetrieverProtocol,
    EmbeddingProtocol,
    QueryDecomposerProtocol,
    RetrieverProtocol,
)

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════
#  适配器：当前 RAG 系统
# ════════════════════════════════════════════════════════

class CurrentRAGRetriever:
    """适配器：将 app.rag.retriever.retrieve_evidence 对接到 RetrieverProtocol"""

    def retrieve(
        self,
        query: str,
        collection_name: str,
        k: int = 5,
        use_rerank: bool = True,
    ) -> list[dict[str, Any]]:
        from app.rag.retriever import retrieve_evidence
        from app.rag.retrieval_strategy import L2_STANDARD

        # 评估场景：使用 L2_STANDARD depth 确保 k 参数不被 adaptive depth 覆盖
        # （retrieve_evidence 中 k==5 时会被 depth.k 替换，传固定 depth 阻止此行为）
        fused = retrieve_evidence(
            query=query,
            collection_name=collection_name,
            k=k,
            use_rerank=use_rerank,
            depth=L2_STANDARD.depth,
        )
        return [{"content": ev.content, "metadata": dict(ev.metadata) if ev.metadata else {}} for ev in fused.text_evidences]


# Metadata 路由名称集合（与 diagnosis.py 共享）
META_ROUTE_NAMES = frozenset({
    "code_meta", "exercise_meta", "answer_meta",
    "concept_meta", "structured_meta",
    "section_meta", "formula_meta", "table_meta", "merged_qa_meta",
})


class CurrentDiagnosticRetriever:
    """适配器：将当前 RAG 系统的内部组件对接到 DiagnosticRetrieverProtocol

    与主管线保持一致：使用查询分类、路由自适应 k、加权 RRF、动态 dedup。
    """

    route_names: list[str] = [
        "semantic", "keyword_bm25", "focus", "expanded", "kg_expand",
        "code_meta", "exercise_meta", "answer_meta",
        "concept_meta", "structured_meta",
        "section_meta", "formula_meta", "table_meta", "merged_qa_meta",
    ]

    def retrieve(
        self,
        query: str,
        collection_name: str,
        k: int = 5,
        use_rerank: bool = True,
    ) -> list[dict[str, Any]]:
        docs, _ = self.retrieve_diagnostic(
            query, collection_name, k, use_rerank=use_rerank,
        )
        return docs

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
        from app.rag.postprocess import dedup_same_section, sentence_window_expand
        from app.rag.reranker import rerank
        from app.rag.rag_utils import extract_query_terms, normalize_query_text
        from app.rag.retriever import _multi_route_search
        from app.rag.query_classifier import classify_query, RetrievalDepth
        from app.rag.retrieval_strategy import resolve_retrieval_strategy

        start = time.perf_counter()
        timing: dict[str, float] = {}

        # ── 查询分类 + Adaptive Depth（与主管线一致）──
        normalized = normalize_query_text(query)
        terms = extract_query_terms(normalized)
        cat = classify_query(query, terms)
        strategy = resolve_retrieval_strategy(cat)
        depth = strategy.depth

        # ── 多路召回（委托 _multi_route_search，与主管线一致）──
        t0 = time.perf_counter()

        # 过滤路由：构造 depth 覆盖
        effective_depth = depth
        if disable_routes is not None:
            # 禁用 BM25 路由时设置 skip_bm25
            if "keyword_bm25" in disable_routes:
                effective_depth = RetrievalDepth(
                    depth=depth.depth, k=depth.k,
                    skip_bm25=True, skip_kg=depth.skip_kg,
                    skip_decompose=depth.skip_decompose, skip_hyde=depth.skip_hyde,
                    skip_metadata_routes=depth.skip_metadata_routes,
                    skip_rerank=depth.skip_rerank,
                    max_metadata_routes=depth.max_metadata_routes,
                )
            # 禁用 metadata 路由时设置 skip_metadata_routes
            meta_routes = {"code_meta", "exercise_meta", "answer_meta",
                           "concept_meta", "structured_meta",
                           "section_meta", "formula_meta", "table_meta", "merged_qa_meta"}
            if any(r in meta_routes for r in disable_routes):
                effective_depth = RetrievalDepth(
                    depth=effective_depth.depth, k=effective_depth.k,
                    skip_bm25=effective_depth.skip_bm25, skip_kg=effective_depth.skip_kg,
                    skip_decompose=effective_depth.skip_decompose, skip_hyde=effective_depth.skip_hyde,
                    skip_metadata_routes=True, skip_rerank=effective_depth.skip_rerank,
                    max_metadata_routes=0,
                )

        rerank_flag = use_rerank if use_rerank is not None else True
        results = _multi_route_search(
            query, collection_name, k,
            cat=cat, use_rerank=rerank_flag,
            terms=terms, depth=effective_depth,
        )
        timing["rrf_ms"] = (time.perf_counter() - t0) * 1000

        # ── 动态去重（与主管线一致）──
        _max_per = 4 if (cat.is_exercise or cat.is_answer) else (3 if (cat.is_comparison or cat.is_long) else 2)
        deduped = dedup_same_section(results, max_per_section=_max_per)
        filtered = [doc for doc, score in deduped]

        # ── Reranker ──
        if rerank_flag and filtered:
            t2 = time.perf_counter()
            reranked = rerank(query, filtered, top_k=k)
            # 双重阈值过滤（与主管线一致），兜底保留 top-2
            from app.rag.retriever import _apply_rerank_threshold
            filtered = _apply_rerank_threshold(reranked, min_keep=2)
            timing["rerank_ms"] = (time.perf_counter() - t2) * 1000
        else:
            filtered = filtered[:k]

        # ── Sentence Window ──
        ws = window_size if window_size is not None else 2
        t3 = time.perf_counter()
        if filtered and collection_name:
            filtered = sentence_window_expand(filtered, collection_name, window_size=ws)
        timing["window_ms"] = (time.perf_counter() - t3) * 1000

        timing["total_ms"] = (time.perf_counter() - start) * 1000
        timing["query_category"] = str(cat)
        timing["retrieval_layer"] = strategy.layer
        timing["route_type"] = strategy.route_type
        return [_doc_to_dict(d) for d in filtered], timing


class CurrentQueryDecomposer:
    """适配器：将 app.rag.query_decomposer 对接到 QueryDecomposerProtocol"""

    @staticmethod
    def _classify(query: str):
        from app.rag.query_classifier import classify_query
        from app.rag.rag_utils import extract_query_terms, normalize_query_text
        normalized = normalize_query_text(query)
        terms = extract_query_terms(normalized)
        return classify_query(query, terms)

    def should_decompose(self, query: str) -> bool:
        from app.rag.query_decomposer import should_decompose as _sd
        return _sd(query, self._classify(query))

    def decompose(self, query: str) -> list[str]:
        from app.rag.query_decomposer import decompose_sync
        return decompose_sync(query, cat=self._classify(query))

    def stats(self) -> dict[str, Any]:
        from app.rag.metrics import get_decompose_stats
        return get_decompose_stats()


class CurrentEmbedding:
    """适配器：将 app.rag.embeddings 对接到 EmbeddingProtocol"""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        from app.rag.embeddings import get_embeddings
        emb = get_embeddings()
        return emb.embed_documents(texts)

    @property
    def langchain_embeddings(self) -> Any:
        from app.rag.embeddings import get_embeddings
        return get_embeddings()


# ════════════════════════════════════════════════════════
#  工具函数
# ════════════════════════════════════════════════════════

def _doc_to_dict(doc: Document) -> dict[str, Any]:
    """将 LangChain Document 转为通用 dict"""
    return {
        "content": doc.page_content,
        "metadata": dict(doc.metadata) if doc.metadata else {},
    }


# ════════════════════════════════════════════════════════
#  全局实例（懒加载）
# ════════════════════════════════════════════════════════

_retriever: RetrieverProtocol | None = None
_diagnostic_retriever: DiagnosticRetrieverProtocol | None = None
_decomposer: QueryDecomposerProtocol | None = None
_embedding: EmbeddingProtocol | None = None


def get_retriever() -> RetrieverProtocol:
    global _retriever
    if _retriever is None:
        _retriever = CurrentRAGRetriever()
    return _retriever


def get_diagnostic_retriever() -> DiagnosticRetrieverProtocol:
    global _diagnostic_retriever
    if _diagnostic_retriever is None:
        _diagnostic_retriever = CurrentDiagnosticRetriever()
    return _diagnostic_retriever


def get_decomposer() -> QueryDecomposerProtocol:
    global _decomposer
    if _decomposer is None:
        _decomposer = CurrentQueryDecomposer()
    return _decomposer


def get_eval_embedding() -> EmbeddingProtocol:
    global _embedding
    if _embedding is None:
        _embedding = CurrentEmbedding()
    return _embedding


