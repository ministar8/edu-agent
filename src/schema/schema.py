from datetime import datetime
from typing import Any, Literal, NotRequired

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class AgentInfo(BaseModel):
    """可用 agent 的信息。"""

    key: str = Field(description="Agent key。", examples=["edu-assistant"])
    description: str = Field(description="Agent 描述。", examples=["408 考研智能辅导助手"])


class ServiceMetadata(BaseModel):
    """服务元数据：可用 agents 与 models。"""

    agents: list[AgentInfo] = Field(description="可用 agent 列表。")
    models: list[str] = Field(description="可用 LLM 标识（<gateway>:<model_id>）。")
    default_agent: str = Field(description="未指定时使用的默认 agent。", examples=["edu-assistant"])
    default_model: str = Field(description="未指定时使用的默认模型。")


class UserInput(BaseModel):
    """agent 的基础用户输入。"""

    message: str = Field(
        max_length=20000,
        description="用户输入。上限 20000 字符 —— 它会直接进入 agent 上下文，需在入口拦住。",
        examples=["什么是虚拟内存？"],
    )
    model: str | None = Field(
        title="Model",
        description="使用的 LLM 标识（<gateway>:<model_id>），缺省用服务默认模型。",
        default=None,
        examples=["dashscope:qwen3.7-max"],
    )
    thread_id: str | None = Field(
        description="多轮对话的 thread ID。",
        default=None,
        examples=["847c6285-8fc9-4560-a83f-4e6285809254"],
    )
    user_id: str | None = Field(
        description="用户 ID（跨线程关联会话）。",
        default=None,
        examples=["847c6285-8fc9-4560-a83f-4e6285809254"],
    )
    agent_config: dict[str, Any] = Field(
        description="透传给 agent 的附加配置。",
        default={},
    )


class StreamInput(UserInput):
    """流式输入，追加 token 流开关。"""

    stream_tokens: bool = Field(description="是否流式输出 LLM token。", default=True)


class ToolCall(TypedDict):
    name: str
    args: dict[str, Any]
    id: str | None
    type: NotRequired[Literal["tool_call"]]


class ChatMessage(BaseModel):
    """聊天消息。"""

    type: Literal["human", "ai", "tool"] = Field(
        description="消息角色。",
        examples=["human", "ai", "tool"],
    )
    content: str = Field(description="消息内容。", examples=["Hello, world!"])
    tool_calls: list[ToolCall] = Field(description="消息中的工具调用。", default=[])
    tool_call_id: str | None = Field(description="此消息响应的工具调用 ID。", default=None)
    run_id: str | None = Field(description="消息的 run ID。", default=None)
    response_metadata: dict[str, Any] = Field(description="响应元数据。", default={})

    def pretty_repr(self) -> str:
        base_title = self.type.title() + " Message"
        padded = " " + base_title + " "
        sep_len = (80 - len(padded)) // 2
        sep = "=" * sep_len
        second_sep = sep + "=" if len(padded) % 2 else sep
        title = f"{sep}{padded}{second_sep}"
        return f"{title}\n\n{self.content}"

    def pretty_print(self) -> None:
        print(self.pretty_repr())  # noqa: T201


class ChatHistoryInput(BaseModel):
    """拉取会话历史的输入。"""

    thread_id: str = Field(description="多轮对话的 thread ID。")


class ChatHistory(BaseModel):
    messages: list[ChatMessage]


class UserThreadsInput(BaseModel):
    """列出用户会话线程的输入。"""

    user_id: str = Field(description="要列线程的用户 ID。")
    limit: int = Field(description="返回线程数上限。", default=20, ge=1, le=100)


class ThreadSummary(BaseModel):
    """单个会话线程摘要。"""

    thread_id: str = Field(description="会话 thread ID。")
    agent_id: str = Field(description="该线程使用的 agent。")
    updated_at: datetime | None = Field(description="最近一次 checkpoint 时间。", default=None)
    title: str | None = Field(description="线程标题，取首条用户消息。", default=None)


class UserThreads(BaseModel):
    threads: list[ThreadSummary]
