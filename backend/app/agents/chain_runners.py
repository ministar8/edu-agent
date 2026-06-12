import asyncio
import logging
import re as _re
import time
from typing import Protocol

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agents.answer_governance import govern_answer
from app.agents.memory_manager import extract_current_query
from app.agents.prompts import FAST_PATH_PROMPT_MAP, FAST_PATH_USER_TEMPLATE
from app.agents.reflection_agent import areflect, apply_reflection_to_answer
from app.agents.retrieval_guard import run_retrieval_guard
from app.agents.trace_utils import extract_sources_from_text
from app.config import settings
from app.rag.query_classifier import DEEP_DEPTH, STANDARD_DEPTH, TEXT_ONLY_DEPTH
from app.rag.rag_utils import extract_query_terms, get_llm, normalize_query_text

logger = logging.getLogger(__name__)


class RetrievedDocument(Protocol):
    metadata: dict[str, object]
    page_content: str


def format_docs(docs: list[RetrievedDocument], max_docs: int = 5, content_limit: int = 800) -> str:
    parts = []
    for doc in docs[:max_docs]:
        src = doc.metadata.get("source_file") or doc.metadata.get("_collection", "")
        parts.append(f"[来源:{src}]\n{doc.page_content[:content_limit]}")
    return "\n\n".join(parts) if parts else ""


async def quick_retrieve(
    query: str,
    *,
    k: int = 5,
    use_rerank: bool = True,
    depth: object,
    timeout: float | None = None,
) -> str:
    from app.rag.query_classifier import classify_query
    from app.rag.retriever import aretrieve_documents

    terms = extract_query_terms(normalize_query_text(query))
    cat = classify_query(query, terms)
    try:
        docs = await asyncio.wait_for(
            aretrieve_documents(query, k=k, use_rerank=use_rerank, depth=depth, cat=cat),
            timeout=timeout or settings.PRE_RETRIEVAL_TIMEOUT,
        )
        if docs:
            return format_docs(docs, max_docs=k)
    except Exception as e:
        logger.warning("quick_retrieve failed: %s", e)
    return ""


def extract_retrieval_query(current_query: str, agent_name: str) -> str:
    if agent_name == "grading_agent":
        topic_match = _re.split(r"学生答案|我的答案|我答的", current_query)
        return topic_match[0].replace("题目：", "").replace("题目:", "").strip()[:200]
    if agent_name == "path_agent":
        subject_kw = _re.sub(r"应该怎么学|怎么学|怎么复习|学习路线|学习路径|学习建议|学习规划|如何学", "", current_query).strip()
        return f"{subject_kw} 学习路线 重点章节" if subject_kw else current_query
    if agent_name == "question_agent":
        match = _re.search(r"关于(.+?)(?:的选择题|的填空题|的简答题|的综合题|的题)", current_query)
        if match:
            return match.group(1).strip()
        match = _re.search(r"涉及(.+?)(?:的|题)", current_query)
        if match:
            return match.group(1).strip()
        return _re.sub(r"出一道|出几道|给我出|来几道|综合题|选择题|填空题|简答题", "", current_query).strip()
    return current_query


def get_agent_prompt(agent_name: str) -> str:
    return FAST_PATH_PROMPT_MAP.get(agent_name, FAST_PATH_PROMPT_MAP["knowledge_agent"])


async def llm_generate(
    system_prompt: str,
    evidence: str,
    query: str,
    *,
    use_fast: bool = False,
    timeout: float | None = None,
) -> str | None:
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=FAST_PATH_USER_TEMPLATE.format(evidence=evidence, query=query)),
    ]
    llm = get_llm(streaming=False, temperature=settings.TEMP_PRECISE, use_fast=use_fast)
    try:
        result = await asyncio.wait_for(llm.ainvoke(messages), timeout=timeout or settings.AGENT_PRIMARY_TIMEOUT)
        answer = result.content if hasattr(result, "content") else str(result)
        return answer if answer else None
    except Exception as e:
        logger.warning("llm_generate failed: %s", e)
        return None


