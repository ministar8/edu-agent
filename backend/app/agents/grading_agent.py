from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.rag.retriever import retrieve_documents, build_rag_context, get_llm


@tool
def search_standard_answer(question: str) -> str:
    """搜索标准答案库，检索与题目对应的标准答案和评分标准。当需要批改学生答案时使用此工具。"""
    docs = retrieve_documents(question, collection_name="answers", k=3)
    if not docs:
        return "标准答案库中暂无相关内容。"
    return build_rag_context(docs)


GRADING_AGENT_PROMPT = """你是一个批改评估Agent。

你的职责是：
1. 使用 search_standard_answer 工具检索标准答案和评分标准
2. 将学生的答案与标准答案进行对比
3. 给出评分（0-100分）和详细的批改意见
4. 指出学生答案中的优点和不足

批改要求：
- 评分要公正客观，严格按照评分标准
- 批改意见要具体，指出哪里正确、哪里错误
- 对错误部分给出正确解释
- 对优秀部分给予鼓励
- 如果标准答案库中没有对应内容，基于知识进行判断，并标注"参考评分"
"""


def create_grading_agent():
    """创建批改评估Agent"""
    llm = get_llm()
    agent = create_react_agent(
        model=llm,
        tools=[search_standard_answer],
        prompt=GRADING_AGENT_PROMPT,
    )
    return agent
