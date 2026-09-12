"""FastAPI 服务：暴露多 Agent 问答（token/message 双流式）、出题/批改与 JWT 认证。"""

import inspect
import json
import logging
import warnings
from collections.abc import AsyncGenerator, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from langchain_core._api import LangChainBetaWarning
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from agents import DEFAULT_AGENT, get_agent, get_all_agent_info
from agents import agents as agent_registry
from agents.grading_core import agrade_answer
from agents.question_core import agenerate_question_set
from core import settings
from db import User, init_db
from memory import initialize_database, initialize_store
from prompts import PROMPT_SET_VERSION
from schema import (
    ChatHistory,
    ChatHistoryInput,
    ChatMessage,
    GradeRequest,
    GradeResponse,
    QuestionRequest,
    QuestionResponse,
    ServiceMetadata,
    StreamInput,
    UserInput,
    UserThreads,
    UserThreadsInput,
)
from service.auth import get_current_user
from service.auth import router as auth_router
from service.errors import (
    CODE_GENERATE_FAILED,
    CODE_GRADE_FAILED,
    CODE_INVALID_CONFIG,
    CODE_THREAD_NOT_FOUND,
    CODE_UNKNOWN_AGENT,
    bad_request,
    internal_error,
    not_found,
)
from service.health import collect_health
from service.threads import list_user_threads
from service.utils import (
    convert_message_content_to_string,
    ensure_model_available,
    langchain_to_chat_message,
    messages_from_checkpoint,
    remove_tool_calls,
)

logger = logging.getLogger(__name__)

# 过滤 LangChain beta 特性告警，避免日志噪音
warnings.filterwarnings("ignore", category=LangChainBetaWarning)


def custom_generate_unique_id(route: APIRoute) -> str:
    """用函数名作为 OpenAPI operationId。"""
    return route.name


def _resolve_agent(agent_id: str) -> Any:
    """按路径取 agent 图；未注册时返回 404，避免 KeyError 变成 500。"""
    if agent_id not in agent_registry:
        raise not_found(CODE_UNKNOWN_AGENT, f"Unknown agent: {agent_id}")
    return get_agent(agent_id)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """启动时初始化追踪、建表，并把 checkpointer / store 挂到各 agent。"""
    if settings.export_langsmith_env():
        if settings.LANGCHAIN_API_KEY:
            logger.info(
                "LangSmith tracing enabled (project=%s, endpoint=%s)",
                settings.LANGCHAIN_PROJECT,
                settings.LANGCHAIN_ENDPOINT,
            )
        else:
            logger.warning("LANGCHAIN_TRACING_V2 已开启但缺少 LANGCHAIN_API_KEY，追踪将无法上报")
    else:
        logger.debug("LangSmith tracing disabled")

    init_db()
    async with initialize_database() as saver, initialize_store() as store:
        if hasattr(saver, "setup"):
            await saver.setup()
        for a in get_all_agent_info():
            agent = get_agent(a.key)
            agent.checkpointer = saver
            agent.store = store
            logger.info("Agent configured with checkpointer: %s", a.key)
        yield


app = FastAPI(lifespan=lifespan, generate_unique_id_function=custom_generate_unique_id)

_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter()


@router.get("/info")
async def info() -> ServiceMetadata:
    models = list(settings.AVAILABLE_MODELS)
    models.sort()
    return ServiceMetadata(
        agents=get_all_agent_info(),
        models=models,
        default_agent=DEFAULT_AGENT,
        default_model=settings.DEFAULT_MODEL,
    )


def _check_thread_owner(metadata: Mapping[str, Any] | None, user_id: str, agent_id: str) -> None:
    """校验 thread 归属，不匹配时按「不存在」处理，避免泄漏他人会话是否存在。

    thread_id 由客户端提供，等同于 bearer capability：若不校验，拿到别人的 thread_id
    即可读取并续写其会话。新建 thread 尚无 checkpoint（metadata 为空）时放行。
    """
    if not metadata:
        return
    if metadata.get("user_id") != user_id or metadata.get("agent_id") != agent_id:
        raise not_found(CODE_THREAD_NOT_FOUND, "对话不存在")


