from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.dependencies import get_visualization_service
from app.services.visualization_service import VisualizationService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/rag-process")
async def get_rag_process_demo(
    query: str,
    collection: str = "data_structure",
    service: VisualizationService = Depends(get_visualization_service),
):
    """RAG检索过程可视化数据（统一检索管线）— 返回完整 trace 供前端增强可视化"""
    return service.get_rag_process_demo(query=query, collection=collection)


@router.get("/knowledge-graph/hierarchical")
async def get_hierarchical_knowledge_graph(
    category: str | None = None,
    levels: int = 3,
    service: VisualizationService = Depends(get_visualization_service),
):
    """获取层级聚合的知识图谱可视化数据（学科→章→知识点）
    levels=2: 仅展示 root + level1（章节级）
    levels=3: 展示全部三级（默认）
    """
    try:
        return service.get_hierarchical_knowledge_graph(category=category, levels=levels)
    except Exception as e:
        logger.error("Hierarchical knowledge graph fetch failed: %s", e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"知识图谱查询失败: {e}")