def build_synthetic_agent_step(
    agent_name: str,
    tool_name: str,
    query: str,
    output: object,
    sources: list[str] | None = None,
) -> dict:
    output_text = str(output or "")
    return {
        "agent_name": agent_name,
        "action": "tool_call",
        "tool_name": tool_name,
        "input_data": str(query or "")[:600],
        "output_data": output_text[:1200],
        "sources": sources if sources is not None else extract_sources_from_text(output_text),
        "timestamp": time.time(),
    }


async def apply_governance_and_reflection(
    answer: str,
    tool_outputs: list[str],
    result_messages: list,
    agent_steps: list[dict],
    name: str,
    current_query: str,
    start_time: float,
    retry_a: int = 0,
    retry_b: int = 0,
    rag_fallback: bool = False,
    retrieval_layer: str = "",
    route_type: str = "",
) -> dict:
    gov = govern_answer(answer, name, tool_outputs=tool_outputs)
    if not agent_steps and tool_outputs:
        agent_steps = [
            build_synthetic_agent_step(
                name,
                "knowledge_search" if name == "knowledge_agent" else "retrieval",
                current_query,
                "\n\n".join(tool_outputs),
            )
        ]

    evidence_for_reflection = " ".join(tool_outputs) if tool_outputs else ""
    try:
        reflection = await asyncio.wait_for(
            areflect(
                answer=gov.answer,
                evidence_text=evidence_for_reflection,
                query=current_query,
                agent_name=name,
                use_llm=True,
            ),
            timeout=settings.AGENT_RETRY_TIMEOUT,
        )
    except Exception as e:
        logger.warning("Agent %s reflection skipped or downgraded: %s", name, e)
        reflection = await areflect(
            answer=gov.answer,
            evidence_text=evidence_for_reflection,
            query=current_query,
            agent_name=name,
            use_llm=False,
        )
    if reflection.suggestion:
        gov.answer = apply_reflection_to_answer(gov.answer, reflection)

    guard = run_retrieval_guard(tool_outputs, name)
    total_retries = retry_a + retry_b
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    logger.info(
        "Agent finished agent=%s elapsed_ms=%.2f gov_confidence=%s gov_flags=%s guard=%s reflection=%s retries=%d(A=%d,B=%d) rag=%s",
        name, elapsed_ms, gov.confidence, gov.flags, guard.has_sufficient_evidence,
        reflection.confidence, total_retries, retry_a, retry_b, rag_fallback,
    )
    return {
        "messages": result_messages,
        "final_answer": gov.answer,
        "agent_steps": agent_steps,
        "governance": {
            "confidence": gov.confidence,
            "has_source": gov.has_source,
            "passed": gov.passed,
            "flags": gov.flags,
            "reflection_confidence": reflection.confidence,
            "reflection_issues": reflection.issues,
        },
        "guard_result": {
            "has_sufficient_evidence": guard.has_sufficient_evidence,
            "warnings": guard.warnings,
        },
        "retrieval_layer": retrieval_layer,
        "route_type": route_type,
    }


async def _generate_with_context(
    name: str,
    current_query: str,
    evidence_context: str,
    *,
    use_fast: bool = False,
) -> tuple[str, list[str], list]:
    answer = await llm_generate(get_agent_prompt(name), evidence_context, current_query, use_fast=use_fast)
    if not answer:
        return "", [evidence_context], []
    return answer, [evidence_context], [AIMessage(content=answer)]


def _no_evidence_result() -> tuple[str, list[str], list]:
    answer = "未在知识库中找到相关内容。请换一种问法，或明确学科与知识点。"
    return answer, [], [AIMessage(content=answer)]


