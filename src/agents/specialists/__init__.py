"""专家层公开 API：三个聊天路径 Agent 实例。

- 路径稳定：`from agents.specialists import knowledge_agent, ...`
- **不**导出 core 业务函数（`agenerate_question_set` / `agrade_answer` 等）——
  供 `runtime.tools` 函数内延迟 import，路径不承诺稳定。
- 依赖方向：本包 → `runtime`；禁止 import `orchestration`。
"""

from agents.specialists.grading import grading_agent
from agents.specialists.knowledge import knowledge_agent
from agents.specialists.question import question_agent

__all__ = ["grading_agent", "knowledge_agent", "question_agent"]
