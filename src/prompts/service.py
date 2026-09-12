"""service 层（HTTP 端点）的出题与批改模板。

层级提醒：这两个模板属于**端点直调**，经 `agents.question_core` / `agents.grading_core`
使用，与 `prompts/agents.py` 里聊天专家的 system prompt 是两套东西。
`/api/questions/grade` 走 `GRADE_PROMPT` + `grading_core`，**不经过 grading_agent**，
因此 `GRADING_AGENT_SYSTEM_PROMPT` 在该路径上不生效。
"""

from langchain_core.prompts import ChatPromptTemplate

# 出题：human 一条即可；结构化 system 在 question_gen_agent
# （QUESTION_GEN_STRUCTURED_SYSTEM_PROMPT），此处不重复。
QUESTION_GEN_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "human",
            "请生成 {count} 道关于「{topic}」的练习题，难度：{difficulty}。"
            "每题给出题干、标准答案与简明解析。",
        )
    ]
)

# 批改：评分规则进 system；学生答案是**不可信输入**，必须留在 human ——
# 结构上把「指令」与「数据」分开，避免答案内容被当成指令执行。
GRADE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "批改 408 考研题目作答并输出结构化结果。\n"
            "评分 0-100；若学生答错（score<60）需填写 error_analysis 分析错因与改进建议。",
        ),
        ("human", "题干：{stem}\n标准答案：{standard_answer}\n学生答案：{user_answer}"),
    ]
)
