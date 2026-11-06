"""长度限制规则。

适用场景：输出面向用户文本的 Agent（knowledge_agent / question_agent / grading_agent）。
Supervisor 作为路由主管，不输出面向用户文本，因此不引入本规则。

- 解析/反馈控制在 100-200 字以内，简明扼要。
- 单条回答总长度不超过 800 字。
"""

LENGTH_LIMIT_RULE = """【长度限制】
- 解析/反馈控制在 100-200 字以内，简明扼要。
- 单条回答总长度不超过 800 字。
"""
