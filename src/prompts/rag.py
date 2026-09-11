"""RAG 层单轮任务模板。

四者都是**单轮调用**（无对话历史），统一把「指令」放 SystemMessage、「数据」放 HumanMessage ——
检索证据属于不可信输入，结构上必须与指令分属不同角色。

调用点：
  - HYDE_PROMPT       → rag/hyde.py
  - CLASSIFY_PROMPT   → rag/query_classifier.py
  - DECOMPOSE_PROMPT  → rag/query_decomposer.py
  - RELEVANCE_PROMPT  → rag/verifier.py
"""

from langchain_core.prompts import ChatPromptTemplate

HYDE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "你是 408 考研教材知识库检索增强器。根据学生问题生成一段可能出现在教材中的、"
            "用于向量检索的假设性知识片段。\n"
            "要求：\n"
            "- 只写客观教材风格内容，不要回答用户\n"
            "- 不要编造章节、页码、题号或来源\n"
            "- 保留关键术语和同义表达",
        ),
        ("human", "学生问题：{query}\n\n请生成一段不超过 {max_chars} 字的假设性知识片段。"),
    ]
)

CLASSIFY_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "判断学生问题的查询意图类别（可多选）。\n"
            "可选标签：code, exercise, answer, structured, concept, comparison, learning_path\n"
            "如果没有匹配的类别，返回 uncategorized。",
        ),
        ("human", "问题：{query}"),
    ]
)

DECOMPOSE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "将 408 考研问题拆分为独立的子问题，每个子问题聚焦单一知识点。\n\n"
            "规则：\n"
            "- 拆分为 2-{max_subs} 个子问题\n"
            "- 每个子问题只涉及一个学科/知识点\n"
            "- 如果问题本身已聚焦单一知识点，返回单元素数组\n"
            "- 子问题应保留原问题中的关键术语\n\n"
            "示例：\n"
            "问题：比较Cache写回法与虚拟存储器的写回策略的异同\n"
            '子问题：["Cache写回法的工作原理", "虚拟存储器写回策略的工作原理", "两者异同对比"]',
        ),
        ("human", "问题：{query}"),
    ]
)

RELEVANCE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "判断检索证据是否与用户查询相关。\n"
            "只输出 JSON，不要其他内容，格式：\n"
            '{{"relevant_count": 数字, "irrelevant_count": 数字, '
            '"completeness": 0-1浮点数, "reason": "简短说明"}}',
        ),
        ("human", "用户查询：{query}\n\n检索证据（前5条）：\n{evidence_list}"),
    ]
)