def run_l1_agent(_agent, name: str):
    async def wrapped(state: dict, config: RunnableConfig | None = None) -> dict:
        start_time = time.perf_counter()
        logger.info("L1 agent execution started agent=%s", name)
        current_query = extract_current_query(state["messages"])

        pre_retrieval_result = state.get("pre_retrieval_result")
        if current_query and not pre_retrieval_result:
            retrieval_query = extract_retrieval_query(current_query, name)
            pre_retrieval_result = await quick_retrieve(retrieval_query, k=5, use_rerank=True, depth=TEXT_ONLY_DEPTH)
            if pre_retrieval_result:
                logger.info("L1 pre-retrieval OK for %s", name)

        tool_outputs: list[str] = []
        result_messages: list = []
        if pre_retrieval_result:
            answer, tool_outputs, result_messages = await _generate_with_context(
                name, current_query, pre_retrieval_result, use_fast=True,
            )
        else:
            answer = ""

        if not answer:
            answer = "未在知识库中找到相关内容。请换一种问法，或明确学科与知识点。"
            result_messages = [AIMessage(content=answer)]

        return await apply_governance_and_reflection(
            answer=answer, tool_outputs=tool_outputs, result_messages=result_messages,
            agent_steps=[], name=name, current_query=current_query, start_time=start_time,
            retrieval_layer=state.get("retrieval_layer", "L1"),
            route_type=state.get("route_type", "l1_fast"),
        )
    wrapped.__name__ = name
    return wrapped


def run_l2_agent(_agent, name: str):
    async def wrapped(state: dict, config: RunnableConfig | None = None) -> dict:
        start_time = time.perf_counter()
        logger.info("L2 agent execution started agent=%s", name)
        current_query = extract_current_query(state["messages"])
        retry_a = 0
        rag_fallback = False

        pre_retrieval_result = state.get("pre_retrieval_result")
        if pre_retrieval_result:
            logger.info("L2 using supervisor pre-retrieval for %s: result_len=%d", name, len(str(pre_retrieval_result)))
        if current_query and not pre_retrieval_result:
            retrieval_query = extract_retrieval_query(current_query, name)
            pre_retrieval_result = await quick_retrieve(retrieval_query, k=5, use_rerank=True, depth=TEXT_ONLY_DEPTH)
            if pre_retrieval_result:
                logger.info("L2 pre-retrieval OK for %s", name)
            if not pre_retrieval_result:
                pre_retrieval_result = await quick_retrieve(
                    retrieval_query, k=5, use_rerank=False, depth=TEXT_ONLY_DEPTH, timeout=15,
                )
                if pre_retrieval_result:
                    logger.info("L2 pre-retrieval fallback OK for %s (no rerank)", name)

        fast_path_answer = ""
        fast_path_tool_outputs: list[str] = []
        if pre_retrieval_result:
            fast_path_answer, fast_path_tool_outputs, result_messages = await _generate_with_context(
                name, current_query, pre_retrieval_result, use_fast=True,
            )
        else:
            result_messages = []

        if fast_path_answer:
            answer = fast_path_answer
            tool_outputs = fast_path_tool_outputs
            agent_steps: list[dict] = []
            logger.info("L2 fast-path: skipping ReAct for %s", name)
        else:
            logger.info("L2 fallback: direct retrieval for %s", name)
            answer = ""
            tool_outputs = []
            result_messages = []
            retrieval_query = extract_retrieval_query(current_query, name)

            retrieval_ctx = await quick_retrieve(retrieval_query, k=5, use_rerank=True, depth=STANDARD_DEPTH)
            if retrieval_ctx:
                tool_outputs = [retrieval_ctx]
            if not retrieval_ctx:
                retrieval_ctx = await quick_retrieve(retrieval_query, k=5, use_rerank=False, depth=STANDARD_DEPTH, timeout=15)
                if retrieval_ctx:
                    tool_outputs = [retrieval_ctx]
                    logger.info("L2 fallback no-rerank OK for %s", name)

            if tool_outputs:
                answer, tool_outputs, result_messages = await _generate_with_context(
                    name, current_query, tool_outputs[0],
                )

            if not answer:
                rag_fallback = True
                answer = "未在知识库中找到相关内容。请换一种问法，或明确学科与知识点。"
                result_messages = [AIMessage(content=answer)]
            agent_steps = []

        return await apply_governance_and_reflection(
            answer=answer, tool_outputs=tool_outputs, result_messages=result_messages,
            agent_steps=agent_steps, name=name, current_query=current_query,
            start_time=start_time, retry_a=retry_a, rag_fallback=rag_fallback,
            retrieval_layer=state.get("retrieval_layer", "L2"),
            route_type=state.get("route_type", "l2_standard"),
        )
    wrapped.__name__ = name
    return wrapped


