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
    SystemMessage,
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
from memory.remember import record_grade, record_question
from memory.retention import acleanup_all_student_episodes
from memory.runtime import set_store
from memory.safe import safe_remember
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
from service.metrics import collect_metrics
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

# 防御性兜底：langgraph-supervisor 的回传控制消息（英文），不应透传给用户。
#
# 当前 supervisor 装配为 add_handoff_back_messages=False，库不会产生此类消息，
# 因此这段过滤**没有活路径**。保留是为了在配置被改回 / 库版本变更时仍能挡住 ——
# 属于「有备无患」而非「正在生效」的防护，勿据此认为系统依赖它。
_HANDOFF_BACK_PREFIXES = (
    "Transferring back to ",
    "Successfully transferred back to ",
)


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
        set_store(store)
        for a in get_all_agent_info():
            agent = get_agent(a.key)
            agent.checkpointer = saver
            agent.store = store
            logger.info("Agent configured with checkpointer: %s", a.key)
        # 启动时清理过期/超量 episodes；失败不阻断启动
        await safe_remember(lambda: acleanup_all_student_episodes(store), label="episode_retention")
        try:
            yield
        finally:
            set_store(None)


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
async def info(_current_user: User = Depends(get_current_user)) -> ServiceMetadata:
    """服务元数据：可用 agents 与 models。

    **需要认证**：未认证时不应暴露部署结构（agent 清单、模型清单、默认模型）。
    这也让"服务是否在线"不再是匿名可探测的。

    代价是客户端 SDK 不能在构造期拉取（那时还没凭证）——
    `AgentClient.login()` / `register()` 成功后会**自动补齐**，
    所以 `AgentClient(base_url=...)` 的用法不变。

    形参名带下划线：依赖只用于鉴权，值本身不用。
    """
    models = list(settings.AVAILABLE_MODELS)
    models.sort()
    return ServiceMetadata(
        agents=get_all_agent_info(),
        models=models,
        default_agent=DEFAULT_AGENT,
        default_model=settings.DEFAULT_MODEL,
    )


@router.get("/metrics")
async def metrics() -> dict[str, Any]:
    """运行时观测指标：缓存命中率等（JSON）。

    **为什么不放 `/health`**：`/health` 被 Docker healthcheck 使用，
    要并发探测 embedding / reranker / chromadb 三个外部依赖，**必须快**；
    而缓存命中率是**运行统计**不是**依赖健康**，混进去会让 healthcheck
    语义模糊、payload 变重，采集方也可能误判。

    **为什么不是 Prometheus 文本格式**：本项目没有 Prometheus 采集端，
    返回 JSON 便于运维与前端直接查看，也便于测试断言。
    若将来接入 Prometheus，应另开**无前缀**的 `/metrics` 用文本格式，
    避免与这个 JSON 端点冲突。
    """
    return collect_metrics()


def _check_thread_owner(
    metadata: Mapping[str, Any] | None,
    user_id: str,
    agent_id: str,
    *,
    has_history: bool = False,
) -> None:
    """校验 thread 归属，不匹配时按「不存在」处理，避免泄漏他人会话是否存在。

    thread_id 由客户端提供，等同于 bearer capability：若不校验，拿到别人的 thread_id
    即可读取并续写其会话。新建 thread 尚无 checkpoint（metadata 为空且无历史）时放行；
    但若 thread 已有历史却缺 metadata，说明归属信息缺失，同样拒绝。
    """
    if not metadata:
        if has_history:
            raise not_found(CODE_THREAD_NOT_FOUND, "对话不存在")
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
        recursion_limit=settings.AGENT_RECURSION_LIMIT,
        metadata={
            "user_id": user_id,
            "agent_id": agent_id,
            "prompt_set_version": PROMPT_SET_VERSION,
        },
        run_id=run_id,
    )

    state = await agent.aget_state(config=config)
    # 先校验归属再决定是否恢复/续写，防止他人 thread 被读取或追加
    has_history = bool(state.values and state.values.get("messages"))
    _check_thread_owner(state.metadata, user_id, agent_id, has_history=has_history)
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
            output = langchain_to_chat_message(_last_user_visible_message(response["messages"]))
        else:
            raise ValueError(f"Unexpected response type: {response_type}")
        output.run_id = run_id
        return output
    except Exception as e:
        logger.error("Invoke failed: %s", e)
        raise internal_error("Unexpected error") from e


