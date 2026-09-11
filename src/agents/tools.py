"""共享 RAG 检索工具：供 knowledge / question / grading agent 复用。"""

import logging

from langchain_core.tools import tool

from rag.query_classifier import TEXT_ONLY_DEPTH
from rag.retriever import aretrieve_evidence_with_retry

logger = logging.getLogger(__name__)


async def _retrieve_context(query: str, *, depth=None, k: int = 5) -> str:
    """统一的「检索 → 上下文字符串」封装。"""
    try:
        fused, verification = await aretrieve_evidence_with_retry(
            query=query,
            k=k,
            use_rerank=True,
            depth=depth,
            max_retries=1,
            use_llm_verify=False,
        )
    except Exception as e:
        logger.error("Retrieval failed: %s", e, exc_info=True)
        return f"检索失败: {e}"

    if not fused.final_context:
        return "知识库中未找到相关内容。"

    result = fused.final_context
    if fused.sources:
        result += f"\n\n来源: {', '.join(fused.sources[:5])}"
    if verification.verdict.value != "pass" and verification.reasons:
        result += (
            f"\n\n证据质量: {verification.verdict.value}; {'; '.join(verification.reasons[:2])}"
        )
    return result


@tool("knowledge_search")
async def aknowledge_search(query: str) -> str:
    """知识库综合检索（多路召回+BM25+Reranker）。适合大多数概念讲解与原理理解问题。"""
    return await _retrieve_context(query)


@tool("text_search")
async def atext_search(query: str) -> str:
    """纯教材文本检索（更快的浅层检索）。适合快速查询概念定义、原理说明。"""
    return await _retrieve_context(query, depth=TEXT_ONLY_DEPTH)


@tool("search_standard_answer")
async def asearch_standard_answer(query: str) -> str:
    """检索教材知识库中的标准答案与评分依据。批改学生答案时使用。"""
    return await _retrieve_context(query)


@tool("search_question_templates")
async def asearch_question_templates(query: str) -> str:
    """检索题库与教材中与知识点相关的题目模板、例题与知识依据。出题时使用。"""
    return await _retrieve_context(query)


@tool("generate_practice_questions")
async def agenerate_practice_questions(
    topic: str, count: int = 1, difficulty: str = "mixed"
) -> str:
    """按知识点生成练习题（选择/填空/简答/综合）。返回已排版的题目文本。

    与专用出题 API 共用同一结构化生成核心；本工具只负责对话展示。
    difficulty: basic | medium | hard | mixed
    """
    # 延迟导入：question_core 依赖本模块的 asearch_question_templates
    from agents.question_core import agenerate_question_set, format_questions_for_chat

    try:
        result = await agenerate_question_set(topic=topic, count=count, difficulty=difficulty)
    except Exception as e:
        return f"出题失败：{e}"
    return format_questions_for_chat(result)
