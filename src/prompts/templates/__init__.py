"""Prompt 模板层（第2层）。

集中存放 ChatPromptTemplate：把第1层的静态 System Prompt 与动态业务变量
组合成消息列表。使用方式分两种：

- Supervisor 模板由 `create_supervisor(prompt=...)` 直接消费，消息由 LangGraph 填充；
- 批改 / 出题模板由 `prompts.service` 准备变量后调用 `format_messages()`。

- `supervisor.py`：Supervisor 路由模板（对话历史）
- `grading.py`   ：批改模板（题干 / 标准答案 / 学生答案）
- `question.py`  ：出题模板（主题 / 数量 / 难度）
"""

from prompts.templates.grading import GRADE_PROMPT
from prompts.templates.question import QUESTION_GEN_PROMPT
from prompts.templates.supervisor import SUPERVISOR_PROMPT_TEMPLATE

__all__ = [
    "GRADE_PROMPT",
    "QUESTION_GEN_PROMPT",
    "SUPERVISOR_PROMPT_TEMPLATE",
]
