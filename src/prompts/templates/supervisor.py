"""Supervisor Agent Prompt 模板层。

将第1层的静态 System Prompt 与动态对话历史组合，
构建 LangGraph Supervisor 节点所需的消息列表。

调用点：`agents/orchestration/supervisor.py` → `create_supervisor(prompt=SUPERVISOR_PROMPT_TEMPLATE)`。
"""

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from prompts.supervisor import SUPERVISOR_PROMPT

# Supervisor 模板：系统提示词 + 对话历史占位符
# 对话历史由 LangGraph 自动填充，包含之前的专家回答和用户输入
SUPERVISOR_PROMPT_TEMPLATE = ChatPromptTemplate.from_messages([
    ("system", SUPERVISOR_PROMPT),
    MessagesPlaceholder(variable_name="messages"),
])