def run_l3_agent(_agent, name: str):
    async def wrapped(state: dict, config: RunnableConfig | None = None) -> dict:
        start_time = time.perf_counter()
        logger.info("L3 agent execution started agent=%s", name)
        current_query = extract_current_query(state["messages"])

        retry_a = 0
        rag_fallback = False
        tool_outputs: list[str] = []
        answer = ""
        result_messages: list = []
        retrieval_query = extract_retrieval_query(current_query, name)

        evidence_context = await quick_retrieve(retrieval_query, k=8, use_rerank=True, depth=DEEP_DEPTH)
        if evidence_context:
            logger.info("L3 deep retrieval OK for %s", name)
        else:
            logger.warning("L3 deep retrieval empty for %s", name)

        if not evidence_context:
            evidence_context = await quick_retrieve(retrieval_query, k=6, use_rerank=False, depth=STANDARD_DEPTH, timeout=15)
            if evidence_context:
                logger.info("L3 no-rerank fallback OK for %s", name)

        if evidence_context:
            answer, tool_outputs, result_messages = await _generate_with_context(
                name, current_query, evidence_context,
            )

        if not answer:
            rag_fallback = True
            retry_a = 1
            ctx_fb = await quick_retrieve(retrieval_query, k=5, use_rerank=False, depth=STANDARD_DEPTH, timeout=15)
            if ctx_fb:
                tool_outputs = [ctx_fb]
                try:
                    rag_messages = [
                        SystemMessage(content="You are a 408 exam Q&A assistant. Answer based strictly on the given context. Be concise: only answer what is asked, do not expand on unrelated topics. 1-2 sentences for concepts, 2-4 key points for lists."),
                        HumanMessage(content=f"Context:\n{ctx_fb}\n\nQuestion: {current_query}\n\nAnswer directly, accurately and concisely. Only address what the question asks."),
                    ]
                    llm = get_llm(streaming=False, temperature=0.0)
                    rag_result = await asyncio.wait_for(llm.ainvoke(rag_messages), timeout=settings.RAG_FALLBACK_TIMEOUT)
                    rag_answer = rag_result.content if hasattr(rag_result, "content") else str(rag_result)
                    if rag_answer:
                        answer = rag_answer
                        result_messages = [AIMessage(content=rag_answer)]
                except Exception as e:
                    logger.warning("L3 RAG fallback failed for %s: %s", name, e)

        if not answer:
            answer, tool_outputs, result_messages = _no_evidence_result()

        return await apply_governance_and_reflection(
            answer=answer, tool_outputs=tool_outputs, result_messages=result_messages,
            agent_steps=[], name=name, current_query=current_query,
            start_time=start_time, retry_a=retry_a, rag_fallback=rag_fallback,
            retrieval_layer=state.get("retrieval_layer", "L3"),
            route_type=state.get("route_type", "l3_deep"),
        )
    wrapped.__name__ = name
    return wrapped


def wrap_agent(agent, name: str):
    async def wrapped(state: dict, config: RunnableConfig | None = None) -> dict:
        layer = state.get("retrieval_layer", "L2")
        if layer == "L1":
            runner = run_l1_agent(agent, name)
        elif layer == "L3":
            runner = run_l3_agent(agent, name)
        else:
            runner = run_l2_agent(agent, name)
        return await runner(state, config)
    wrapped.__name__ = name
    return wrapped
