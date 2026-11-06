"""教学图状态定义与执行结果推断。

MVP 只定义两张 Schema：

- ``TeachingState``：外层教学图，普通 TypedDict，不继承 AgentState（不需要 ReAct 托管值）。
- ``SupervisorState``：内层 Supervisor，必须继承 prebuilt ``AgentState``（含 remaining_steps）。

命名避坑：``schema.task_policy.TaskMode`` 是**检索策略词表**（learn/method/…），
本模块的 ``TaskKind`` 是**业务任务词表**（chat/question/…），两者不可混用。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, NotRequired, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langgraph.graph.message import add_messages
from langgraph.prebuilt.chat_agent_executor import AgentState as SupervisorBase

from schema.task_policy import TaskMode as RetrievalMode

TaskKind = Literal["chat", "question", "grading", "knowledge", "unknown"]
TaskStatus = Literal["pending", "completed", "failed"]
ErrorStage = Literal["prepare", "supervisor", "finalize"]


class TaskError(TypedDict):
    """业务任务失败信息。四个键都是原始类型，可直接进 checkpoint。"""

    code: str
    message: str
    stage: ErrorStage
    recoverable: bool


class TeachingState(TypedDict):
    """外层教学图状态。只在教学图里流转，不透传给内层 supervisor。"""

    messages: Annotated[list[AnyMessage], add_messages]
    task_id: NotRequired[str]
    task_mode: NotRequired[TaskKind]
    task_context: NotRequired[dict[str, Any]]
    context_mode: NotRequired[RetrievalMode | None]
    active_agent: NotRequired[str | None]
    task_status: NotRequired[TaskStatus]
    # MVP 不写此字段（结构化结果回传暂缓），保留 channel 以便后续启用。
    task_result: NotRequired[dict[str, Any] | None]
    error: NotRequired[TaskError | None]


class SupervisorState(SupervisorBase):
    """内层 Supervisor 状态。继承 prebuilt AgentState 以获得 remaining_steps。"""

    task_context: NotRequired[dict[str, Any]]
    context_mode: NotRequired[RetrievalMode | None]
    task_result: NotRequired[dict[str, Any] | None]


_KNOWN_AGENTS = frozenset({"knowledge_agent", "question_agent", "grading_agent"})

# 专家名 → 业务类型：best-effort，仅在没有结构化结果时使用。
_AGENT_HINT: dict[str, TaskKind] = {
    "knowledge_agent": "knowledge",
    "question_agent": "question",
    "grading_agent": "grading",
}

# 结构化结果 kind → 业务类型：权威信号（MVP 暂不产生，保留给后续启用）。
_RESULT_KIND_TO_TASK: dict[str, TaskKind] = {
    "grading": "grading",
    "question_set": "question",
}

# create_supervisor 会给 supervisor 自己的 AIMessage 打上这个 name（不是 None）。
# 实测：fake 模型直答时末条是 AIMessage(name="supervisor")。
_SUPERVISOR_NAME = "supervisor"


class ExecutionInference(TypedDict):
    active_agent: str | None
    task_mode: TaskKind


def last_ai_message(messages: list[AnyMessage]) -> AIMessage | None:
    """尾部最近一条实质 AI 消息，跳过连续 ToolMessage。

    ``output_mode="last_message"`` 在末条是 ToolMessage 时会保留两条，故不能直接取 [-1]。
    """
    for message in reversed(messages):
        if isinstance(message, ToolMessage):
            continue
        return message if isinstance(message, AIMessage) else None
    return None


def infer_execution(
    messages: list[AnyMessage],
    *,
    task_result: dict[str, Any] | None = None,
    run_ok: bool = True,
) -> ExecutionInference:
    """从一次已结束的内层运行中，独立推断 active_agent 与 task_mode。

    ``active_agent`` 只回答"谁执行了"，``task_mode`` 只回答"这是什么业务"，
    两个字段分别赋值，不通过前者推导后者。
    """
    tail = last_ai_message(messages)

    if not run_ok or tail is None or tail.name not in _KNOWN_AGENTS:
        active_agent: str | None = None
    else:
        active_agent = tail.name

    if not run_ok:
        task_mode: TaskKind = "unknown"
    elif task_result is not None:
        # 权威信号；未知 kind 不猜，归 unknown。
        task_mode = _RESULT_KIND_TO_TASK.get(str(task_result.get("kind")), "unknown")
    elif tail is None:
        task_mode = "unknown"
    elif tail.name is None or tail.name == _SUPERVISOR_NAME:
        # supervisor 自己的直答：name 可能是 None，也可能是 "supervisor"（实测后者）
        task_mode = "chat"
    else:
        task_mode = _AGENT_HINT.get(tail.name, "unknown")

    return {"active_agent": active_agent, "task_mode": task_mode}


def has_final_answer(messages: list[AnyMessage]) -> bool:
    """本轮是否产出了可返回的终答（用于 finalize 判定 completed）。

    只看尾部：若最后一条实质消息不是带内容的 AI 消息（例如只剩用户消息），
    说明本轮没有产出，不能因为"跑到了 finalize"就算完成。
    """
    tail = last_ai_message(messages)
    return tail is not None and bool(str(tail.content).strip())
