"""Prompt 模板层（第2层）。

将第1层的纯字符串 System Prompt 与动态业务变量组合成
ChatPromptTemplate，负责把静态提示词与运行时上下文
（如对话历史）结合成消息列表。

说明：三个专业 Agent 的动态数据由 LangGraph 以 messages 直接传入，
不需要额外的 HumanMessage 模板；批改/出题的动态模板由
`prompts.service`（GRADE_PROMPT / QUESTION_GEN_PROMPT）在 core 节点中
用 `format_messages()` 组装，避免在此重复定义。
"""

from prompts.templates.supervisor import SUPERVISOR_PROMPT_TEMPLATE

__all__ = [
    "SUPERVISOR_PROMPT_TEMPLATE",
]
