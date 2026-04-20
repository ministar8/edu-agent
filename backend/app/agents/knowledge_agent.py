from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from langgraph.prebuilt import create_react_agent

from app.rag.retriever import retrieve_documents, build_rag_context, get_llm


@tool
def search_knowledge_base(query: str) -> str:
    """搜索教材知识库，检索与问题相关的知识点内容。当学生询问知识点、概念解释时使用此工具。"""
    docs = retrieve_documents(query, k=5)
    if not docs:
        return "未在知识库中找到相关内容。"
    return build_rag_context(docs)


KNOWLEDGE_AGENT_PROMPT = """你是一个专业的知识点检索与讲解Agent。

你的职责是：
1. 使用 search_knowledge_base 工具检索教材中相关的知识点
2. 基于检索到的内容，为学生提供清晰、准确的讲解
3. 在回答中标注知识来源（如"根据教材第X章..."）
4. 如果检索结果不足以回答问题，诚实说明并建议学生查阅更多资料

回答要求：
- 语言通俗易懂，适合学生理解
- 适当举例说明抽象概念
- 引用来源时要具体标注
"""


def create_knowledge_agent():
    """创建知识点检索Agent"""
    llm = get_llm()
    agent = create_react_agent(
        model=llm,
        tools=[search_knowledge_base],
        prompt=KNOWLEDGE_AGENT_PROMPT,
    )
    return agent
