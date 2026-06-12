import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.config import settings
from app.agents.trace_utils import collect_sources_from_steps
from app.db import Conversation, Message, User, get_db
from app.events import TrackingEvent, emit, extract_kp_ids_from_docs, extract_kp_ids_from_steps
from app.schemas import ChatRequest, ChatResponse, ConversationDetail, ConversationItem, MessageItem
from app.rag.feedback import log_feedback
from app.rag.metrics import metrics
from app.rag.rag_utils import estimate_tokens

logger = logging.getLogger(__name__)
router = APIRouter()

_SOURCE_MARKER_RE = re.compile(
    r"(\[(?:来源|Source)\s*\d*\s*:)|(^|\n)\s*(?:来源依据|来源|Sources?|参考来源)\s*[:：]",
    re.IGNORECASE,
)


def _ensure_conversation(db: Session, user_id: int, base_thread: str, first_message: str) -> Conversation:
    """确保 Conversation 记录存在，不存在则创建"""
    thread_id = f"{user_id}:{base_thread}"
    conv = db.query(Conversation).filter(Conversation.thread_id == thread_id).first()
    if conv:
        return conv
    title = first_message[:50] if first_message else "新对话"
    conv = Conversation(user_id=user_id, thread_id=thread_id, title=title)
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return conv


def _save_message(db: Session, conversation_id: int, role: str, content: str,
                  agent_name: str | None = None,
                  sources: list[str] | None = None,
                  governance: dict | None = None,
                  parent_id: int | None = None) -> Message:
    """写入一条消息记录"""
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conv is not None:
        conv.updated_at = datetime.now(timezone.utc)

    # Determine siblings_order: count existing siblings with same parent
    parent_filter = Message.parent_id == parent_id if parent_id is not None else Message.parent_id.is_(None)
    max_order = (
        db.query(func.max(Message.siblings_order))
        .filter(parent_filter, Message.conversation_id == conversation_id)
        .scalar()
    )
    siblings_order = (max_order or 0) + 1

    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        agent_name=agent_name,
        sources=json.dumps(sources or [], ensure_ascii=False),
        governance=json.dumps(governance, ensure_ascii=False) if governance else None,
        parent_id=parent_id,
        siblings_order=siblings_order,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def _append_source_line_if_missing(answer: str, sources: list[str]) -> str:
    if not answer or not sources:
        return answer
    if _SOURCE_MARKER_RE.search(answer):
        return answer
    return answer.rstrip() + "\n\n来源依据：" + "，".join(sources[:5])


def _build_governance_from_agent(gov: dict, guard: dict | None) -> dict:
    """从 Agent 节点输出构建 governance 字典（graph_stream 路径）"""
    return {
        "confidence": gov.get("confidence", "unknown"),
        "has_source": gov.get("has_source", False),
        "passed": gov.get("passed", True),
        "flags": gov.get("flags", []),
        "has_sufficient_evidence": guard.get("has_sufficient_evidence", True) if guard else True,
    }


def _build_timeout_governance(sources: list[str], **extra) -> dict:
    """构建超时降级 governance 字典"""
    return {
        "confidence": "low",
        "has_source": bool(sources),
        "passed": False,
        "flags": ["timeout_partial"],
        **extra,
    }


def _make_metric_emitter(
    *,
    endpoint: str,
    query: str,
    route_type: str,
    start_time: float,
):
    """创建绑定固定参数的 metric 发射器，减少重复传参"""
    def emit(
        agent_name: str,
        final_answer: str = "",
        sources: list[str] | None = None,
        first_token_at: float | None = None,
        governance: dict | None = None,
        evidence_metadata: dict | None = None,
        agent_steps: list[dict] | None = None,
        status: str = "ok",
        error_type: str = "",
    ) -> None:
        _emit_chat_baseline_metric(
            endpoint=endpoint,
            query=query,
            route_type=route_type,
            agent_name=agent_name,
            start_time=start_time,
            final_answer=final_answer,
            sources=sources,
            first_token_at=first_token_at,
            governance=governance,
            evidence_metadata=evidence_metadata,
            agent_steps=agent_steps,
            status=status,
            error_type=error_type,
        )
    return emit