async def _handle_input(
    user_input: UserInput, agent: Any, agent_id: str, user_id: str
) -> tuple[dict[str, Any], str]:
    """组装 agent 调用参数，并处理 interrupt 恢复；返回 (kwargs, run_id)。"""
    run_id = uuid4()
    thread_id = user_input.thread_id or str(uuid4())

    configurable: dict[str, Any] = {"thread_id": thread_id, "user_id": user_id}
    if user_input.model is not None:
        ensure_model_available(user_input.model)
        configurable["model"] = user_input.model

    if user_input.agent_config:
        reserved_keys = {"thread_id", "user_id", "model"}
        if overlap := reserved_keys & user_input.agent_config.keys():
            raise bad_request(
                CODE_INVALID_CONFIG, f"agent_config contains reserved keys: {overlap}"
            )
        configurable.update(user_input.agent_config)

    config = RunnableConfig(
        configurable=configurable,
        metadata={
            "user_id": user_id,
            "agent_id": agent_id,
            "prompt_set_version": PROMPT_SET_VERSION,
        },
        run_id=run_id,
    )

    state = await agent.aget_state(config=config)
    # 先校验归属再决定是否恢复/续写，防止他人 thread 被读取或追加
    _check_thread_owner(state.metadata, user_id, agent_id)
    interrupted_tasks = [
        task for task in state.tasks if hasattr(task, "interrupts") and task.interrupts
    ]

    input: Command | dict[str, Any]
    if interrupted_tasks:
        input = Command(resume=user_input.message)
    else:
        input = {"messages": [HumanMessage(content=user_input.message)]}

    return {"input": input, "config": config}, str(run_id)


@router.post("/{agent_id}/invoke", operation_id="invoke_with_agent_id")
@router.post("/invoke")
async def invoke(
    user_input: UserInput,
    current_user: User = Depends(get_current_user),
    agent_id: str = DEFAULT_AGENT,
) -> ChatMessage:
    """单次调用 agent，返回最后一条消息。

    未指定 agent_id 时使用默认 agent；路径形式为 `/{agent_id}/invoke`。
    """
    agent = _resolve_agent(agent_id)
    kwargs, run_id = await _handle_input(user_input, agent, agent_id, str(current_user.id))
    try:
        response_events: list[tuple[str, Any]] = await agent.ainvoke(**kwargs, stream_mode=["updates", "values"])  # type: ignore[no-matching-overload]  # fmt: skip
        response_type, response = response_events[-1]
        if "__interrupt__" in response:
            output = langchain_to_chat_message(
                AIMessage(content=response["__interrupt__"][0].value)
            )
        elif response_type == "values":
            output = langchain_to_chat_message(response["messages"][-1])
        else:
            raise ValueError(f"Unexpected response type: {response_type}")
        output.run_id = run_id
        return output
    except Exception as e:
        logger.error("Invoke failed: %s", e)
        raise internal_error("Unexpected error") from e


