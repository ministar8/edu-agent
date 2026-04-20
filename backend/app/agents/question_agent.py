from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.rag.retriever import retrieve_documents, build_rag_context, get_llm


@tool
def search_question_templates(topic: str) -> str:
    """搜索题库中与指定知识点相关的题目模板和例题。当需要生成练习题时使用此工具。"""
    docs = retrieve_documents(topic, collection_name="questions", k=3)
    if not docs:
        return "题库中暂无相关题目模板。"
    return build_rag_context(docs)


QUESTION_AGENT_PROMPT = """你是一个题目生成Agent。

你的职责是：
1. 使用 search_question_templates 工具检索题库中的相关题目模板
2. 根据模板和知识点，生成新的练习题
3. 题目类型包括：选择题、填空题、简答题、编程题
4. 每道题必须附带标准答案和解析

生成要求：
- 题目应覆盖知识点的不同难度层次（基础/中等/困难）
- 避免与题库中的原题完全重复
- 答案必须准确，解析要详细
- 编程题需给出参考代码
"""


def create_question_agent():
    """创建题目生成Agent"""
    llm = get_llm()
    agent = create_react_agent(
        model=llm,
        tools=[search_question_templates],
        prompt=QUESTION_AGENT_PROMPT,
    )
    return agent
