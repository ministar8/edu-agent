import logging

from langchain_core.tools import tool

from app.config import settings
from app.agents.kg_tools import aquery_knowledge_graph
from app.agents.prompts import PATH_AGENT_SYSTEM_PROMPT as PATH_AGENT_PROMPT
from app.agents.agent_factory import ReactAgentSpec, create_react_tool_agent

logger = logging.getLogger(__name__)


@tool("search_learning_path")
async def asearch_learning_path(query: str) -> str:
    """异步搜索学习路径模板和教材内容（多路召回+BM25+KG扩展+Reranker）。"""
    try:
        from app.rag.retriever import aretrieve_evidence_with_retry
        fused, verification = await aretrieve_evidence_with_retry(
            query=query,
            k=4,
            use_rerank=True,
            max_retries=1,
            use_llm_verify=False,
        )
        if not fused.final_context:
            return "学习路径库中暂无相关内容。"
        result = fused.final_context
        if verification.verdict.value != "pass" and verification.reasons:
            result += f"\n\nEvidence quality: {verification.verdict.value}; {'; '.join(verification.reasons[:2])}"
        return result
    except Exception as e:
        logger.error("Learning path search failed: %s", e, exc_info=True)
        return f"学习路径检索失败: {e}"


def create_path_agent():
    """创建学习路径推荐Agent"""
    return create_react_tool_agent(
        ReactAgentSpec(
            name="path_agent",
            prompt=PATH_AGENT_PROMPT,
            tools=[
                aquery_knowledge_graph,
                asearch_learning_path,
            ],
            temperature=settings.TEMP_PRECISE,
        )
    )
