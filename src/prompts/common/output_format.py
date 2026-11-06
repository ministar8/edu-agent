"""输出格式约束。

适用场景：输出面向用户文本的 Agent（knowledge_agent / question_agent / grading_agent）。
Supervisor 作为路由主管，不输出面向用户文本，因此不引入本规则。

与 JSON_ONLY_RULE 的关系：OUTPUT_FORMAT_RULES 是通用约束（不得 Markdown 代码块、不得引导语等），
JSON_ONLY_RULE 是 JSON 专用的更严格变体（只输出合法 JSON）。两者可同时引入，无冲突。

- 不得输出 Markdown 代码块标记（如 ```json）。
- 不得输出引导语（如「以下是答案：」「这里是结果：」）。
- 不得包含与任务无关的闲聊或自我介绍。
- 必须使用中文回答。
"""

OUTPUT_FORMAT_RULES = """【输出格式要求】
- 不得输出 Markdown 代码块标记（如 ```json）。
- 不得输出引导语（如「以下是答案：」「这里是结果：」）。
- 不得包含与任务无关的闲聊或自我介绍。
- 必须使用中文回答。
"""
