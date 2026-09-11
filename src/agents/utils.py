"""Agent 共享工具：自定义流事件等。"""

from typing import Any

from langchain_core.messages import ChatMessage
from langgraph.types import StreamWriter
from pydantic import BaseModel, Field


class CustomData(BaseModel):
    """Agent 通过 custom 流模式下发的结构化数据。"""

    data: dict[str, Any] = Field(description="自定义数据载荷。")

    def to_langchain(self) -> ChatMessage:
        return ChatMessage(content=[self.data], role="custom")

    def dispatch(self, writer: StreamWriter) -> None:
        writer(self.to_langchain())
