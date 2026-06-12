from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/rag-process")
async def get_rag_process_demo(query: str, collection: str = "data_structure"):
    """RAG检索过程可视化数据（统一检索管线）— 返回完整 trace 供前端增强可视化"""
    from app.rag.fusion import fuse_documents
    from app.rag.context import kg_context_supplement as _kg_context_supplement
    from app.rag.trace import retrieve_documents_with_trace

    try:
        docs, trace = retrieve_documents_with_trace(query=query, collection_name=collection, k=5, use_rerank=True)

        # 用 fuse_documents 生成最终上下文（复用 trace 的 docs，避免重复检索）
        kg_supplement = ""
        try:
            kg_supplement = _kg_context_supplement(query)
        except Exception as e:
            logger.debug("KG supplement skipped for visualization: %s", e)
        retrieval_depth = trace.get("policy", {}).get("retrieval_depth", "standard")
        fused = fuse_documents(docs, query="", kg_supplement=kg_supplement, depth=retrieval_depth)
        result_text = fused.final_context

        # 提取源文档节点
        source_nodes = []
        for doc in docs[:5]:
            source_nodes.append({
                "content": doc.page_content[:200] if doc.page_content else "",
                "score": float(doc.metadata.get("rerank_score", 0.0)),
                "metadata": doc.metadata,
            })

        # 兼容旧 steps 格式（逐步展示用）
        route_summary = trace.get("route_summary", {})
        kg_trace = trace.get("kg", {})
        hyde_trace = trace.get("hyde", {})
        counts = trace.get("counts", {})

        steps = [
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

        return {
            "steps": steps,
            "trace": trace,
            "result_text": result_text[:800] if result_text else "",
        }
    except Exception as e:
        logger.error("RAG process visualization failed: %s", e, exc_info=True)
        return {
            "steps": [
                {"step": 1, "name": "原始查询", "data": query, "type": "input"},
                {"step": 2, "name": "错误", "data": str(e), "type": "error"},
            ],
            "trace": {},
            "result_text": "",
        }


@router.get("/knowledge-graph/hierarchical")
async def get_hierarchical_knowledge_graph(category: str | None = None, levels: int = 3):
    """获取层级聚合的知识图谱可视化数据（学科→章→知识点）
    levels=2: 仅展示 root + level1（章节级）
    levels=3: 展示全部三级（默认）
    """
    try:
        from app.rag.knowledge_graph import get_kg_manager
        return get_kg_manager().get_hierarchical_graph_data(category=category, levels=levels)
    except Exception as e:
        logger.error("Hierarchical knowledge graph fetch failed: %s", e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"知识图谱查询失败: {e}")