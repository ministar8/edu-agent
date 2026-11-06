"""Question Prompt 模板层（第2层）。

调用链：
  `question_core.agenerate_question_set` → `prompts.service.build_question_gen_messages`
  → `QUESTION_GEN_PROMPT.format_messages()`。

其配套的静态 System Prompt 见 `prompts.agents.question`。
"""

from langchain_core.prompts import ChatPromptTemplate

QUESTION_GEN_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "human",
            "请生成 {count} 道关于「{topic}」的练习题，难度：{difficulty}。"
            "每题给出题干、标准答案与简明解析。",
        )
    ]
)
