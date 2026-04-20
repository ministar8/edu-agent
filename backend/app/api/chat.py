import json
import logging
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from app.models.schemas import ChatRequest, ChatResponse
from app.agents.supervisor import get_graph

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """与多Agent系统对话（非流式）"""
    thread_id = request.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    try:
        graph = get_graph()
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=request.message)]},
            config=config,
        )

        agent_name = result.get("current_agent", "unknown")
        final_answer = result.get("final_answer", "")
        agent_steps = result.get("agent_steps", [])

        sources = []
        for step in agent_steps:
            if step.get("sources"):
                sources.extend(step["sources"])

        return ChatResponse(
            answer=final_answer,
            agent_name=agent_name,
            sources=list(set(sources)),
            agent_steps=agent_steps,
        )
    except Exception as e:
        logger.error("Chat error: %s", e)
        return ChatResponse(
            answer=f"抱歉，系统处理时出错：{e}",
            agent_name="system",
            sources=[],
            agent_steps=[],
        )


def _sse(event: str, data: dict) -> str:
    """格式化 SSE 事件"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """流式对话（SSE，前端逐字显示）"""
    thread_id = request.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    async def event_generator():
        graph = get_graph()
        current_agent = "supervisor"

        try:
            async for event in graph.astream_events(
                {"messages": [HumanMessage(content=request.message)]},
                config=config,
                version="v2",
            ):
                kind = event.get("event", "")
                name = event.get("name", "")

                # 捕获 Agent 路由信息
                if kind == "on_chain_start":
                    if name in ("knowledge_agent", "question_agent", "grading_agent", "path_agent"):
                        current_agent = name
                        logger.info("Agent routed: %s", name)
                        yield _sse("agent", {"agent_name": current_agent})

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
                    if text:
                        yield _sse("token", {"text": text})

                # 捕获工具调用信息
                elif kind == "on_tool_start":
                    yield _sse("tool", {"tool_name": name, "status": "start"})

                elif kind == "on_tool_end":
                    yield _sse("tool", {"tool_name": name, "status": "end"})

            # 流结束
            yield _sse("done", {"agent_name": current_agent})

        except Exception as e:
            logger.error("Stream error: %s", e, exc_info=True)
            yield _sse("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
