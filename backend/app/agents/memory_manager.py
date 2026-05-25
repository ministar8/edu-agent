from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage


def _truncate(text: str, limit: int = 200) -> str:
    """截断文本到指定字数"""
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def build_scoped_context(
    current_query: str,
    knowledge_context: str = "",
    conversation_history: str = "",
) -> list[BaseMessage]:
    context: list[BaseMessage] = []

    if conversation_history:
        context.append(SystemMessage(
            content=(
                "【对话历史】以下是本会话中之前的对话内容，请结合历史上下文理解当前问题：\n\n"
                f"{conversation_history}\n"
                "---"
            )
        ))

    if knowledge_context:
        context.append(SystemMessage(
            content=(
                "【知识库检索结果】\n"
                "以下是系统为你预先检索到的相关知识内容，请结合这些内容完成任务：\n\n"
                f"{knowledge_context}"
            )
        ))

    context.append(HumanMessage(content=current_query))
    return context


def format_history_from_messages(messages: list[BaseMessage], max_turns: int = 6) -> str:
    """从 LangChain messages 列表中提取历史轮次，格式化为文本

    跳过 SystemMessage，将 HumanMessage/AIMessage 配对为轮次。
    只取最近 max_turns 轮，每条截断至 200 字。
    """
    # 提取 user/assistant 对
    pairs: list[tuple[str, str]] = []
    pending_user: str | None = None

    for msg in messages:
        # LangGraph 可能传入 tuple 格式 ("user"/"assistant", "text")
        if isinstance(msg, tuple) and len(msg) >= 2:
            role, content = msg[0], str(msg[1])
            if role == "user":
                pending_user = content
            elif role == "assistant" and pending_user is not None:
                pairs.append((pending_user, content))
                pending_user = None
            continue
        if isinstance(msg, SystemMessage):
            continue
        if isinstance(msg, HumanMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            pending_user = content
        elif isinstance(msg, AIMessage) and pending_user is not None:
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            pairs.append((pending_user, content))
            pending_user = None

    # 只保留最近 max_turns 轮
    pairs = pairs[-max_turns:]

    if not pairs:
        return ""

    lines: list[str] = []
    for user_msg, assistant_msg in pairs:
        lines.append(f"用户问：{_truncate(user_msg)}")
        lines.append(f"系统答：{_truncate(assistant_msg)}")

    return "\n".join(lines)


def extract_current_query(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        # LangGraph 可能传入 tuple 格式 ("user", "text")
        if isinstance(msg, tuple) and len(msg) >= 2 and msg[0] == "user":
            return str(msg[1])
        if isinstance(msg, HumanMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            return content
    return ""


# ── 增量合并摘要 ─────────────────────────────────────────────

_SUMMARIZE_PROMPT = """请将以下对话内容合并为一份简洁的摘要。
保留所有关键知识点、用户关注点和讨论脉络，不超过300字。

{existing_summary}

新增对话内容：
{new_messages}

请输出合并后的更新摘要："""


async def summarize_messages(
    new_messages: list[dict],
    existing_summary: str = "",
) -> str:
    """增量合并摘要：旧 summary + 新一批消息 → LLM → 更新 summary

    Args:
        new_messages: [{"role": "user"|"assistant", "content": "..."}]
        existing_summary: 已有的旧摘要（空字符串表示首次摘要）
    """
    from app.rag.rag_utils import get_llm

    # 格式化新消息
    new_text = "\n".join(
        f"{'用户' if m['role'] == 'user' else '系统'}：{_truncate(m['content'], limit=150)}"
        for m in new_messages
    )

    existing_part = f"已有摘要：\n{existing_summary}" if existing_summary else "（这是首次摘要，没有已有摘要）"

    prompt = _SUMMARIZE_PROMPT.format(
        existing_summary=existing_part,
        new_messages=new_text,
    )

    llm = get_llm()
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    content = response.content if hasattr(response, "content") else str(response)
    return content.strip()


def should_trigger_summary(message_count: int, window: int = 12) -> bool:
    """判断是否应触发摘要：每 window 条消息触发一次"""
    return message_count >= window and message_count % window == 0
