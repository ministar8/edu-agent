from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class VisualizationService:
    def get_rag_process_demo(self, *, query: str, collection: str = "data_structure") -> dict:
        from app.rag.context import kg_context_supplement
        from app.rag.fusion import fuse_documents
        from app.rag.trace import retrieve_documents_with_trace

        try:
            docs, trace = retrieve_documents_with_trace(query=query, collection_name=collection, k=5, use_rerank=True)

            kg_supplement = ""
            try:
                kg_supplement = kg_context_supplement(query)
            except Exception as exc:
                logger.debug("KG supplement skipped for visualization: %s", exc)

            retrieval_depth = trace.get("policy", {}).get("retrieval_depth", "standard")
            fused = fuse_documents(docs, query="", kg_supplement=kg_supplement, depth=retrieval_depth)
            result_text = fused.final_context
            steps = build_rag_process_steps(query=query, docs=docs, trace=trace, result_text=result_text)

            return {
                "steps": steps,
                "trace": trace,
                "result_text": result_text[:800] if result_text else "",
            }
        except Exception as exc:
            logger.error("RAG process visualization failed: %s", exc, exc_info=True)
            return build_rag_process_error(query, exc)

    def get_hierarchical_knowledge_graph(self, *, category: str | None = None, levels: int = 3) -> dict:
        from app.rag.knowledge_graph import get_kg_manager

        return get_kg_manager().get_hierarchical_graph_data(category=category, levels=levels)


def build_rag_process_error(query: str, exc: Exception) -> dict:
    return {
        "steps": [
            {"step": 1, "name": "原始查询", "data": query, "type": "input"},
            {"step": 2, "name": "错误", "data": str(exc), "type": "error"},
        ],
        "trace": {},
        "result_text": "",
    }


def build_rag_process_steps(*, query: str, docs: list, trace: dict, result_text: str) -> list[dict]:
    source_nodes = []
    for doc in docs[:5]:
        source_nodes.append({
            "content": doc.page_content[:200] if doc.page_content else "",
            "score": float(doc.metadata.get("rerank_score", 0.0)),
            "metadata": doc.metadata,
        })

    route_summary = trace.get("route_summary", {})
    kg_trace = trace.get("kg", {})
    hyde_trace = trace.get("hyde", {})
    counts = trace.get("counts", {})

    return [
        {
            "step": 1,
            "name": "原始查询",
            "data": query,
            "type": "input",
        },
        {
            "step": 2,
            "name": "多路召回+BM25+KG扩展",
            "data": (
                f"实际搜索集合: {', '.join(trace['collections'])}\n"
                f"粗召回K: {trace['policy']['coarse_k']}；阈值: {trace['policy']['threshold']:.2f}\n"
                f"路由数: {len(trace['routes'])}；原始合并结果: {counts.get('raw', 0)} 条\n"
                f"各路命中: {route_summary.get('hits_by_route', {})}"
            ),
            "type": "search",
        },
        {
            "step": 3,
            "name": "Reranker重排+层级展开",
            "data": source_nodes[:5],
            "type": "results",
        },
        {
            "step": 4,
            "name": "上下文构建",
            "data": (
                f"阶段统计: 去重后 {counts.get('after_dedup', 0)} 条 → "
                f"阈值过滤后 {counts.get('after_threshold', 0)} 条 → "
                f"重排后 {counts.get('after_rerank', 0)} 条 → "
                f"HyDE后 {counts.get('after_hyde', counts.get('after_rerank', 0))} 条 → "
                f"层级展开后 {counts.get('after_window', counts.get('after_expand', 0))} 条 → "
                f"最终上下文 {counts.get('final', 0)} 条\n"
                f"HyDE: triggered={hyde_trace.get('triggered', False)}, added={hyde_trace.get('added_count', 0)}\n"
                f"KG: used={kg_trace.get('used', False)}, nodes={kg_trace.get('nodes_count', 0)}, "
                f"edges={kg_trace.get('edges_count', 0)}, paths={kg_trace.get('paths_count', 0)}\n\n"
                f"{result_text[:500] if result_text else '未构建上下文：当前集合中没有检索到相关内容，请确认知识库已入库，或切换到匹配的408科目集合。'}"
            ),
            "type": "output",
        },
    ]
