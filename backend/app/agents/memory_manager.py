from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

def build_scoped_context(
    current_query: str,
    knowledge_context: str = "",
) -> list[BaseMessage]:
    context: list[BaseMessage] = []

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


def extract_current_query(messages: list[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            return content
    return ""
