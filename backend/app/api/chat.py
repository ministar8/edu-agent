import asyncio
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.api.auth import get_current_user
from app.config import settings
from app.agents.trace_utils import collect_sources_from_steps
from app.core.dependencies import get_chat_message_service
from app.db import User
from app.schemas import ChatRequest, ChatResponse, ConversationDetail, ConversationItem
from app.services.chat_message_service import ChatMessageService
from app.services.chat_metrics_service import emit_chat_baseline_metric as _emit_chat_baseline_metric
from app.services.chat_metrics_service import make_metric_emitter as _make_metric_emitter
from app.services.chat_stream_helpers import append_source_line_if_missing as _append_source_line_if_missing
from app.services.chat_stream_helpers import build_governance_from_agent as _build_governance_from_agent
from app.services.chat_stream_helpers import build_timeout_governance as _build_timeout_governance
from app.services.chat_stream_helpers import chunk_text as _chunk_text
from app.services.chat_stream_helpers import deadline_remaining as _deadline_remaining
from app.services.chat_stream_helpers import sse as _sse
from app.services.chat_tracking_service import ChatTrackingService
from app.rag.feedback import log_feedback

logger = logging.getLogger(__name__)
router = APIRouter()


async def _maybe_summarize_conversation(conversation_id: int) -> None:
    """检查并触发增量合并摘要（后台任务）

    每 12 条消息触发一次：取已有 summary + 最早 6 轮（12条）→ LLM → 更新 summary。
    """
    await ChatMessageService.summarize_with_managed_session(conversation_id)


def _build_input_messages(
    service: ChatMessageService,
    user_message: str,
    *,
    conv_id: int,
    conv_summary: str,
    leaf_message_id: int | None = None,
) -> list:
    return service.build_input_messages(
        user_message=user_message,
        conversation_id=conv_id,
        conversation_summary=conv_summary,
        leaf_message_id=leaf_message_id,
    )


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    service: ChatMessageService = Depends(get_chat_message_service),
):
    """与多Agent系统对话（非流式）"""
    base_thread = request.thread_id or str(uuid.uuid4())
    thread_id = f"{current_user.id}:{base_thread}"
    start_time = time.perf_counter()
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 25,
    }
    metric_answer = ""
    metric_agent = "unknown"
    metric_sources: list[str] = []
    metric_steps: list[dict] = []
    metric_status = "ok"
    metric_error = ""
    metric_retrieval_layer = ""
    metric_route_type = ""

    conv = service.ensure_conversation(current_user.id, base_thread, request.message)
    conv_id = conv.id
    conv_summary = conv.summary or ""
    parent_msg_id = request.parent_message_id
    leaf_message_id: int | None = parent_msg_id
    user_msg = service.save_message(conv_id, "user", request.message, parent_id=parent_msg_id)
    input_messages = _build_input_messages(
        service,
        request.message,
        conv_id=conv_id,
        conv_summary=conv_summary,
        leaf_message_id=leaf_message_id,
    )

    try:
        logger.info("Chat request started thread_id=%s", thread_id)
        from app.agents.supervisor import get_graph
        graph = get_graph()
        result = await asyncio.wait_for(
            graph.ainvoke(
                {
                    "messages": input_messages,
                },
                config=config,
            ),
            timeout=settings.GLOBAL_DEADLINE,
        )

        agent_name = result.get("current_agent", "unknown")
        final_answer = result.get("final_answer", "")
        agent_steps = result.get("agent_steps", [])
        metric_retrieval_layer = result.get("retrieval_layer", "")
        metric_route_type = result.get("route_type", "")

        sources = collect_sources_from_steps(agent_steps)
        metric_answer = final_answer
        metric_agent = agent_name
        metric_sources = sources
        metric_steps = agent_steps

        service.save_message(conv_id, "assistant", final_answer,
                             parent_id=user_msg.id, agent_name=agent_name, sources=sources)

        # M2: 同步触发增量摘要（非流式端点，阻塞无碍）
        await _maybe_summarize_conversation(conv_id)

        return ChatResponse(
            answer=final_answer,
            agent_name=agent_name,
            sources=sources,
            agent_steps=agent_steps,
        )
    except asyncio.TimeoutError:
        logger.error("Chat timeout thread_id=%s", thread_id)
        timeout_answer = "抱歉，系统响应超时，请稍后重试或缩小问题范围。"
        metric_answer = timeout_answer
        metric_agent = "system"
        metric_status = "timeout"
        metric_error = "TimeoutError"
        service.save_message(conv_id, "assistant", timeout_answer, parent_id=user_msg.id, agent_name="system")
        return ChatResponse(
            answer=timeout_answer,
            agent_name="system",
            sources=[],
            agent_steps=[],
        )
    except Exception as e:
        logger.error("Chat error: %s", e)
        error_answer = f"抱歉，系统处理时出错：{e}"
        metric_answer = error_answer
        metric_agent = "system"
        metric_status = "error"
        metric_error = e.__class__.__name__
        service.save_message(conv_id, "assistant", error_answer, parent_id=user_msg.id, agent_name="system")
        return ChatResponse(
            answer=error_answer,
            agent_name="system",
            sources=[],
            agent_steps=[],
        )
    finally:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        _emit_chat_baseline_metric(
            endpoint="/api/chat",
            query=request.message,
            route_type="graph_non_stream",
            agent_name=metric_agent,
            start_time=start_time,
            final_answer=metric_answer,
            sources=metric_sources,
            first_token_at=start_time if metric_answer else None,
            agent_steps=metric_steps,
            evidence_metadata={
                "retrieval_layer": metric_retrieval_layer,
                "route_type": metric_route_type,
            },
            status=metric_status,
            error_type=metric_error,
        )
        logger.info("Chat request finished thread_id=%s elapsed_ms=%.2f", thread_id, elapsed_ms)