async def message_generator(
    user_input: StreamInput, agent: Any, kwargs: dict[str, Any], run_id: str
) -> AsyncGenerator[str, None]:
    """SSE 消息生成器：区分 token 流与 message 流。

    agent / kwargs / run_id 由路由预先解析后传入 —— 这样鉴权失败、model 不可用等错误
    能在流开始前以正常的 HTTP 状态码返回，而不是变成流中途断开。
    """
    try:
        async for stream_event in agent.astream(  # type: ignore[no-matching-overload]
            **kwargs, stream_mode=["updates", "messages", "custom"], subgraphs=True
        ):
            if not isinstance(stream_event, tuple):
                continue
            if len(stream_event) == 3:
                _, stream_mode, event = stream_event
            else:
                stream_mode, event = stream_event

            new_messages: list[Any] = []
            if stream_mode == "updates":
                for node, updates in event.items():
                    if node == "__interrupt__":
                        for interrupt in updates:
                            new_messages.append(AIMessage(content=interrupt.value))
                        continue
                    updates = updates or {}
                    update_messages = updates.get("messages", [])
                    if "supervisor" in node or "sub-agent" in node:
                        if update_messages and isinstance(update_messages[-1], ToolMessage):
                            if "sub-agent" in node and len(update_messages) > 1:
                                update_messages = update_messages[-2:]
                            else:
                                update_messages = [update_messages[-1]]
                        else:
                            update_messages = []
                    new_messages.extend(update_messages)
            elif stream_mode == "custom":
                # CustomData.dispatch 写出的 LangChain ChatMessage(role=custom)
                new_messages = [event]

            processed_messages = []
            current_message: dict[str, Any] = {}
            for message in new_messages:
                if isinstance(message, tuple):
                    key, value = message
                    current_message[key] = value
                else:
                    if current_message:
                        processed_messages.append(_create_ai_message(current_message))
                        current_message = {}
                    processed_messages.append(message)
            if current_message:
                processed_messages.append(_create_ai_message(current_message))

            for message in processed_messages:
                try:
                    chat_message = langchain_to_chat_message(message)
                    chat_message.run_id = run_id
                except Exception as e:
                    logger.error("Error parsing message: %s", e)
                    yield f"data: {json.dumps({'type': 'error', 'content': 'Unexpected error'})}\n\n"
                    continue
                if chat_message.type == "human" and chat_message.content == user_input.message:
                    continue
                yield f"data: {json.dumps({'type': 'message', 'content': chat_message.model_dump()})}\n\n"

            if stream_mode == "messages":
                if not user_input.stream_tokens:
                    continue
                msg, metadata = event
                if "skip_stream" in metadata.get("tags", []):
                    continue
                if not isinstance(msg, AIMessageChunk):
                    continue
                content = remove_tool_calls(msg.content)
                if content:
                    yield f"data: {json.dumps({'type': 'token', 'content': convert_message_content_to_string(content)})}\n\n"
    except Exception as e:
        logger.error("Error in message generator: %s", e)
        yield f"data: {json.dumps({'type': 'error', 'content': 'Internal server error'})}\n\n"
    finally:
        yield "data: [DONE]\n\n"


def _create_ai_message(parts: dict) -> AIMessage:
    sig = inspect.signature(AIMessage)
    valid_keys = set(sig.parameters)
    filtered = {k: v for k, v in parts.items() if k in valid_keys}
    return AIMessage(**filtered)


def _sse_response_example() -> dict[int | str, Any]:
    return {
        status.HTTP_200_OK: {
            "description": "Server Sent Event Response",
            "content": {
                "text/event-stream": {
                    "example": "data: {'type': 'token', 'content': 'Hello'}\n\ndata: [DONE]\n\n",
                    "schema": {"type": "string"},
                }
            },
        }
    }


@router.post(
    "/{agent_id}/stream",
    response_class=StreamingResponse,
    responses=_sse_response_example(),
    operation_id="stream_with_agent_id",
)
@router.post("/stream", response_class=StreamingResponse, responses=_sse_response_example())
async def stream(
    user_input: StreamInput,
    current_user: User = Depends(get_current_user),
    agent_id: str = DEFAULT_AGENT,
) -> StreamingResponse:
    """流式返回 agent 响应（含中间消息与 token）。

    未指定 agent_id 时使用默认 agent；路径形式为 `/{agent_id}/stream`。
    """
    agent = _resolve_agent(agent_id)
    # 先解析参数（含归属校验），再开始流，保证错误以 4xx 返回而非流中断
    kwargs, run_id = await _handle_input(user_input, agent, agent_id, str(current_user.id))
    return StreamingResponse(
        message_generator(user_input, agent, kwargs, run_id),
        media_type="text/event-stream",
    )


