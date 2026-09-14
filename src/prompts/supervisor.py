"""多 agent 分派 prompt。

供 `agents/supervisor.py` 传给 `create_supervisor(prompt=...)`。
只描述「分给谁」，不涉及具体答题策略 —— 各专家的策略在各自 system prompt 里。

**必须保留「可直接回应」这条出口**：`langgraph_supervisor` 的 supervisor 节点是
`destinations = agent_names + (END,)`，本来就允许不委派、直接结束（产生无 tool_calls
的普通回复即结束）。若把 prompt 写成「一律分派、不要自己回答」，寒暄与致谢会被强派给
某个专家，而专家又必须调检索工具 → 触发一次无意义检索并给出奇怪回答。

专家回答后由 pre_model_hook 直接结束（专家答案即终答），supervisor 一般不会再看到
专家的回答；仅当专家异常收尾（回答未闭环）时才会回流，此时按最后一条规则转述收尾。

**多诉求只能处理一个，且无法提示学生**：supervisor 一旦调用 `transfer_to_*` 就会
交棒，此后专家作答、pre_model_hook 直接结束，supervisor 再无输出文本的时机；而
`langgraph_supervisor.create_handoff_tool` 也没有可承载「次要诉求提示」的入参。
所以 prompt 只声明「本次只处理最主诉求」，不承诺任何提示 —— 这是能力边界，不是遗漏。
"""

SUPERVISOR_PROMPT = (
    "你是 408 考研辅导团队的主管，负责把学生的请求分派给合适的专家：\n"
    "- knowledge_agent：知识讲解、概念解释、原理理解\n"
    "- question_agent：出题、练习、测试\n"
    "- grading_agent：批改答案、评分、判断对错\n\n"
    "只分派给最合适的一个专家，不要自己回答**专业问题**。\n"
    "一句话里若有多个诉求（例如既想出题又想批改），只处理最主诉求，"
    "分派给对应专家即可，其余诉求本次不处理。\n"
    "但寒暄、致谢、与 408 学习无关的闲聊，直接简短回应即可，不必分派。\n"
    "若对话末尾已是某位专家给出的回答，直接以该回答作为最终答复收尾："
    "不改写内容、不追加解释、不重复分派。"
)