def _persist_message(conv_id: int, role: str, text: str, *, parent_id: int | None = None, **kwargs) -> int:
    """Save a message in an independent DB session (safe from generator closure). Returns the message id."""
    return ChatMessageService.persist_message_with_managed_session(
        conv_id,
        role,
        text,
        parent_id=parent_id,
        **kwargs,
    )


def _should_fast_stream_simple_knowledge(query: str) -> bool:
    try:
        from app.agents.supervisor import _rule_based_route
        from app.rag.query_classifier import classify_query
        from app.rag.rag_utils import extract_query_terms, normalize_query_text
        from app.rag.retrieval_strategy import resolve_retrieval_strategy

        if _rule_based_route(query) != "knowledge_agent":
            return False
        normalized = normalize_query_text(query)
        terms = extract_query_terms(normalized)
        cat = classify_query(query, terms)
        strategy = resolve_retrieval_strategy(cat)
        if strategy.layer not in {"L1", "L2"}:
            return False
        if (
            cat.is_code
            or cat.is_exercise
            or cat.is_answer
            or cat.is_comparison
            or cat.is_learning_path
        ):
            return False
        if strategy.layer == "L2" and (cat.is_long or not cat.is_concept):
            return False
        return True
    except Exception as e:
        logger.debug("Fast-stream eligibility check skipped: %s", e)
        return False


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    service: ChatMessageService = Depends(get_chat_message_service),
):
    """流式对话（SSE，前端逐字显示）"""
    base_thread = request.thread_id or str(uuid.uuid4())
    thread_id = f"{current_user.id}:{base_thread}"
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 25,
    }

    conv = service.ensure_conversation(current_user.id, base_thread, request.message)
    conv_id = conv.id
    conv_summary = conv.summary or ""
    parent_msg_id = request.parent_message_id

    # Determine leaf_message_id for branch-aware history loading
    leaf_message_id: int | None = parent_msg_id

    user_msg = service.save_message(conv_id, "user", request.message, parent_id=parent_msg_id)
    input_messages = _build_input_messages(
        service,
        request.message,
        conv_id=conv_id,
        conv_summary=conv_summary,
        leaf_message_id=leaf_message_id,
    )

    async def _rag_fallback_stream(query: str):
        """Graph 构建失败时的兜底：直接 RAG 检索 + LLM 生成"""
        from langchain_core.messages import HumanMessage, SystemMessage
        from app.rag.retriever import aretrieve_evidence_with_retry
        from app.rag.rag_utils import get_llm
        full_text = ""
        try:
            yield _sse("agent", {"agent_name": "rag_fallback"})
            fused, _verification = await aretrieve_evidence_with_retry(
                query=query,
                k=5,
                use_rerank=True,
                max_retries=1,
                use_llm_verify=False,
            )
            if not fused.final_context:
                full_text = "系统暂时无法使用多Agent模式，且知识库未检索到相关内容。请稍后重试。"
                yield _sse("token", {"text": full_text})
            else:
                messages = [
                    SystemMessage(content="你是408考研智能问答助手。请严格基于给定上下文回答，不要编造。"),
                    HumanMessage(content=f"上下文：\n{fused.final_context}\n\n问题：{query}\n\n请直接回答。"),
                ]
                llm = get_llm()
                async for chunk in llm.astream(messages):
                    content = chunk.content if hasattr(chunk, "content") else str(chunk)
                    text = str(content or "")
                    if text:
                        full_text += text
                        yield _sse("token", {"text": text})
        except Exception as e:
            logger.error("RAG fallback also failed: %s", e, exc_info=True)
            if not full_text:
                yield _sse("token", {"text": f"系统暂时不可用，请稍后重试。错误：{e}"})
        yield _sse("done", {"agent_name": "rag_fallback", "sources": [], "user_msg_id": user_msg.id})

    async def _simple_knowledge_fast_stream(query: str):
        """简单知识问答真流式路径：检索完成后直接 LLM astream 输出 token。"""
        from langchain_core.messages import HumanMessage, SystemMessage
        from app.agents.answer_governance import govern_answer
        from app.agents.prompts import SINGLE_AGENT_FAST_PATH_SYSTEM_PROMPT, SINGLE_AGENT_FAST_PATH_USER_TEMPLATE
        from app.agents.reflection_agent import areflect, apply_reflection_to_answer
        from app.rag.retriever import aretrieve_evidence_with_retry
        from app.rag.rag_utils import get_llm

        full_text = ""
        context = ""
        docs = []
        latest_sources: list[str] = []
        governance = None
        evidence_metadata: dict = {}
        start_time = time.perf_counter()
        first_token_at = None
        deadline_at = start_time + min(settings.GLOBAL_DEADLINE, settings.STREAM_TIMEOUT)
        agent_name = "knowledge_agent"
        emit_metric = _make_metric_emitter(
            endpoint="/api/chat/stream",
            query=query,
            route_type="fast_stream",
            start_time=start_time,
        )

        try:
            yield _sse("agent", {"agent_name": agent_name, "mode": "fast_stream"})
            yield _sse("status", {"stage": "retrieval", "label": "正在检索知识库...", "elapsed_ms": 0})
            yield _sse("tool", {"tool_name": "retrieve_evidence", "status": "start"})

            student_profile = ""
            try:
                from app.services.knowledge_tracker import get_knowledge_tracker
                tracker = get_knowledge_tracker()
                student_profile = tracker.build_cross_session_context(current_user.id)
            except Exception as e:
                logger.debug("Student profile injection skipped: %s", e)

            remaining = _deadline_remaining(deadline_at)
            if remaining <= 0:
                raise asyncio.TimeoutError()
            fused, verification = await asyncio.wait_for(
                aretrieve_evidence_with_retry(
                    query=query,
                    k=5,
                    use_rerank=True,
                    student_profile=student_profile,
                    max_retries=1,
                    use_llm_verify=False,
                ),
                timeout=min(settings.PRE_RETRIEVAL_TIMEOUT, remaining),
            )
            yield _sse("tool", {"tool_name": "retrieve_evidence", "status": "end"})
            yield _sse("status", {"stage": "generation", "label": "正在生成回答...", "elapsed_ms": round((time.perf_counter() - start_time) * 1000)})

            latest_sources = fused.sources
            docs = fused.text_evidences
            context = fused.final_context
            evidence_metadata = {
                **(fused.metadata or {}),
                "text_evidence_count": len(fused.text_evidences),
                "context_tokens": fused.used_token_budget,
            }
            if not context:
                full_text = "未在知识库中找到相关内容。请换一种问法，或明确学科与知识点。"
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                yield _sse("token", {"text": full_text})
            else:
                messages = [
                    SystemMessage(content=SINGLE_AGENT_FAST_PATH_SYSTEM_PROMPT),
                    HumanMessage(content=SINGLE_AGENT_FAST_PATH_USER_TEMPLATE.format(evidence=context, query=query)),
                ]
                llm = get_llm(streaming=True, temperature=settings.TEMP_PRECISE, use_fast=True)
                stream_iter = llm.astream(messages).__aiter__()
                try:
                    while True:
                        remaining = _deadline_remaining(deadline_at)
                        if remaining <= 0:
                            raise asyncio.TimeoutError()
                        try:
                            chunk = await asyncio.wait_for(stream_iter.__anext__(), timeout=remaining)
                        except StopAsyncIteration:
                            break
                        text = _chunk_text(chunk)
                        if not text:
                            continue
                        full_text += text
                        if first_token_at is None:
                            first_token_at = time.perf_counter()
                        yield _sse("token", {"text": text})
                finally:
                    aclose = getattr(stream_iter, "aclose", None)
                    if aclose:
                        await aclose()

            source_augmented = _append_source_line_if_missing(full_text, latest_sources)
            if source_augmented != full_text:
                yield _sse("token", {"text": source_augmented[len(full_text):]})
                full_text = source_augmented
            gov_result = govern_answer(full_text, agent_name, tool_outputs=[context] if context else None)
            reflection_confidence = "unknown"
            reflection_issues: list[str] = []
            try:
                remaining = _deadline_remaining(deadline_at)
                if remaining > 0 and context:
                    reflection = await asyncio.wait_for(
                        areflect(
                            answer=gov_result.answer,
                            evidence_text=context,
                            query=query,
                            agent_name=agent_name,
                            use_llm=False,
                        ),
                        timeout=min(settings.AGENT_RETRY_TIMEOUT, remaining),
                    )
                    reflection_confidence = reflection.confidence
                    reflection_issues = reflection.issues
                    if reflection.suggestion:
                        gov_result.answer = apply_reflection_to_answer(gov_result.answer, reflection)
            except Exception as e:
                logger.warning("Fast-stream reflection skipped: %s", e)

            if gov_result.answer != full_text:
                if gov_result.answer.startswith(full_text):
                    delta = gov_result.answer[len(full_text):]
                    if delta:
                        yield _sse("token", {"text": delta})
                full_text = gov_result.answer

            governance = {
                "confidence": gov_result.confidence,
                "has_source": gov_result.has_source,
                "passed": gov_result.passed,
                "flags": gov_result.flags,
                "reflection_confidence": reflection_confidence,
                "reflection_issues": reflection_issues,
                "evidence_verdict": verification.verdict.value,
                "evidence_score": verification.overall_score,
            }
            yield _sse("governance", {"agent_name": agent_name, **governance})
            yield _sse("final", {
                "agent_name": agent_name,
                "final_answer": full_text,
                "sources": latest_sources,
                "agent_steps": [],
                "streaming_mode": "fast_stream",
            })

            _persist_message(conv_id, "assistant", full_text,
                             parent_id=user_msg.id, agent_name=agent_name, sources=latest_sources, governance=governance)

            await ChatTrackingService.emit_document_qa_event(
                user_id=current_user.id,
                docs=docs,
                governance=governance,
                context="fast-stream",
            )

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            emit_metric(
                agent_name=agent_name,
                final_answer=full_text,
                sources=latest_sources,
                first_token_at=first_token_at,
                governance=governance,
                evidence_metadata=evidence_metadata,
            )
            logger.info("Fast-stream completed thread_id=%s elapsed_ms=%.2f", thread_id, elapsed_ms)
            yield _sse("done", {"agent_name": agent_name, "sources": latest_sources, "user_msg_id": user_msg.id})
            asyncio.create_task(_maybe_summarize_conversation(conv_id))
        except asyncio.TimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Fast-stream timeout thread_id=%s elapsed_ms=%.2f", thread_id, elapsed_ms)
            if full_text:
                partial_governance = _build_timeout_governance(
                    latest_sources,
                    reflection_confidence="unknown",
                    reflection_issues=["响应超时，返回部分答案"],
                )
                emit_metric(
                    agent_name=agent_name,
                    final_answer=full_text,
                    sources=latest_sources,
                    first_token_at=first_token_at,
                    governance=partial_governance,
                    evidence_metadata=evidence_metadata,
                    status="timeout",
                    error_type="TimeoutError",
                )
                yield _sse("governance", {"agent_name": agent_name, **partial_governance})
                yield _sse("final", {
                    "agent_name": agent_name,
                    "final_answer": full_text,
                    "sources": latest_sources,
                    "agent_steps": [],
                    "streaming_mode": "fast_stream_partial",
                })
                _persist_message(conv_id, "assistant", full_text,
                                 parent_id=user_msg.id, agent_name=agent_name, sources=latest_sources, governance=partial_governance)
                yield _sse("done", {"agent_name": agent_name, "sources": latest_sources, "partial": True, "user_msg_id": user_msg.id})
            else:
                emit_metric(
                    agent_name=agent_name,
                    final_answer="",
                    sources=latest_sources,
                    first_token_at=first_token_at,
                    governance=None,
                    evidence_metadata=evidence_metadata,
                    status="timeout",
                    error_type="TimeoutError",
                )
                yield _sse("error", {"message": "响应超时，请稍后重试"})
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Fast-stream error thread_id=%s elapsed_ms=%.2f error=%s", thread_id, elapsed_ms, e, exc_info=True)
            emit_metric(
                agent_name=agent_name,
                final_answer=full_text,
                sources=latest_sources,
                first_token_at=first_token_at,
                governance=governance,
                evidence_metadata=evidence_metadata,
                status="error",
                error_type=e.__class__.__name__,
            )
            yield _sse("error", {"message": str(e)})

    async def event_generator():
        if _should_fast_stream_simple_knowledge(request.message):
            async for chunk in _simple_knowledge_fast_stream(request.message):
                yield chunk
            return

        from app.agents.supervisor import get_graph
        try:
            graph = get_graph()
        except Exception as graph_err:
            logger.error("Graph build failed, falling back to direct RAG: %s", graph_err)
            async for chunk in _rag_fallback_stream(request.message):
                yield chunk
            return
        current_agent = "supervisor"
        full_text = ""
        latest_governance = None
        latest_sources: list[str] = []
        latest_agent_steps: list[dict] = []
        stream_retrieval_layer = ""
        stream_route_type = ""
        stream_route_source = ""
        start_time = time.perf_counter()
        first_token_at = None
        _STREAM_TIMEOUT = settings.STREAM_TIMEOUT
        deadline_at = start_time + min(settings.GLOBAL_DEADLINE, _STREAM_TIMEOUT)
        emit_metric = _make_metric_emitter(
            endpoint="/api/chat/stream",
            query=request.message,
            route_type="graph_stream",
            start_time=start_time,
        )
        done_emitted = False
        stream_failed = False
        partial_timeout_governance = None
        logger.info("Chat stream started thread_id=%s", thread_id)

        try:
            # 使用 astream（节点级流式）而非 astream_events
            # 因为 _wrap_agent 是黑盒节点，astream_events 无法捕获其内部 LLM token
            graph_stream = graph.astream(
                {
                    "messages": input_messages,
                },
                config=config,
                stream_mode="updates",
            ).__aiter__()
            try:
                while True:
                    remaining = _deadline_remaining(deadline_at)
                    if remaining <= 0:
                        logger.error("Stream global deadline exceeded thread_id=%s elapsed_ms=%.2f", thread_id, (time.perf_counter() - start_time) * 1000)
                        if full_text:
                            yield _sse("final", {
                                "agent_name": current_agent,
                                "final_answer": full_text,
                                "sources": latest_sources,
                                "agent_steps": latest_agent_steps,
                                "streaming_mode": "graph_partial",
                            })
                            yield _sse("done", {"agent_name": current_agent, "sources": latest_sources, "partial": True, "user_msg_id": user_msg.id})
                            done_emitted = True
                            partial_timeout_governance = _build_timeout_governance(
                                latest_sources,
                                has_sufficient_evidence=False,
                            )
                            latest_governance = partial_timeout_governance
                        else:
                            yield _sse("error", {"message": "响应超时，请稍后重试"})
                            stream_failed = True
                        break
                    try:
                        update = await asyncio.wait_for(graph_stream.__anext__(), timeout=remaining)
                    except StopAsyncIteration:
                        break
                    except asyncio.TimeoutError:
                        logger.error("Stream global deadline timeout thread_id=%s elapsed_ms=%.2f", thread_id, (time.perf_counter() - start_time) * 1000)
                        if full_text:
                            yield _sse("final", {
                                "agent_name": current_agent,
                                "final_answer": full_text,
                                "sources": latest_sources,
                                "agent_steps": latest_agent_steps,
                                "streaming_mode": "graph_partial",
                            })
                            yield _sse("done", {"agent_name": current_agent, "sources": latest_sources, "partial": True, "user_msg_id": user_msg.id})
                            done_emitted = True
                            partial_timeout_governance = _build_timeout_governance(
                                latest_sources,
                                has_sufficient_evidence=False,
                            )
                            latest_governance = partial_timeout_governance
                        else:
                            yield _sse("error", {"message": "响应超时，请稍后重试"})
                            stream_failed = True
                        break

                    # 整体超时检查
                    if (time.perf_counter() - start_time) > min(settings.GLOBAL_DEADLINE, _STREAM_TIMEOUT):
                        logger.error("Stream timeout thread_id=%s elapsed_ms=%.2f", thread_id, (time.perf_counter() - start_time) * 1000)
                        if full_text:
                            yield _sse("final", {
                                "agent_name": current_agent,
                                "final_answer": full_text,
                                "sources": latest_sources,
                                "agent_steps": latest_agent_steps,
                                "streaming_mode": "graph_partial",
                            })
                            yield _sse("done", {"agent_name": current_agent, "sources": latest_sources, "partial": True, "user_msg_id": user_msg.id})
                            done_emitted = True
                            partial_timeout_governance = _build_timeout_governance(
                                latest_sources,
                                has_sufficient_evidence=False,
                            )
                            latest_governance = partial_timeout_governance
                        else:
                            yield _sse("error", {"message": "响应超时，请稍后重试"})
                            stream_failed = True
                        break

                    # update 是 {node_name: node_output} 格式
                    for node_name, node_output in update.items():
                        now = time.perf_counter()
                        logger.debug("Stream node=%s elapsed_ms=%.2f", node_name, (now - start_time) * 1000)

                        # ── 阶段性状态事件：让前端知道当前进度 ──
                        _STAGE_LABELS = {
                            "supervisor": "正在分析问题...",
                            "knowledge_agent": "正在检索知识库...",
                            "question_agent": "正在生成题目...",
                            "grading_agent": "正在批改答案...",
                            "path_agent": "正在规划学习路径...",
                            "synthesis_node": "正在综合多个来源...",
                        }
                        _stage_label = _STAGE_LABELS.get(node_name)
                        if _stage_label:
                            yield _sse("status", {"stage": node_name, "label": _stage_label, "elapsed_ms": round((now - start_time) * 1000)})

                        # ── supervisor 路由节点 ──
                        if node_name == "supervisor":
                            # supervisor 返回 Command(goto=agent_name, update={...})
                            # astream updates 模式下，supervisor 的输出包含路由信息
                            if isinstance(node_output, dict):
                                routed_agent = node_output.get("current_agent", "")
                                if routed_agent and routed_agent != "supervisor":
                                    current_agent = routed_agent
                                    # 提取策略层信息用于指标
                                    stream_retrieval_layer = node_output.get("retrieval_layer", "")
                                    stream_route_type = node_output.get("route_type", "")
                                    stream_route_source = node_output.get("route_source", "")
                                    logger.info("Agent routed thread_id=%s agent=%s layer=%s route=%s source=%s elapsed_ms=%.2f",
                                                thread_id, current_agent, stream_retrieval_layer, stream_route_type, stream_route_source, (now - start_time) * 1000)
                                    yield _sse("agent", {"agent_name": current_agent})
                            continue

                        # ── Agent 节点完成 ──
                        if node_name in ("knowledge_agent", "question_agent", "grading_agent", "path_agent"):
                            current_agent = node_name
                            agent_data = node_output if isinstance(node_output, dict) else {}

                            final_answer = agent_data.get("final_answer", "")
                            gov = agent_data.get("governance")
                            guard = agent_data.get("guard_result")
                            agent_steps = agent_data.get("agent_steps", [])

                            # 提取策略层信息
                            if agent_data.get("retrieval_layer"):
                                stream_retrieval_layer = agent_data["retrieval_layer"]
                            if agent_data.get("route_type"):
                                stream_route_type = agent_data["route_type"]

                            latest_sources = collect_sources_from_steps(agent_steps)
                            latest_agent_steps = agent_steps

                            if final_answer:
                                full_text = final_answer
                                # 逐块推送 final_answer（模拟流式效果）
                                _CHUNK_SIZE = 20  # 每次推送字符数
                                for i in range(0, len(final_answer), _CHUNK_SIZE):
                                    chunk_text = final_answer[i:i + _CHUNK_SIZE]
                                    if first_token_at is None:
                                        first_token_at = time.perf_counter()
                                        logger.info("Chat stream first_token thread_id=%s agent=%s elapsed_ms=%.2f",
                                                    thread_id, current_agent, (first_token_at - start_time) * 1000)
                                    yield _sse("token", {"text": chunk_text})
                                    await asyncio.sleep(0.01)

                            if gov:
                                latest_governance = _build_governance_from_agent(gov, guard)
                                yield _sse("governance", {
                                    "agent_name": current_agent,
                                    **latest_governance,
                                })

                            yield _sse("final", {
                                "agent_name": current_agent,
                                "final_answer": final_answer,
                                "sources": latest_sources,
                                "agent_steps": agent_steps,
                                "retrieval_layer": stream_retrieval_layer,
                                "route_type": stream_route_type,
                            })
                            continue

                        # ── synthesis_node（复杂路径） ──
                        if node_name == "synthesis_node":
                            syn_data = node_output if isinstance(node_output, dict) else {}
                            syn_answer = syn_data.get("final_answer", "")
                            if syn_answer:
                                full_text = syn_answer
                                _CHUNK_SIZE = 20
                                for i in range(0, len(syn_answer), _CHUNK_SIZE):
                                    chunk_text = syn_answer[i:i + _CHUNK_SIZE]
                                    if first_token_at is None:
                                        first_token_at = time.perf_counter()
                                    yield _sse("token", {"text": chunk_text})
                                    await asyncio.sleep(0.01)
                            gov = syn_data.get("governance")
                            guard = syn_data.get("guard_result")
                            agent_steps = syn_data.get("agent_steps", [])
                            latest_sources = collect_sources_from_steps(agent_steps)
                            latest_agent_steps = agent_steps
                            if gov:
                                latest_governance = _build_governance_from_agent(gov, guard)
                                yield _sse("governance", {"agent_name": current_agent, **latest_governance})
                            yield _sse("final", {
                                "agent_name": current_agent,
                                "final_answer": syn_answer,
                                "sources": latest_sources,
                                "agent_steps": agent_steps,
                            })
                            continue

            finally:
                aclose = getattr(graph_stream, "aclose", None)
                if aclose:
                    await aclose()

            if stream_failed and not full_text:
                emit_metric(
                    agent_name=current_agent,
                    final_answer="",
                    sources=latest_sources,
                    first_token_at=first_token_at,
                    governance=latest_governance,
                    agent_steps=latest_agent_steps,
                    evidence_metadata={
                        "retrieval_layer": stream_retrieval_layer,
                        "route_type": stream_route_type,
                    },
                    status="timeout",
                    error_type="TimeoutError",
                )
                return

            # 流结束，持久化 assistant 消息
            total_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "Chat stream completed thread_id=%s agent=%s total_ms=%.2f had_first_token=%s",
                thread_id,
                current_agent,
                total_ms,
                first_token_at is not None,
            )
            # 在独立 session 中写入，避免 generator 关闭后 session 失效
            _persist_message(conv_id, "assistant", full_text,
                             parent_id=user_msg.id, agent_name=current_agent, sources=latest_sources, governance=latest_governance)

            await ChatTrackingService.emit_multi_agent_event(
                user_id=current_user.id,
                current_agent=current_agent,
                agent_steps=latest_agent_steps,
                governance=latest_governance,
                final_answer=full_text,
            )

            graph_metric_status = "timeout" if "timeout_partial" in ((latest_governance or {}).get("flags") or []) else "ok"
            graph_metric_error = "TimeoutError" if graph_metric_status == "timeout" else ""
            emit_metric(
                agent_name=current_agent,
                final_answer=full_text,
                sources=latest_sources,
                first_token_at=first_token_at,
                governance=latest_governance,
                agent_steps=latest_agent_steps,
                evidence_metadata={
                    "retrieval_layer": stream_retrieval_layer,
                    "route_type": stream_route_type,
                },
                status=graph_metric_status,
                error_type=graph_metric_error,
            )
            if not done_emitted:
                yield _sse("done", {"agent_name": current_agent, "sources": latest_sources, "user_msg_id": user_msg.id})

            # M2: 异步触发增量摘要（不阻塞 SSE 流）
            asyncio.create_task(_maybe_summarize_conversation(conv_id))

        except asyncio.TimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Stream timeout thread_id=%s elapsed_ms=%.2f", thread_id, elapsed_ms)
            if full_text:
                partial_governance = _build_timeout_governance(
                    latest_sources,
                    has_sufficient_evidence=False,
                )
                yield _sse("governance", {"agent_name": current_agent, **partial_governance})
                yield _sse("final", {
                    "agent_name": current_agent,
                    "final_answer": full_text,
                    "sources": latest_sources,
                    "agent_steps": latest_agent_steps,
                    "streaming_mode": "graph_partial",
                })
                _persist_message(conv_id, "assistant", full_text,
                                 parent_id=user_msg.id, agent_name=current_agent, sources=latest_sources, governance=partial_governance)
                emit_metric(
                    agent_name=current_agent,
                    final_answer=full_text,
                    sources=latest_sources,
                    first_token_at=first_token_at,
                    governance=partial_governance,
                    agent_steps=latest_agent_steps,
                    evidence_metadata={
                        "retrieval_layer": stream_retrieval_layer,
                        "route_type": stream_route_type,
                    },
                    status="timeout",
                    error_type="TimeoutError",
                )
                yield _sse("done", {"agent_name": current_agent, "sources": latest_sources, "partial": True, "user_msg_id": user_msg.id})
            else:
                emit_metric(
                    agent_name=current_agent,
                    final_answer="",
                    sources=latest_sources,
                    first_token_at=first_token_at,
                    governance=None,
                    agent_steps=latest_agent_steps,
                    evidence_metadata={
                        "retrieval_layer": stream_retrieval_layer,
                        "route_type": stream_route_type,
                    },
                    status="timeout",
                    error_type="TimeoutError",
                )
                yield _sse("error", {"message": "响应超时，请稍后重试"})
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Stream error thread_id=%s elapsed_ms=%.2f error=%s", thread_id, elapsed_ms, e, exc_info=True)
            emit_metric(
                agent_name=current_agent,
                final_answer=full_text,
                sources=latest_sources,
                first_token_at=first_token_at,
                governance=latest_governance,
                agent_steps=latest_agent_steps,
                evidence_metadata={
                    "retrieval_layer": stream_retrieval_layer,
                    "route_type": stream_route_type,
                },
                status="error",
                error_type=e.__class__.__name__,
            )
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/rag-stream")
async def chat_rag_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    service: ChatMessageService = Depends(get_chat_message_service),
):
    """直接RAG流式问答：跳过Supervisor和多Agent，只做检索+LLM生成"""
    base_thread = request.thread_id or str(uuid.uuid4())
    conv = service.ensure_conversation(current_user.id, base_thread, request.message)
    conv_id = conv.id
    parent_msg_id = request.parent_message_id
    user_msg = service.save_message(conv_id, "user", request.message, parent_id=parent_msg_id)

    async def event_generator():
        from langchain_core.messages import HumanMessage, SystemMessage
        from app.rag.retriever import aretrieve_evidence_with_retry
        from app.rag.rag_utils import get_llm

        full_text = ""
        context = ""
        docs = []
        latest_sources: list[str] = []
        governance = None
        evidence_metadata: dict = {}
        first_token_at = None
        start_time = time.perf_counter()
        _STREAM_TIMEOUT = settings.STREAM_TIMEOUT
        deadline_at = start_time + min(settings.GLOBAL_DEADLINE, _STREAM_TIMEOUT)
        emit_metric = _make_metric_emitter(
            endpoint="/api/chat/rag-stream",
            query=request.message,
            route_type="rag_direct",
            start_time=start_time,
        )
        rag_done_emitted = False
        logger.info("Direct RAG stream started conversation_id=%s", conv_id)

        try:
            yield _sse("agent", {"agent_name": "rag_direct"})
            yield _sse("tool", {"tool_name": "retrieve_evidence", "status": "start"})
            # 构建学生画像（个性化增强）
            student_profile = ""
            try:
                from app.services.knowledge_tracker import get_knowledge_tracker
                tracker = get_knowledge_tracker()
                student_profile = tracker.build_cross_session_context(current_user.id)
            except Exception as e:
                logger.debug("Student profile injection skipped: %s", e)
            remaining = _deadline_remaining(deadline_at)
            if remaining <= 0:
                raise asyncio.TimeoutError()
            fused, verification = await asyncio.wait_for(
                aretrieve_evidence_with_retry(
                    query=request.message,
                    k=5,
                    use_rerank=True,
                    student_profile=student_profile,
                    max_retries=1,
                    use_llm_verify=False,
                ),
                timeout=min(settings.PRE_RETRIEVAL_TIMEOUT, remaining),
            )
            yield _sse("tool", {"tool_name": "retrieve_evidence", "status": "end"})

            latest_sources = fused.sources
            docs = fused.text_evidences
            evidence_metadata = {
                **(fused.metadata or {}),
                "text_evidence_count": len(fused.text_evidences),
                "context_tokens": fused.used_token_budget,
            }
            if not fused.final_context:
                full_text = "未在知识库中找到相关内容。请换一种问法，或明确学科与知识点。"
                if first_token_at is None:
                    first_token_at = time.perf_counter()
                yield _sse("token", {"text": full_text})
            else:
                context = fused.final_context
                messages = [
                    SystemMessage(
                        content=(
                            "你是408考研智能问答助手。请严格基于给定知识库上下文回答。"
                            "不要输出原始JSON或调试信息；不要寒暄，不要自我介绍；"
                            "如果上下文不足，先说明知识库依据不足，再给出保守解释。\n\n"
                            "请按以下结构输出：\n"
                            "1. 概念解释：用通俗中文解释问题。\n"
                            "2. 核心要点：用 2-4 条列出关键原理/特点。\n"
                            "3. 示例说明：给出一个简短例子；若不适合举例可省略。\n"
                            "4. 来源依据：列出检索到的来源文件名。\n\n"
                            "示例输出：\n"
                            "概念解释：进程死锁是指两个或两个以上的进程因争夺资源而互相等待的僵局。\n"
                            "核心要点：\n"
                            "- 产生死锁的四个必要条件：互斥、占有并等待、非抢占、循环等待。\n"
                            "- 常见预防策略是破坏四个必要条件之一。\n"
                            "示例说明：进程A持有R1等待R2，进程B持有R2等待R1，两者都无法继续。\n"
                            "来源依据：xxx.md"
                        )
                    ),
                    HumanMessage(
                        content=(
                            f"知识库上下文：\n{context}\n\n"
                            f"用户问题：{request.message}\n\n"
                            "请给出直接、准确、适合学习的回答。"
                        )
                    ),
                ]
                llm = get_llm()
                stream_iter = llm.astream(messages).__aiter__()
                try:
                    while True:
                        remaining = _deadline_remaining(deadline_at)
                        if remaining <= 0:
                            raise asyncio.TimeoutError()
                        try:
                            chunk = await asyncio.wait_for(stream_iter.__anext__(), timeout=remaining)
                        except StopAsyncIteration:
                            break
                        # 整体超时检查
                        if (time.perf_counter() - start_time) > min(settings.GLOBAL_DEADLINE, _STREAM_TIMEOUT):
                            logger.error("Direct RAG stream timeout conversation_id=%s", conv_id)
                            if full_text:
                                yield _sse("final", {
                                    "agent_name": "rag_direct",
                                    "final_answer": full_text,
                                    "sources": latest_sources,
                                    "agent_steps": [],
                                    "streaming_mode": "rag_direct_partial",
                                })
                                yield _sse("done", {"agent_name": "rag_direct", "sources": latest_sources, "partial": True, "user_msg_id": user_msg.id})
                                rag_done_emitted = True
                            else:
                                yield _sse("error", {"message": "响应超时，请稍后重试"})
                            break
                        text = _chunk_text(chunk)
                        if not text:
                            continue
                        full_text += text
                        if first_token_at is None:
                            first_token_at = time.perf_counter()
                        yield _sse("token", {"text": text})
                finally:
                    aclose = getattr(stream_iter, "aclose", None)
                    if aclose:
                        await aclose()

            if rag_done_emitted:
                emit_metric(
                    agent_name="rag_direct",
                    final_answer=full_text,
                    sources=latest_sources,
                    first_token_at=first_token_at,
                    governance=governance,
                    evidence_metadata=evidence_metadata,
                    status="timeout",
                    error_type="TimeoutError",
                )
                return

            # 后治理：与 Agent 路径对齐，检查格式合规和来源
            from app.agents.answer_governance import govern_answer
            source_augmented = _append_source_line_if_missing(full_text, latest_sources)
            if source_augmented != full_text:
                yield _sse("token", {"text": source_augmented[len(full_text):]})
                full_text = source_augmented
            gov_result = govern_answer(full_text, "knowledge_agent", tool_outputs=[context] if context else None)
            governance = {
                "confidence": gov_result.confidence,
                "has_source": gov_result.has_source,
                "passed": gov_result.passed,
                "flags": gov_result.flags,
                "evidence_verdict": verification.verdict.value,
                "evidence_score": verification.overall_score,
            }
            # 如果治理追加了降级标注，更新 full_text
            if gov_result.answer != full_text:
                full_text = gov_result.answer
            yield _sse("governance", governance)
            yield _sse("final", {
                "agent_name": "rag_direct",
                "final_answer": full_text,
                "sources": latest_sources,
                "agent_steps": [],
            })

            _persist_message(conv_id, "assistant", full_text,
                             parent_id=user_msg.id, agent_name="rag_direct", sources=latest_sources, governance=governance)

            await ChatTrackingService.emit_document_qa_event(
                user_id=current_user.id,
                docs=docs,
                governance=governance,
                context="direct-rag",
            )

            elapsed_ms = (time.perf_counter() - start_time) * 1000
            emit_metric(
                agent_name="rag_direct",
                final_answer=full_text,
                sources=latest_sources,
                first_token_at=first_token_at,
                governance=governance,
                evidence_metadata=evidence_metadata,
            )
            logger.info("Direct RAG stream completed conversation_id=%s elapsed_ms=%.2f", conv_id, elapsed_ms)
            if not rag_done_emitted:
                yield _sse("done", {"agent_name": "rag_direct", "sources": latest_sources, "user_msg_id": user_msg.id})

            # M2: 异步触发增量摘要（不阻塞 SSE 流）
            asyncio.create_task(_maybe_summarize_conversation(conv_id))
        except asyncio.TimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Direct RAG stream timeout conversation_id=%s elapsed_ms=%.2f", conv_id, elapsed_ms)
            emit_metric(
                agent_name="rag_direct",
                final_answer=full_text,
                sources=latest_sources,
                first_token_at=first_token_at,
                governance=governance,
                evidence_metadata=evidence_metadata,
                status="timeout",
                error_type="TimeoutError",
            )
            if full_text:
                yield _sse("final", {
                    "agent_name": "rag_direct",
                    "final_answer": full_text,
                    "sources": latest_sources,
                    "agent_steps": [],
                    "streaming_mode": "rag_direct_partial",
                })
                yield _sse("done", {"agent_name": "rag_direct", "sources": latest_sources, "partial": True, "user_msg_id": user_msg.id})
            else:
                yield _sse("error", {"message": "响应超时，请稍后重试"})
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Direct RAG stream error conversation_id=%s elapsed_ms=%.2f error=%s", conv_id, elapsed_ms, e, exc_info=True)
            emit_metric(
                agent_name="rag_direct",
                final_answer=full_text,
                sources=latest_sources,
                first_token_at=first_token_at,
                governance=governance,
                evidence_metadata=evidence_metadata,
                status="error",
                error_type=e.__class__.__name__,
            )
            if full_text:
                yield _sse("final", {
                    "agent_name": "rag_direct",
                    "final_answer": full_text,
                    "sources": latest_sources,
                    "agent_steps": [],
                    "streaming_mode": "rag_direct_partial",
                })
                yield _sse("done", {"agent_name": "rag_direct", "sources": latest_sources, "partial": True, "user_msg_id": user_msg.id})
            else:
                yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 对话历史 API ──────────────────────────────


