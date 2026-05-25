import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.agents.trace_utils import collect_sources_from_steps
from app.db import Conversation, Message, User, get_db
from app.events import TrackingEvent, emit, extract_kp_ids_from_docs, extract_kp_ids_from_steps
from app.schemas import ChatRequest, ChatResponse, ConversationDetail, ConversationItem, MessageItem
from app.rag.feedback import log_feedback

logger = logging.getLogger(__name__)
router = APIRouter()


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
                  governance: dict | None = None) -> Message:
    """写入一条消息记录"""
    conv = db.query(Conversation).filter(Conversation.id == conversation_id).first()
    if conv is not None:
        conv.updated_at = datetime.now(timezone.utc)
    msg = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        agent_name=agent_name,
        sources=json.dumps(sources or [], ensure_ascii=False),
        governance=json.dumps(governance, ensure_ascii=False) if governance else None,
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


async def _maybe_summarize_conversation(conversation_id: int) -> None:
    """检查并触发增量合并摘要（后台任务）

    每 12 条消息触发一次：取已有 summary + 最早 6 轮（12条）→ LLM → 更新 summary。
    """
    from app.agents.memory_manager import summarize_messages, should_trigger_summary
    from app.db.session import SessionLocal

    db = SessionLocal()
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
    finally:
        db.close()


def _build_input_messages(conv: Conversation, user_message: str, db: Session | None = None) -> list:
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

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
    if conv.summary:
        messages.append(SystemMessage(
            content=f"【会话早期摘要】\n{conv.summary}\n---"
        ))

    # 加载最近 6 轮历史消息（12 条，跳过已被摘要覆盖的更早消息）
    if db is not None:
        history_msgs = (
            db.query(Message)
            .filter(Message.conversation_id == conv.id)
            .order_by(Message.created_at.desc())
            .limit(12)
            .all()
        )
        history_msgs.reverse()  # 恢复时间正序
        for msg in history_msgs:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                # 截断过长的 assistant 回复，避免 token 爆炸
                content = msg.content[:300] + "..." if len(msg.content) > 300 else msg.content
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
        "recursion_limit": 10,
    }

    conv = _ensure_conversation(db, current_user.id, base_thread, request.message)
    _save_message(db, conv.id, "user", request.message)

    try:
        logger.info("Chat request started thread_id=%s", thread_id)
        from app.agents.supervisor import get_graph
        graph = get_graph()
        result = await graph.ainvoke(
            {
                "messages": _build_input_messages(conv, request.message, db=db),
            },
            config=config,
        )

        agent_name = result.get("current_agent", "unknown")
        final_answer = result.get("final_answer", "")
        agent_steps = result.get("agent_steps", [])

        sources = collect_sources_from_steps(agent_steps)

        _save_message(db, conv.id, "assistant", final_answer,
                      agent_name=agent_name, sources=sources)

        # M2: 同步触发增量摘要（非流式端点，阻塞无碍）
        await _maybe_summarize_conversation(conv.id)

        return ChatResponse(
            answer=final_answer,
            agent_name=agent_name,
            sources=sources,
            agent_steps=agent_steps,
        )
    except Exception as e:
        logger.error("Chat error: %s", e)
        _save_message(db, conv.id, "assistant", f"抱歉，系统处理时出错：{e}", agent_name="system")
        return ChatResponse(
            answer=f"抱歉，系统处理时出错：{e}",
            agent_name="system",
            sources=[],
            agent_steps=[],
        )
    finally:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info("Chat request finished thread_id=%s elapsed_ms=%.2f", thread_id, elapsed_ms)