def _emit_chat_baseline_metric(
    *,
    endpoint: str,
    query: str,
    route_type: str,
    agent_name: str,
    start_time: float,
    final_answer: str = "",
    sources: list[str] | None = None,
    first_token_at: float | None = None,
    governance: dict | None = None,
    evidence_metadata: dict | None = None,
    agent_steps: list[dict] | None = None,
    status: str = "ok",
    error_type: str = "",
) -> None:
    sources = sources or []
    governance = governance or {}
    evidence_metadata = evidence_metadata or {}
    agent_steps = agent_steps or []
    total_ms = round((time.perf_counter() - start_time) * 1000, 3)
    first_token_ms = round((first_token_at - start_time) * 1000, 3) if first_token_at is not None else None
    prompt_tokens = estimate_tokens(query or "")
    completion_tokens = estimate_tokens(final_answer or "")
    raw_evidence_verdict = governance.get("evidence_verdict", evidence_metadata.get("evidence_verdict", ""))
    if isinstance(raw_evidence_verdict, dict):
        evidence_verdict = raw_evidence_verdict.get("verdict", "")
        evidence_score = raw_evidence_verdict.get("overall_score", evidence_metadata.get("evidence_score", 0.0))
    else:
        evidence_verdict = raw_evidence_verdict
        evidence_score = governance.get("evidence_score", evidence_metadata.get("evidence_score", 0.0))
    metrics.emit_chat_baseline(
        endpoint=endpoint,
        query=query,
        route_type=route_type,
        agent_name=agent_name,
        status=status,
        duration_ms=total_ms,
        values={
            "total_latency_ms": total_ms,
            "first_token_ms": first_token_ms,
            "answer_chars": len(final_answer or ""),
            "answer_tokens_est": completion_tokens,
            "query_tokens_est": prompt_tokens,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "llm_call_count": evidence_metadata.get("llm_call_count", 1 if final_answer else 0),
            "embedding_call_count": evidence_metadata.get("embedding_call_count", 0),
            "reranker_call_count": evidence_metadata.get("reranker_call_count", 1 if evidence_metadata.get("use_rerank") else 0),
            "source_count": len(sources),
            "agent_step_count": len(agent_steps),
            "governance_confidence": governance.get("confidence", ""),
            "governance_passed": governance.get("passed", None),
            "governance_flags": governance.get("flags", []),
            "evidence_verdict": evidence_verdict,
            "evidence_score": evidence_score,
            "retrieval_depth": evidence_metadata.get("retrieval_depth", ""),
            "retrieval_layer": evidence_metadata.get("retrieval_layer", ""),
            "retrieval_route_type": evidence_metadata.get("route_type", ""),
            "text_evidence_count": evidence_metadata.get("text_evidence_count", 0),
            "hit_docs_count": evidence_metadata.get("result_count", evidence_metadata.get("text_evidence_count", 0)),
            "used_evidence_count": evidence_metadata.get("text_evidence_count", 0),
            "kg_used": evidence_metadata.get("kg_used", False),
            "kg_skipped": evidence_metadata.get("kg_skipped", False),
            "hyde_triggered": evidence_metadata.get("hyde_triggered", False),
            "verifier_retry_triggered": bool(evidence_metadata.get("retry_count", 0)),
            "agentic_path_triggered": route_type in {"graph_stream", "graph_non_stream"},
            "context_tokens": evidence_metadata.get("context_tokens", 0),
            "retrieval_latency_ms": evidence_metadata.get("retrieval_latency_ms", None),
            "rerank_latency_ms": evidence_metadata.get("rerank_latency_ms", None),
            "kg_latency_ms": evidence_metadata.get("kg_latency_ms", None),
            "generation_latency_ms": evidence_metadata.get("generation_latency_ms", None),
            "governance_latency_ms": evidence_metadata.get("governance_latency_ms", None),
            "semantic_cache_hit": evidence_metadata.get("semantic_cache_hit", False),
            "semantic_cache_similarity": evidence_metadata.get("semantic_cache_similarity", 0.0),
            "error_type": error_type,
        },
    )


