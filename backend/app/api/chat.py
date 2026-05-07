import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.agents.trace_utils import collect_sources_from_steps
from app.db import Conversation, Message, User, get_db
from app.schemas import ChatRequest, ChatResponse, ConversationDetail, ConversationItem, MessageItem

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


def _build_input_messages(conv: Conversation, user_message: str) -> list:
    from langchain_core.messages import HumanMessage, SystemMessage

    return [
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
        HumanMessage(content=user_message),
    ]


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
                "messages": _build_input_messages(conv, request.message),
            },
            config=config,
        )

        agent_name = result.get("current_agent", "unknown")
        final_answer = result.get("final_answer", "")
        agent_steps = result.get("agent_steps", [])

        sources = collect_sources_from_steps(agent_steps)

        _save_message(db, conv.id, "assistant", final_answer,
                      agent_name=agent_name, sources=sources)

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
        start_time = time.perf_counter()
        first_event_at = None
        first_token_at = None
        logger.info("Chat stream started thread_id=%s", thread_id)

        try:
            async for event in graph.astream_events(
                {
                    "messages": _build_input_messages(conv, request.message),
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
            yield _sse("done", {"agent_name": current_agent, "sources": latest_sources})

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