@router.get("/conversations", response_model=list[ConversationItem])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    service: ChatMessageService = Depends(get_chat_message_service),
):
    """获取当前用户的对话列表"""
    return service.list_conversations(current_user.id)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    service: ChatMessageService = Depends(get_chat_message_service),
):
    """获取对话详情（含全部历史消息，含分支结构）"""
    detail = service.get_conversation_detail(conversation_id, current_user.id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")
    return detail


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    service: ChatMessageService = Depends(get_chat_message_service),
):
    """删除对话及其全部消息"""
    if not service.delete_conversation(conversation_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")
    return {"success": True}


class FeedbackRequest(BaseModel):
    thread_id: str
    rating: int = 0  # 1=like, -1=dislike
    query: str = ""
    answer: str = ""
    metadata: dict = Field(default_factory=dict)


@router.post("/feedback")
async def submit_feedback(
    request: FeedbackRequest,
    current_user: User = Depends(get_current_user),
):
    """Submit user feedback for data flywheel (Phase 5 P1-1).

    Records like/dislike with query context for periodic bad case clustering.
    """
    try:
        log_feedback(
            query=request.query or "",
            answer=request.answer or "",
            rating=request.rating,
            metadata={
                "thread_id": request.thread_id,
                "user_id": current_user.id,
                **(request.metadata or {}),
            },
        )
        return {"status": "ok", "rating": request.rating}
    except Exception as e:
        logger.error("Feedback submission failed: %s", e)
        return {"status": "error", "detail": str(e)}


@router.get("/feedback/stats")
async def get_feedback_stats(days: int = 7, current_user: User = Depends(get_current_user)):
    """Get feedback statistics for data flywheel dashboard."""
    from app.rag.feedback import get_feedback_stats, cluster_bad_cases
    stats = get_feedback_stats(days=days)
    clusters = cluster_bad_cases(days=days)
    stats["bad_case_clusters"] = clusters
    return stats