async def _maybe_summarize_conversation(conversation_id: int) -> None:
    """检查并触发增量合并摘要（后台任务）

    每 12 条消息触发一次：取已有 summary + 最早 6 轮（12条）→ LLM → 更新 summary。
    """
    from app.agents.memory_manager import summarize_messages, should_trigger_summary
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        try:
            msg_count = db.query(Message).filter(Message.conversation_id == conversation_id).count()
            if not should_trigger_summary(msg_count):
                return

            conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not conv:
                return

            # 取最早 12 条（6 轮）用于摘要
            early_msgs = (
                db.query(Message)
                .filter(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc())
                .limit(12)
                .all()
            )
            if not early_msgs:
                return

            new_messages = [{"role": m.role, "content": m.content} for m in early_msgs]
            existing_summary = conv.summary or ""

            summary = await summarize_messages(new_messages, existing_summary=existing_summary)
            if summary:
                conv.summary = summary
                db.commit()
                logger.info("Conversation summary updated conv_id=%s", conversation_id)
        except Exception as e:
            logger.warning("Summary generation failed (non-fatal): %s", e)


def _build_input_messages(conv: Conversation, user_message: str, db: Session | None = None, *, conv_id: int | None = None, conv_summary: str | None = None, leaf_message_id: int | None = None) -> list:
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

    # Use pre-extracted values if provided (avoids DetachedInstanceError in async generators)
    _conv_id = conv_id if conv_id is not None else conv.id
    _conv_summary = conv_summary if conv_summary is not None else (conv.summary or "")

    messages: list = [
        SystemMessage(
            content=(
                "请用简洁、规范、整洁的中文分点回答。"
                "除非用户明确要求表格、长文或完整试卷，否则不要使用表格和大段说明；"
                "优先使用有序编号或短横线列表，每一点控制在1到2句话；"
                "必要时只保留少量二级标题，不要输出三级标题；"
                "不要使用 Markdown 加粗符号 **，需要强调时使用空格或普通文字表达；"
                "408题目或解析必须包含题干、答案、解析三个部分；"
                "不要输出原始JSON、调试信息或无意义前缀。"
            )
        ),
    ]

    # 注入会话摘要（更早的对话已被压缩）
    if _conv_summary:
        messages.append(SystemMessage(
            content=f"【会话早期摘要】\n{_conv_summary}\n---"
        ))

    if db is not None:
        # Branch-aware: if leaf_message_id provided, trace parent chain
        if leaf_message_id is not None:
            chain: list[Message] = []
            current = db.query(Message).filter(Message.id == leaf_message_id).first()
            while current is not None:
                chain.append(current)
                if current.parent_id is not None:
                    current = db.query(Message).filter(Message.id == current.parent_id).first()
                else:
                    break
            chain.reverse()  # oldest first
            # Take last 12 messages from the chain
            chain = chain[-12:]
            for msg in chain:
                if msg.role == "user":
                    messages.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    content = msg.content[:500] + "..." if len(msg.content) > 500 else msg.content
                    messages.append(AIMessage(content=content))
        else:
            # Legacy: load last 12 messages by time
            history_msgs = (
                db.query(Message)
                .filter(Message.conversation_id == _conv_id)
                .order_by(Message.created_at.desc())
                .limit(12)
                .all()
            )
            history_msgs.reverse()  # 恢复时间正序
            for msg in history_msgs:
                if msg.role == "user":
                    messages.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    content = msg.content[:500] + "..." if len(msg.content) > 500 else msg.content
                    messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=user_message))
    return messages


