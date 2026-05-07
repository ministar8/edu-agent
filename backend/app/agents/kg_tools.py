"""知识图谱共享工具定义

供 knowledge_agent / question_agent / grading_agent / path_agent 复用，
避免在多个 Agent 文件中重复定义相同的 @tool 函数。
"""

import asyncio
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool("query_knowledge_graph")
async def aquery_knowledge_graph(topic: str) -> str:
    """异步查询知识图谱，获取知识点的前置知识和后续知识关系。"""
    try:
        from app.rag.knowledge_graph import get_kg_manager
        kg_manager = get_kg_manager()
        prerequisites, next_topics, learning_paths = await asyncio.gather(
            asyncio.to_thread(kg_manager.get_prerequisites, topic),
            asyncio.to_thread(kg_manager.get_next_topics, topic),
            asyncio.to_thread(kg_manager.get_learning_path, topic),
        )

        result_parts = []
        if prerequisites:
            names = [p["name"] for p in prerequisites]
            result_parts.append(f"前置知识: {', '.join(names)}")
        if next_topics:
            names = [n["name"] for n in next_topics]
            result_parts.append(f"后续知识: {', '.join(names)}")
        if learning_paths:
            for i, path in enumerate(learning_paths):
                steps = " → ".join([n["name"] for n in path])
                result_parts.append(f"学习路径{i+1}: {steps}")

        if not result_parts:
            return f"知识图谱中暂无 '{topic}' 的相关信息。"
        return "\n".join(result_parts)
    except Exception as e:
        logger.error("Knowledge graph query failed for topic=%s: %s", topic, e, exc_info=True)
        return f"知识图谱查询失败（服务不可用）: {e}"