def _sse(event: str, data: dict) -> str:
    """格式化 SSE 事件"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


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
        "recursion_limit": 10,
    }

    conv = _ensure_conversation(db, current_user.id, base_thread, request.message)
    _save_message(db, conv.id, "user", request.message)

    async def event_generator():
        from app.agents.supervisor import get_graph
        graph = get_graph()
        current_agent = "supervisor"
        full_text = ""
        latest_governance = None
        latest_sources: list[str] = []
        latest_agent_steps: list[dict] = []
        start_time = time.perf_counter()
        first_event_at = None
        first_token_at = None
        logger.info("Chat stream started thread_id=%s", thread_id)

        try:
            async for event in graph.astream_events(
                {
                    "messages": _build_input_messages(conv, request.message, db=db),
                },
                config=config,
                version="v2",
            ):
                now = time.perf_counter()
                if first_event_at is None:
                    first_event_at = now
                    logger.info(
                        "Chat stream first_event thread_id=%s elapsed_ms=%.2f",
                        thread_id,
                        (first_event_at - start_time) * 1000,
                    )
                kind = event.get("event", "")
                name = event.get("name", "")

                # 捕获 Agent 路由信息
                if kind == "on_chain_start":
                    if name in ("knowledge_agent", "question_agent", "grading_agent", "path_agent"):
                        current_agent = name
                        logger.info(
                            "Agent routed thread_id=%s agent=%s elapsed_ms=%.2f",
                            thread_id,
                            name,
                            (now - start_time) * 1000,
                        )
                        yield _sse("agent", {"agent_name": current_agent})

                # 捕获 Agent 执行结束 + 治理结果
                elif kind == "on_chain_end":
                    if name in ("knowledge_agent", "question_agent", "grading_agent", "path_agent"):
                        output = event.get("data", {}).get("output", {})
                        gov = output.get("governance")
                        guard = output.get("guard_result")
                        final_answer = output.get("final_answer")
                        agent_steps = output.get("agent_steps", [])
                        latest_sources = collect_sources_from_steps(agent_steps)
                        latest_agent_steps = agent_steps
                        if final_answer:
                            full_text = final_answer
                        if gov:
                            latest_governance = {
                                "confidence": gov.get("confidence", "unknown"),
                                "has_source": gov.get("has_source", False),
                                "passed": gov.get("passed", True),
                                "flags": gov.get("flags", []),
                                "has_sufficient_evidence": guard.get("has_sufficient_evidence", True) if guard else True,
                            }
                            yield _sse("governance", {
                                "agent_name": name,
                                **latest_governance,
                            })
                        if final_answer:
                            yield _sse("final", {
                                "agent_name": name,
                                "final_answer": final_answer,
                                "sources": latest_sources,
                                "agent_steps": agent_steps,
                            })

                # 捕获 LLM 文本输出，逐 token 推送
                elif kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    content = chunk.content if hasattr(chunk, "content") else str(chunk)
                    # content 可能是 str 或 list（多模态）
                    if isinstance(content, list):
                        text = "".join(
                            item.get("text", "") if isinstance(item, dict) else str(item)
                            for item in content
                        )
                    elif isinstance(content, str):
                        text = content
                    else:
                        text = str(content) if content else ""
                    if text and current_agent != "supervisor":
                        full_text += text
                        if first_token_at is None:
                            first_token_at = now
                            logger.info(
                                "Chat stream first_token thread_id=%s agent=%s elapsed_ms=%.2f",
                                thread_id,
                                current_agent,
                                (first_token_at - start_time) * 1000,
                            )
                        yield _sse("token", {"text": text})

                # 捕获工具调用信息
                elif kind == "on_tool_start":
                    logger.info(
                        "Tool start thread_id=%s agent=%s tool=%s elapsed_ms=%.2f",
                        thread_id,
                        current_agent,
                        name,
                        (now - start_time) * 1000,
                    )
                    yield _sse("tool", {"tool_name": name, "status": "start"})

                elif kind == "on_tool_end":
                    logger.info(
                        "Tool end thread_id=%s agent=%s tool=%s elapsed_ms=%.2f",
                        thread_id,
                        current_agent,
                        name,
                        (now - start_time) * 1000,
                    )
                    yield _sse("tool", {"tool_name": name, "status": "end"})

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
            from app.db.session import SessionLocal as _SL
            _persist_db = _SL()
            try:
                _save_message(_persist_db, conv.id, "assistant", full_text,
                              agent_name=current_agent,
                              sources=latest_sources,
                              governance=latest_governance)
            finally:
                _persist_db.close()

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
                                from app.db.session import SessionLocal as _SL2
                                _lookup_db = _SL2()
                                try:
                                    kp_reg = _lookup_db.query(KnowledgePointRegistry).filter(
                                        KnowledgePointRegistry.name == kp_name,
                                    ).first()
                                    if kp_reg:
                                        kp_ids = [kp_reg.id]
                                finally:
                                    _lookup_db.close()
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

            yield _sse("done", {"agent_name": current_agent, "sources": latest_sources})

            # M2: 异步触发增量摘要（不阻塞 SSE 流）
            asyncio.create_task(_maybe_summarize_conversation(conv.id))

        except asyncio.TimeoutError:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Stream timeout thread_id=%s elapsed_ms=%.2f", thread_id, elapsed_ms)
            yield _sse("error", {"message": "响应超时，请稍后重试"})
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Stream error thread_id=%s elapsed_ms=%.2f error=%s", thread_id, elapsed_ms, e, exc_info=True)
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
    _save_message(db, conv.id, "user", request.message)

    async def event_generator():
        from langchain_core.messages import HumanMessage, SystemMessage
        from app.rag.retriever import retrieve_evidence
        from app.rag.rag_utils import get_llm

        full_text = ""
        context = ""
        docs = []
        latest_sources: list[str] = []
        start_time = time.perf_counter()
        logger.info("Direct RAG stream started conversation_id=%s", conv.id)

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
            fused = await asyncio.to_thread(
                retrieve_evidence,
                query=request.message,
                k=5,
                use_rerank=True,
                student_profile=student_profile,
            )
            yield _sse("tool", {"tool_name": "retrieve_evidence", "status": "end"})

            latest_sources = fused.sources
            docs = fused.text_evidences
            if not fused.final_context:
                full_text = "未在知识库中找到相关内容。请换一种问法，或明确学科与知识点。"
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
                async for chunk in llm.astream(messages):
                    content = chunk.content if hasattr(chunk, "content") else str(chunk)
                    if isinstance(content, list):
                        text = "".join(
                            item.get("text", "") if isinstance(item, dict) else str(item)
                            for item in content
                        )
                    else:
                        text = str(content or "")
                    if not text:
                        continue
                    full_text += text
                    yield _sse("token", {"text": text})

            # 后治理：与 Agent 路径对齐，检查格式合规和来源
            from app.agents.answer_governance import govern_answer
            gov_result = govern_answer(full_text, "knowledge_agent", tool_outputs=[context] if context else None)
            governance = {
                "confidence": gov_result.confidence,
                "has_source": gov_result.has_source,
                "passed": gov_result.passed,
                "flags": gov_result.flags,
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

            from app.db.session import SessionLocal as _SL
            _persist_db = _SL()
            try:
                _save_message(
                    _persist_db,
                    conv.id,
                    "assistant",
                    full_text,
                    agent_name="rag_direct",
                    sources=latest_sources,
                    governance=governance,
                )
            finally:
                _persist_db.close()

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
            logger.info("Direct RAG stream completed conversation_id=%s elapsed_ms=%.2f", conv.id, elapsed_ms)
            yield _sse("done", {"agent_name": "rag_direct", "sources": latest_sources})

            # M2: 异步触发增量摘要（不阻塞 SSE 流）
            asyncio.create_task(_maybe_summarize_conversation(conv.id))
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error("Direct RAG stream error conversation_id=%s elapsed_ms=%.2f error=%s", conv.id, elapsed_ms, e, exc_info=True)
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── 对话历史 API ──────────────────────────────


def _msg_to_item(msg: Message) -> MessageItem:
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
    """获取对话详情（含全部历史消息）"""
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
    return ConversationDetail(
        id=conv.id,
        thread_id=conv.thread_id,
        title=conv.title,
        summary=conv.summary or "",
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[_msg_to_item(m) for m in msgs],
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