@router.post("", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
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

    conv = _ensure_conversation(db, current_user.id, base_thread, request.message)
    conv_id = conv.id
    conv_summary = conv.summary or ""
    parent_msg_id = request.parent_message_id
    leaf_message_id: int | None = parent_msg_id
    user_msg = _save_message(db, conv_id, "user", request.message, parent_id=parent_msg_id)

    try:
        logger.info("Chat request started thread_id=%s", thread_id)
        from app.agents.supervisor import get_graph
        graph = get_graph()
        result = await asyncio.wait_for(
            graph.ainvoke(
                {
                    "messages": _build_input_messages(conv, request.message, db=db, conv_id=conv_id, conv_summary=conv_summary, leaf_message_id=leaf_message_id),
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

        _save_message(db, conv_id, "assistant", final_answer,
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
        _save_message(db, conv_id, "assistant", timeout_answer, parent_id=user_msg.id, agent_name="system")
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
        _save_message(db, conv_id, "assistant", error_answer, parent_id=user_msg.id, agent_name="system")
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


def _sse(event: str, data: dict) -> str:
    """格式化 SSE 事件"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _deadline_remaining(deadline_at: float) -> float:
    return max(0.0, deadline_at - time.perf_counter())


def _chunk_text(chunk) -> str:
    content = chunk.content if hasattr(chunk, "content") else str(chunk)
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content or "")


def _persist_message(conv_id: int, role: str, text: str, *, parent_id: int | None = None, **kwargs) -> int:
    """Save a message in an independent DB session (safe from generator closure). Returns the message id."""
    from app.db.session import SessionLocal
    with SessionLocal() as _db:
        msg = _save_message(_db, conv_id, role, text, parent_id=parent_id, **kwargs)
        return msg.id


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
    db: Session = Depends(get_db),
):
    """流式对话（SSE，前端逐字显示）"""
    base_thread = request.thread_id or str(uuid.uuid4())
    thread_id = f"{current_user.id}:{base_thread}"
    config = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": 25,
    }

    conv = _ensure_conversation(db, current_user.id, base_thread, request.message)
    conv_id = conv.id
    conv_summary = conv.summary or ""
    parent_msg_id = request.parent_message_id

    # Determine leaf_message_id for branch-aware history loading
    leaf_message_id: int | None = parent_msg_id

    user_msg = _save_message(db, conv_id, "user", request.message, parent_id=parent_msg_id)

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

            kp_ids = extract_kp_ids_from_docs(docs)
            if kp_ids:
                try:
                    await emit(TrackingEvent(
                        event_type="qa_high_confidence" if governance.get("confidence") == "high" else "qa_low_confidence",
                        user_id=current_user.id,
                        knowledge_point_ids=kp_ids,
                        category=(docs[0].metadata.get("category") or docs[0].collection or "") if docs else "",
                        difficulty=1.0,
                        outcome=1.0 if governance.get("confidence") == "high" else 0.3,
                    ))
                except Exception as e:
                    logger.warning("Tracking event emission failed (fast-stream): %s", e)

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
                    "messages": _build_input_messages(conv, request.message, db=db, conv_id=conv_id, conv_summary=conv_summary, leaf_message_id=leaf_message_id),
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

            # ── 知识追踪事件 ──
            try:
                kp_ids = extract_kp_ids_from_steps(latest_agent_steps)
                if kp_ids and current_agent in ("knowledge_agent", "grading_agent", "path_agent"):
                    gov_confidence = (latest_governance or {}).get("confidence", "low")
                    if current_agent == "grading_agent":
                        # 从批改结果中提取分数、知识点、难度
                        import re
                        score_match = re.search(r'评分[：:]\s*(\d+)\s*/\s*100', full_text)
                        score = int(score_match.group(1)) if score_match else 50
                        if score >= 80:
                            event_type = "grading_excellent"
                        elif score >= 50:
                            event_type = "grading_pass"
                        else:
                            event_type = "grading_fail"
                        outcome = score / 100.0
                        # 解析难度
                        diff_match = re.search(r'难度[：:]\s*(基础|理解|综合|创新)', full_text)
                        diff_map = {"基础": 1.0, "理解": 1.3, "综合": 1.6, "创新": 2.0}
                        difficulty = diff_map.get(diff_match.group(1), 1.3) if diff_match else 1.3
                        # 解析知识点名称 → 匹配 Registry
                        kp_match = re.search(r'知识点[：:]\s*(.+)', full_text)
                        if kp_match and not kp_ids:
                            kp_name = kp_match.group(1).strip()
                            try:
                                from app.db.models import KnowledgePointRegistry
                                from app.db.session import SessionLocal
                                with SessionLocal() as _lookup_db:
                                    kp_reg = _lookup_db.query(KnowledgePointRegistry).filter(
                                        KnowledgePointRegistry.name == kp_name,
                                    ).first()
                                    if kp_reg:
                                        kp_ids = [kp_reg.id]
                            except Exception as e:
                                logger.debug("Knowledge point registry lookup skipped: %s", e)
                    else:
                        event_type = "qa_high_confidence" if gov_confidence == "high" else "qa_low_confidence"
                        outcome = 1.0 if gov_confidence == "high" else 0.3
                        difficulty = 1.0
                    await emit(TrackingEvent(
                        event_type=event_type,
                        user_id=current_user.id,
                        knowledge_point_ids=kp_ids,
                        category="",
                        difficulty=difficulty,
                        outcome=outcome,
                    ))
            except Exception as e:
                logger.warning("Tracking event emission failed (multi-agent): %s", e)

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
    db: Session = Depends(get_db),
):
    """直接RAG流式问答：跳过Supervisor和多Agent，只做检索+LLM生成"""
    base_thread = request.thread_id or str(uuid.uuid4())
    conv = _ensure_conversation(db, current_user.id, base_thread, request.message)
    conv_id = conv.id
    parent_msg_id = request.parent_message_id
    user_msg = _save_message(db, conv_id, "user", request.message, parent_id=parent_msg_id)

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

            # ── 知识追踪事件 ──
            kp_ids = extract_kp_ids_from_docs(docs)
            if kp_ids:
                gov_confidence = governance.get("confidence", "low") if governance else "low"
                event_type = "qa_high_confidence" if gov_confidence == "high" else "qa_low_confidence"
                try:
                    await emit(TrackingEvent(
                        event_type=event_type,
                        user_id=current_user.id,
                        knowledge_point_ids=kp_ids,
                        category=(docs[0].metadata.get("category") or docs[0].collection or "") if docs else "",
                        difficulty=1.0,
                        outcome=1.0 if gov_confidence == "high" else 0.3,
                    ))
                except Exception as e:
                    logger.warning("Tracking event emission failed: %s", e)

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


def _msg_to_item(msg: Message, *, child_count: int = 0) -> MessageItem:
    """ORM Message → Pydantic MessageItem"""
    sources = json.loads(msg.sources) if msg.sources else []
    governance = json.loads(msg.governance) if msg.governance else None
    return MessageItem(
        id=msg.id,
        role=msg.role,
        content=msg.content,
        agent_name=msg.agent_name,
        sources=sources,
        governance=governance,
        parent_id=msg.parent_id,
        siblings_order=msg.siblings_order,
        child_count=child_count,
        created_at=msg.created_at,
    )


@router.get("/conversations", response_model=list[ConversationItem])
async def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的对话列表"""
    convs = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )
    items = []
    for conv in convs:
        msg_count = db.query(Message).filter(Message.conversation_id == conv.id).count()
        items.append(ConversationItem(
            id=conv.id,
            thread_id=conv.thread_id,
            title=conv.title,
            summary=conv.summary or "",
            created_at=conv.created_at,
            updated_at=conv.updated_at,
            message_count=msg_count,
        ))
    return items


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取对话详情（含全部历史消息，含分支结构）"""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")

    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    # Compute child_count for each message
    child_counts: dict[int, int] = {}
    for m in msgs:
        if m.parent_id is not None:
            child_counts[m.parent_id] = child_counts.get(m.parent_id, 0) + 1

    return ConversationDetail(
        id=conv.id,
        thread_id=conv.thread_id,
        title=conv.title,
        summary=conv.summary or "",
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[_msg_to_item(m, child_count=child_counts.get(m.id, 0)) for m in msgs],
    )


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除对话及其全部消息"""
    conv = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对话不存在")

    db.query(Message).filter(Message.conversation_id == conv.id).delete()
    db.delete(conv)
    db.commit()
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