@router.post("/{agent_id}/history", operation_id="history_with_agent_id")
@router.post("/history")
async def history(
    input: ChatHistoryInput,
    current_user: User = Depends(get_current_user),
    agent_id: str = DEFAULT_AGENT,
) -> ChatHistory:
    """获取某 thread 的会话历史。

    未指定 agent_id 时使用默认 agent；路径形式为 `/{agent_id}/history`。
    """
    agent = _resolve_agent(agent_id)
    config = RunnableConfig(configurable={"thread_id": input.thread_id})
    try:
        checkpointer = getattr(agent, "checkpointer", None)
        tup = await checkpointer.aget_tuple(config) if checkpointer else None
        # thread_id 来自客户端，必须校验归属后才能返回内容
        _check_thread_owner(tup.metadata if tup else None, str(current_user.id), agent_id)

        messages: list[BaseMessage] = []
        if tup is not None and "__previous__" in (tup.checkpoint.get("channel_values") or {}):
            messages = messages_from_checkpoint(tup.checkpoint)
        if not messages:
            state_snapshot = await agent.aget_state(config=config)
            messages = state_snapshot.values["messages"]
        return ChatHistory(messages=[langchain_to_chat_message(m) for m in messages])
    except HTTPException:
        raise  # 归属校验的 404 不能被下面的兜底 except 吞成 500
    except Exception as e:
        logger.error("History failed: %s", e)
        raise internal_error("Unexpected error") from e


@router.get("/{agent_id}/threads", operation_id="threads_with_agent_id")
@router.get("/threads")
async def threads(
    input: UserThreadsInput = Depends(),
    current_user: User = Depends(get_current_user),
    agent_id: str = DEFAULT_AGENT,
) -> UserThreads:
    """列出当前用户的会话线程。

    未指定 agent_id 时使用默认 agent；路径形式为 `/{agent_id}/threads`。
    """
    agent = _resolve_agent(agent_id)
    checkpointer = getattr(agent, "checkpointer", None)
    if not checkpointer:
        return UserThreads(threads=[])
    try:
        summaries = await list_user_threads(
            checkpointer, str(current_user.id), agent_id, input.limit
        )
    except Exception as e:
        logger.error("Threads failed: %s", e)
        raise internal_error("Unexpected error") from e
    return UserThreads(threads=summaries)


@router.post("/questions/generate", response_model=QuestionResponse)
async def generate_questions(
    req: QuestionRequest, current_user: User = Depends(get_current_user)
) -> QuestionResponse:
    """出题：基于题库与知识库生成**结构化**练习题。

    返回结构化而非整页 Markdown，是为了让前端把「单题题干 + 该题标准答案」原样交给
    批改端点 —— 否则批改只能拿到一份含答案的整页文本。

    生成核心与聊天出题共用 `agenerate_question_set`（HTTP 契约不变）。
    """
    try:
        result = await agenerate_question_set(
            topic=req.topic, count=req.count, difficulty=req.difficulty
        )
    except Exception as e:
        logger.error("Question generation failed: %s", e)
        raise internal_error("出题失败", CODE_GENERATE_FAILED) from e
    return QuestionResponse(questions=result.questions, batch_id=str(uuid4()))


@router.post("/questions/grade", response_model=GradeResponse)
async def grade_question(
    req: GradeRequest, current_user: User = Depends(get_current_user)
) -> GradeResponse:
    """批改：基于题干与标准答案给出评分与反馈。

    评分实现见 `agents.grading_core`；本路由只做 HTTP 映射（契约不变）。
    """
    try:
        result = await agrade_answer(
            stem=req.stem,
            user_answer=req.user_answer,
            standard_answer=req.standard_answer or "",
        )
    except Exception as e:
        logger.error("Grading failed: %s", e)
        raise internal_error("批改失败", CODE_GRADE_FAILED) from e
    return GradeResponse(
        score=float(result.score),
        feedback=result.feedback,
        error_analysis=result.error_analysis or "",
    )


@app.get("/health")
async def health_check() -> dict[str, Any]:
    """健康检查：返回各外部依赖状态。

    永远返回 200（该端点同时被 Docker healthcheck 使用），整体状态放在 body 的 status 字段。
    """
    return await collect_health()


app.include_router(auth_router, prefix="/api")
app.include_router(router, prefix="/api")

# 静态前端（纯 HTML/CSS/JS）：挂在根路径，/api 路由优先级更高
STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
