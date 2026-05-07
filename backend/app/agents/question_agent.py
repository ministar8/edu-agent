import asyncio
import logging
import re

from langchain_core.documents import Document
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.rag.retriever import get_llm, build_rag_context, _kg_context_supplement, _raw_search
from app.agents.kg_tools import aquery_knowledge_graph

logger = logging.getLogger(__name__)


def _subject_collection(query: str) -> str:
    if "数据结构" in query:
        return "data_structure"
    if "组成原理" in query or "计算机组成" in query:
        return "computer_organization"
    if "操作系统" in query:
        return "operating_system"
    if "计算机网络" in query or "网络" in query:
        return "computer_network"
    return ""


def _extract_topic(query: str) -> str:
    match = re.search(r"「([^」]+)」", query)
    if match:
        return match.group(1).strip()
    return query.strip()


def _dedupe_docs(docs: list[Document]) -> list[Document]:
    """按 content_hash 或 source_file+content 去重"""
    deduped = []
    seen: set[str] = set()
    for doc in docs:
        key = doc.metadata.get("content_hash") or f"{doc.metadata.get('source_file', '')}:{doc.page_content[:120]}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(doc)
    return deduped


def _lightweight_retrieve(query: str, collection_name: str, k: int) -> list[Document]:
    """轻量检索：直接调底层向量搜索，不走完整 RAG 管线"""
    results = _raw_search(query, collection_name, k, route_name="question_lightweight")
    return [doc for doc, _score in results[:k]]


@tool("search_question_templates")
async def asearch_question_templates(query: str) -> str:
    """异步搜索题库和教材中与指定知识点相关的题目模板、例题和知识点内容（多路召回+BM25+Reranker）。"""
    try:
        search_query = f"{query} 练习题 题目 模板 例题"
        subject = _subject_collection(query)
        docs = []
        if subject:
            docs.extend(_lightweight_retrieve(query, subject, k=3))

        if len(docs) < 2:
            docs.extend(_lightweight_retrieve(search_query, "questions", k=2))

        docs = _dedupe_docs(docs)
        try:
            kg_supplement = await asyncio.wait_for(asyncio.to_thread(_kg_context_supplement, query), timeout=3)
        except Exception:
            logger.debug("KG supplement timeout or failed for query=%s", query[:30])
            kg_supplement = ""
        if not docs:
            return "题库和教材中暂无相关内容。"
        context = build_rag_context(docs, query=query, kg_supplement=kg_supplement or "")
        max_context_chars = 4500
        if len(context) > max_context_chars:
            context = context[:max_context_chars] + "\n\n[上下文已截断：仅保留最相关的题库模板与知识依据。]"
        return context
    except Exception as e:
        logger.error("Question template search failed: %s", e, exc_info=True)
        return f"题库检索失败: {e}"


async def generate_questions_with_retrieval(prompt: str) -> str:
    retrieval_query = _extract_topic(prompt)
    retrieval_context = await asearch_question_templates.ainvoke({"query": retrieval_query})
    if (
        not retrieval_context
        or "暂无相关内容" in retrieval_context
        or "题库检索失败" in retrieval_context
    ):
        return retrieval_context or "题库和教材中暂无相关内容。"

    llm = get_llm()
    generation_prompt = "\n\n".join([
        QUESTION_GENERATION_PROMPT,
        "【已检索到的题库模板与知识依据】",
        retrieval_context,
        "【用户出题需求】",
        prompt,
        "请严格基于已检索依据生成题目；题干和解析必须简洁；每题解析不超过80字；不要兜底编造；不要输出寒暄、背景介绍或 Markdown 加粗符号。",
    ])
    response = await llm.ainvoke(generation_prompt)
    raw = response.content if hasattr(response, "content") else str(response)
    return raw.strip()


QUESTION_AGENT_PROMPT = """你是一个练习题生成Agent，任务是基于题库模板与知识库内容进行检索增强生成。

【工具使用规则】
1. 只要用户要求出题、练习、测试、刷题，必须先调用检索工具。
2. 检索工具选择策略：
   - 查找题目模板与知识依据 → search_question_templates（统一检索管线会根据查询自动路由到相关集合）
3. 若检索结果为空或工具返回失败，不要生成题目；必须直接说明无法基于当前知识库生成。
4. 知识图谱辅助出题：当需要出综合题或关联题时，可先调用 query_knowledge_graph 查询知识点的前置/后续关系。
5. 若检索结果不足，要明确说明题库模板不足，不要生成保守兜底题目。
6. 不要编造"来自题库第几套题"之类不存在的信息。
7. 生成内容应与用户主题高度相关，不要跑题。
8. 只输出题目结果，不要寒暄，不要自我介绍。

【出题要求】
1. 支持选择题、填空题、简答题、综合应用题。
2. 默认覆盖基础到中等难度；若用户指定难度，则优先遵循用户要求。
3. 题目应避免与检索模板完全重复，但可以复用考点结构。
4. 每道题都必须给出标准答案与简明解析。
5. 综合应用题需给出完整的分析过程与关键步骤。

【输出格式】
每道题按以下结构输出：
题目X：
类型：
难度：
题干：
标准答案：
解析：

若有多道题，请逐题编号。
"""


def create_question_agent():
    """创建题目生成Agent（ReAct 模式，供 Supervisor 路由使用）"""
    llm = get_llm()
    agent = create_react_agent(
        model=llm,
        tools=[
            asearch_question_templates,
            aquery_knowledge_graph,
        ],
        prompt=QUESTION_AGENT_PROMPT,
    )
    return agent


QUESTION_GENERATION_PROMPT = """你是一个练习题生成助手，任务是基于已检索到的题库模板与知识库内容生成练习题。

【生成规则】
1. 严格基于已检索依据生成题目，不要兜底编造。
2. 若检索依据不足，直接说明无法生成，不要生成保守兜底题目。
3. 不要编造"来自题库第几套题"之类不存在的信息。
4. 生成内容应与用户主题高度相关，不要跑题。
5. 只输出题目结果，不要寒暄，不要自我介绍。

【出题要求】
1. 支持选择题、填空题、简答题、综合应用题。
2. 默认覆盖基础到中等难度；若用户指定难度，则优先遵循用户要求。
3. 题目应避免与检索模板完全重复，但可以复用考点结构。
4. 每道题都必须给出标准答案与简明解析。
5. 综合应用题需给出完整的分析过程与关键步骤。

【输出格式】
每道题按以下结构输出：
题目X：
类型：
难度：
题干：
标准答案：
解析：

若有多道题，请逐题编号。
"""
