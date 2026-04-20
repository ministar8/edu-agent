from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.rag.retriever import retrieve_documents, build_rag_context, get_llm
from app.rag.knowledge_graph import kg_manager


@tool
def search_learning_path(weak_point: str) -> str:
    """搜索学习路径模板（基于RAG向量检索）。当需要查找学习建议文档时使用。"""
    docs = retrieve_documents(weak_point, collection_name="learning_paths", k=5)
    if not docs:
        return "学习路径库中暂无相关内容。"
    return build_rag_context(docs)


@tool
def query_knowledge_graph(topic: str) -> str:
    """查询知识图谱，获取知识点的前置知识和后续知识关系。当需要分析知识依赖、推荐学习路径时优先使用此工具。"""
    prerequisites = kg_manager.get_prerequisites(topic)
    next_topics = kg_manager.get_next_topics(topic)
    learning_paths = kg_manager.get_learning_path(topic)

    result_parts = []
    if prerequisites:
        names = [p["name"] for p in prerequisites]
        result_parts.append(f"前置知识: {', '.join(names)}")
    if next_topics:
        names = [n["name"] for n in next_topics]
        result_parts.append(f"后续知识: {', '.join(names)}")
    if learning_paths:
        for i, path in enumerate(learning_paths):
            steps = " → ".join([n["name"] for n in path])
            result_parts.append(f"学习路径{i+1}: {steps}")

    if not result_parts:
        return f"知识图谱中暂无 '{topic}' 的相关信息。"
    return "\n".join(result_parts)


PATH_AGENT_PROMPT = """你是一个学习路径推荐Agent。

你的职责是：
1. 优先使用 query_knowledge_graph 工具查询知识图谱中的知识依赖关系
2. 辅助使用 search_learning_path 工具检索学习建议文档
3. 根据学生的薄弱点，分析其前置知识是否掌握
4. 生成个性化的学习路径推荐
5. 推荐学习顺序和重点内容

推荐要求：
- 先补前置知识，再学目标知识
- 给出具体的学习步骤（1、2、3...）
- 每个步骤说明为什么要学、学什么
- 推荐练习题类型以巩固薄弱点
- 适当鼓励学生
"""


def create_path_agent():
    """创建学习路径推荐Agent"""
    llm = get_llm()
    agent = create_react_agent(
        model=llm,
        tools=[query_knowledge_graph, search_learning_path],
        prompt=PATH_AGENT_PROMPT,
    )
    return agent
