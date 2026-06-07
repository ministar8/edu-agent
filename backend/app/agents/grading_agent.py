import logging

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.rag.retriever import aretrieve_evidence_with_retry
from app.rag.rag_utils import get_llm
from app.config import settings
from app.rag.schemas import GradingResult
from app.agents.kg_tools import aquery_knowledge_graph
from app.agents.prompts import GRADING_AGENT_SYSTEM_PROMPT as GRADING_AGENT_PROMPT

logger = logging.getLogger(__name__)


@tool("search_standard_answer")
async def asearch_standard_answer(query: str) -> str:
    """搜索教材知识库中的标准答案和评分依据（多路召回+BM25+KG扩展+Reranker）。当需要批改学生答案时使用此工具。"""
    try:
        fused, verification = await aretrieve_evidence_with_retry(
            query=query,
            k=5,
            use_rerank=True,
            max_retries=1,
            use_llm_verify=False,
        )
        if not fused.final_context:
            return "知识库中暂无相关内容。"
        result = fused.final_context
        if verification.verdict.value != "pass" and verification.reasons:
            result += f"\n\nEvidence quality: {verification.verdict.value}; {'; '.join(verification.reasons[:2])}"
        return result
    except Exception as e:
        logger.error("Standard answer search failed: %s", e, exc_info=True)
        return f"标准答案检索失败: {e}"



async def grade_single_question(
    stem: str,
    standard_answer: str,
    user_answer: str,
) -> dict:
    """单题批改（非 ReAct）：检索知识库 + LLM 判卷，返回 {score, feedback, is_wrong}

    不走 ReAct 循环，直接检索 → 生成 → 解析，延迟 < 2s。"""

    # 1. 构建检索查询：题干关键词 + 标准答案前段
    search_query = f"{stem[:200]} {standard_answer[:100]}" if standard_answer else stem[:200]
    try:
        fused, verification = await aretrieve_evidence_with_retry(
            query=search_query,
            k=5,
            use_rerank=True,
            max_retries=1,
            use_llm_verify=False,
        )
        context = fused.final_context if fused.final_context else ""
        if not context:
            context = "（知识库中未检索到相关依据）"
        elif verification.verdict.value != "pass" and verification.reasons:
            context += f"\n\nEvidence quality: {verification.verdict.value}; {'; '.join(verification.reasons[:2])}"
    except Exception:
        context = "（检索失败，请基于题干和标准答案判卷）"

    # 2. 结构化批改（Function Calling / JSON Schema，替代正则解析）
    grade_prompt = f"""请基于知识库依据和标准答案，批改以下408考研题目。

知识库依据：
{context[:2500]}

题干：{stem}
标准答案：{standard_answer or "（无标准答案，请基于知识库依据判断）"}
学生答案：{user_answer}

请以JSON格式输出。
"""

    llm = get_llm(temperature=settings.TEMP_PRECISE)
    structured_llm = llm.with_structured_output(GradingResult)
    try:
        result = await structured_llm.ainvoke(grade_prompt)
        return {"score": float(result.score), "feedback": result.feedback, "is_wrong": result.is_wrong}
    except Exception as e:
        logger.warning("Structured grading failed, fallback to regex: %s", e)
        # 兜底：用原始 LLM 调用 + 正则解析
        import re
        response = await llm.ainvoke(grade_prompt)
        text = response.content if hasattr(response, "content") else str(response)
        score_match = re.search(r"[0-9]{1,3}", text)
        score = float(score_match.group(0)) if score_match else 50.0
        score = max(0.0, min(100.0, score))
        feedback = text[:500] if not score_match else text
        return {"score": score, "feedback": feedback, "is_wrong": score < 60}


def create_grading_agent():
    """创建批改评估Agent"""
    llm = get_llm(temperature=settings.TEMP_PRECISE, use_fast=True)  # ReAct 工具选择用 fast
    agent = create_react_agent(
        model=llm,
        tools=[
            asearch_standard_answer,
            aquery_knowledge_graph,
        ],
        prompt=GRADING_AGENT_PROMPT,
    )
    return agent