def _last_user_visible_message(messages: list[BaseMessage]) -> BaseMessage:
    """从消息尾部回溯，取最后一条用户可见的消息。

    ``values`` 流的末条消息未必是给用户看的最终回答：专家可能以空 content（或带
    tool_calls 的中间步骤）收尾，直接取 ``messages[-1]`` 会返回空气泡。这里复用 SSE
    侧的可见性判定（``_is_user_visible_message``），与流式路径保持同一口径。

    全部不可见时回退到原始末条，保证返回值类型仍是 BaseMessage、不会返回 None。
    """
    for message in reversed(messages):
        if _is_user_visible_message(message):
            return message
    return messages[-1]


def _is_user_visible_message(message: Any) -> bool:
    """SSE message 流只放行用户可见的对话内容。

    updates 流（含 subgraphs）会把同一最终消息从内层节点（model/agent）与外层包装
    节点各报一次，并夹带路由/工具中间消息：

    - SystemMessage：工作记忆卡，只进模型上下文
    - ToolMessage：工具结果与 handoff 控制消息，不是对话气泡
    - 带 tool_calls 或空内容的 AIMessage：分派决策与中间步骤，不是最终回答
    - 同 ID 消息只发一次（配合 message_generator 里的 seen_ids 去重）
    """
    if isinstance(message, SystemMessage | ToolMessage):
        return False
    if isinstance(message, AIMessage):
        content = message.content
        if not content or (isinstance(content, str) and not content.strip()):
            return False
        if message.tool_calls:
            return False
    return True


async def message_generator(
    user_input: StreamInput, agent: Any, kwargs: dict[str, Any], run_id: str
) -> AsyncGenerator[str, None]:
    """SSE 消息生成器：区分 token 流与 message 流。

    agent / kwargs / run_id 由路由预先解析后传入 —— 这样鉴权失败、model 不可用等错误
    能在流开始前以正常的 HTTP 状态码返回，而不是变成流中途断开。
    """
    # 同一条消息会经内层与外层节点重复上报，按消息 ID 全局去重
    seen_ids: set[str] = set()
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
                        # 生成器代替「for + append」：少 1 判定点（backlog #36 第三步）
                        new_messages.extend(AIMessage(content=i.value) for i in updates)
                        continue
                    # 内层/外层节点统一收集，交给 _is_user_visible_message + ID 去重筛选
                    new_messages.extend((updates or {}).get("messages", []))
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
                if not _is_user_visible_message(message):
                    continue
                msg_id = getattr(message, "id", None)
                if msg_id and msg_id in seen_ids:
                    continue
                if msg_id:
                    seen_ids.add(msg_id)
                try:
                    chat_message = langchain_to_chat_message(message)
                    chat_message.run_id = run_id
                except Exception as e:
                    logger.error("Error parsing message: %s", e)
                    yield f"data: {json.dumps({'type': 'error', 'content': 'Unexpected error'})}\n\n"
                    continue
                if chat_message.type == "human" and chat_message.content == user_input.message:
                    continue
                if chat_message.content.startswith(_HANDOFF_BACK_PREFIXES):
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
        _check_thread_owner(
            tup.metadata if tup else None,
            str(current_user.id),
            agent_id,
            has_history=tup is not None,
        )

        messages: list[BaseMessage] = []
        if tup is not None and "__previous__" in (tup.checkpoint.get("channel_values") or {}):
            messages = messages_from_checkpoint(tup.checkpoint)
        if not messages:
            state_snapshot = await agent.aget_state(config=config)
            messages = state_snapshot.values["messages"]
        # 工作记忆卡（SystemMessage）是内部上下文，且 langchain_to_chat_message 不支持它
        return ChatHistory(
            messages=[
                langchain_to_chat_message(m) for m in messages if not isinstance(m, SystemMessage)
            ]
        )
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
    batch_id = str(uuid4())
    await record_question(
        user_id=str(current_user.id),
        topic=req.topic,
        agent_path="api_question",
        count=req.count,
        batch_id=batch_id,
    )
    return QuestionResponse(questions=result.questions, batch_id=batch_id)


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
    await record_grade(
        user_id=str(current_user.id),
        topic=req.stem[:80],
        score=float(result.score),
        error_analysis=result.error_analysis or "",
        stem=req.stem,
        agent_path="api_grade",
        batch_id=req.batch_id,
        question_id=req.question_id,
    )
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
