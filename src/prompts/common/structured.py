"""结构化输出约束。

适用场景：需要结构化输出的 Agent（question_agent / grading_agent）。
知识 Agent 讲解知识、Supervisor 做路由，不需要结构化输出，因此不引入本规则。

STRUCTURED_OUTPUT_RULE 与 JSON_ONLY_RULE 的区别：
- STRUCTURED_OUTPUT_RULE：强调“可被解析为结构化数据、字段名严格按约定”，适用于有明确字段定义的输出（如出题、批改）。
- JSON_ONLY_RULE：强调“只输出合法 JSON、无自然语言包装”，适用于需要纯 JSON 响应的场景（目前暂无 Agent 使用）。
"""

STRUCTURED_OUTPUT_RULE = """【结构化输出】
- 最终输出必须可被解析为结构化数据，不要夹带自然语言包装。
- 字段名必须严格按照约定，不要自行增减或改名。
"""

JSON_ONLY_RULE = """【JSON 仅输出】
只输出合法 JSON，不要包含 Markdown 代码块标记，不要输出任何自然语言包装。
"""
