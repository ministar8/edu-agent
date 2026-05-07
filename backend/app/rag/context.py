"""上下文构建模块

职责：KG 关联知识补充、RAG 上下文拼接
"""

from __future__ import annotations

import logging

from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def kg_context_supplement(query: str, max_related: int = 5) -> str:
    """从知识图谱获取关联知识点，构建上下文补充段落

    查询 KG 获取 query 对应节点的学习路径和前置知识，
    格式化为结构化文本附加到 RAG context 末尾。

    防泛化约束：
    - 仅取直接相邻节点（1跳），不做深度遍历
    - 最多 max_related 个关联知识点
    - 每个知识点描述截断 100 字
    - KG 查询失败时静默降级
    """
    try:
        from app.rag.knowledge_graph import get_kg_manager
        kg_manager = get_kg_manager()
        resolved = kg_manager.resolve_topic(query)
        if not resolved:
            return ""

        parts: list[str] = []
        count = 0

        # 前置知识
        prerequisites = kg_manager.get_prerequisites(resolved)
        if prerequisites:
            names = [p.get("name", "") for p in prerequisites if p.get("name")]
            if names:
                parts.append(f"前置知识: {', '.join(names[:max_related])}")
                count += len(names[:max_related])

        # 后续知识
        next_topics = kg_manager.get_next_topics(resolved)
        if next_topics and count < max_related:
            names = [n.get("name", "") for n in next_topics if n.get("name")]
            remaining = max_related - count
            if names:
                parts.append(f"后续知识: {', '.join(names[:remaining])}")
                count += len(names[:remaining])

        # 学习路径
        if count < max_related:
            learning_path = kg_manager.get_learning_path(resolved)
            if learning_path:
                path_names = [step.get("name", "") for step in learning_path if step.get("name")]
                remaining = max_related - count
                if path_names:
                    parts.append(f"学习路径: {' → '.join(path_names[:remaining])}")

        if not parts:
            return ""

        return "【知识图谱关联信息】\n" + "\n".join(parts)
    except Exception as e:
        logger.debug("KG context supplement failed (non-fatal): %s", e)
        return ""


def build_rag_context(docs: list[Document], query: str = "",
                      kg_supplement: str = "") -> str:
    """将检索结果构建为上下文（含层级路径标注 + KG 关联知识补充）

    Args:
        docs: 检索结果文档列表
        query: 原始查询（仅用于日志）
        kg_supplement: KG 关联知识补充文本（由调用方预取传入，避免重复查询）
    """
    context_parts = []
    for i, doc in enumerate(docs, 1):
        source = doc.metadata.get("source_file", "未知来源")
        rerank_score = doc.metadata.get("rerank_score")
        score_info = f" (相关度: {rerank_score:.2f})" if rerank_score else ""
        # 层级路径标注
        section_path = doc.metadata.get("section.path") or doc.metadata.get("heading_path") or ""
        path_info = f" [{section_path}]" if section_path else ""
        # 展开来源标注
        expanded_from = doc.metadata.get("_expanded_from")
        expand_info = " (展开)" if expanded_from else ""
        # 缺口填补标注
        filled_gap = doc.metadata.get("_filled_gap")
        fill_info = " (补齐)" if filled_gap else ""
        context_parts.append(
            f"[来源{i}: {source}{score_info}{path_info}{expand_info}{fill_info}]\n{doc.page_content}"
        )

    # KG 关联知识补充：由调用方预取传入，不再内部查询
    if kg_supplement:
        context_parts.append(kg_supplement)

    return "\n\n".join(context_parts)
