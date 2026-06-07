"""上下文构建模块

职责：KG 关联知识补充
"""

from __future__ import annotations

import logging


logger = logging.getLogger(__name__)


def kg_context_supplement(query: str, max_related: int = 5, category: str = "") -> str:
    """从知识图谱获取关联知识点，构建上下文补充段落

    查询 KG 获取 query 对应节点的学习路径和前置知识，
    格式化为结构化文本附加到 RAG context 末尾。

    拓扑保留：输出 前置->当前->后续 的有向链路，而非扁平名称列表，
    让 LLM 能理解知识点之间的依赖/递进关系。

    防泛化约束：
    - 仅取直接相邻节点（1跳），不做深度遍历
    - 最多 max_related 个关联知识点
    - 每个知识点描述截断 100 字
    - KG 查询失败时静默降级

    Args:
        query: 查询文本
        max_related: 最大关联知识点数
        category: KG 分类限定（用于跨学科消歧，空=不限）
    """
    try:
        from app.rag.knowledge_graph import get_kg_manager
        kg_manager = get_kg_manager()
        resolved = kg_manager.resolve_topic(query, category=category)
        if not resolved:
            return ""

        parts: list[str] = []
        count = 0

        # 当前知识点名称
        current_name = resolved

        # 前置知识（保留依赖关系：前置 → 当前）
        prerequisites = kg_manager.get_prerequisites(resolved)
        if prerequisites:
            pre_names = [p.get("name", "") for p in prerequisites if p.get("name")]
            if pre_names:
                # 用箭头表达依赖方向
                chain = " → ".join(pre_names[:max_related]) + f" → 【{current_name}】"
                parts.append(f"前置知识链: {chain}")
                count += len(pre_names[:max_related])

        # 后续知识（保留递进关系：当前 → 后续）
        next_topics = kg_manager.get_next_topics(resolved)
        if next_topics and count < max_related:
            next_names = [n.get("name", "") for n in next_topics if n.get("name")]
            remaining = max_related - count
            if next_names:
                chain = f"【{current_name}】 → " + " → ".join(next_names[:remaining])
                parts.append(f"后续知识链: {chain}")
                count += len(next_names[:remaining])

        # 学习路径（保留完整路径拓扑）
        if count < max_related:
            learning_path = kg_manager.get_learning_path(resolved)
            if learning_path:
                first_path = learning_path[0] if isinstance(learning_path[0], list) else learning_path
                path_names = [step.get("name", "") for step in first_path if step.get("name")]
                remaining = max_related - count
                if path_names:
                    parts.append(f"学习路径: {' → '.join(path_names[:remaining + 1])}")

        if not parts:
            return ""

        return "【知识图谱关联信息】\n" + "\n".join(parts)
    except Exception as e:
        logger.debug("KG context supplement failed (non-fatal): %s", e)
        return ""
