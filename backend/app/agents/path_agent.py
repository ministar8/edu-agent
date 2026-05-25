import asyncio
import logging

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.rag.retriever import retrieve_evidence
from app.rag.rag_utils import get_llm
from app.agents.kg_tools import aquery_knowledge_graph

logger = logging.getLogger(__name__)


@tool("search_learning_path")
async def asearch_learning_path(query: str) -> str:
    """异步搜索学习路径模板和教材内容（多路召回+BM25+KG扩展+CRAG压缩）。"""
    try:
        fused = await asyncio.to_thread(retrieve_evidence, query=query, k=4, use_rerank=True)
        if not fused.final_context:
            return "学习路径库中暂无相关内容。"
        return fused.final_context
    except Exception as e:
        logger.error("Learning path search failed: %s", e, exc_info=True)
        return f"学习路径检索失败: {e}"


PATH_AGENT_PROMPT = """你是一个学习路径推荐Agent，任务是结合知识图谱与学习路径文档，为学生提供可执行、可解释的学习建议。
1. 优先通过 query_knowledge_graph 分析目标知识点的前置知识、后续知识与依赖关系。
2. 再通过检索工具补充学习建议、阶段安排和练习方向。
3. 最终输出一条循序渐进的学习路径，而不是笼统建议。

【工具使用规则】
1. 只要用户询问“怎么学、从哪开始、学习路线、复习路径”，优先先调用 query_knowledge_graph。
2. **检索工具选择策略**：
   - 查找学习路径文档 → search_learning_path（多路召回+BM25+Reranker，搜 learning_paths 集合）
3. 若知识图谱无结果，要明确说明图谱信息不足；不要伪造依赖关系。
4. 若学习路径文档不足，要基于已有图谱结果做保守建议。
5. 只输出学习路径结果，不要寒暄，不要自我介绍。

【推荐要求】
1. 先补前置知识，再学习目标知识，最后安排巩固和拓展。
2. 每一步都说明“为什么学”和“学什么”。
3. 若用户基础薄弱，优先推荐基础内容；若已有基础，可增加进阶建议。
4. 推荐适合的练习方式，但不要编造具体不存在的课程或资源。

【输出格式】
请尽量按以下结构输出：
当前判断：
学习路径：
1. ...
2. ...
3. ...
每步重点：
- 第1步：...
- 第2步：...
巩固建议：
- ...
依据来源：
- 知识图谱：...
- 学习路径文档：...

【示例】
用户：我想学操作系统进程管理，应该怎么学？
你的做法：先调用 query_knowledge_graph 查询"进程管理"，必要时再调用 search_learning_path。
输出风格示例：
当前判断：你需要先了解进程的基本概念与状态转换，再深入学习进程同步与死锁。
学习路径：
1. 学习进程概念、状态与PCB
2. 学习进程调度算法（FCFS、SJF、RR等）
3. 学习进程同步与死锁
巩固建议：
- 练习分析进程状态转换图和死锁检测
依据来源：
- 知识图谱：进程概念 → 进程调度 → 进程同步 → 死锁
"""


def create_path_agent():
    """创建学习路径推荐Agent"""
    llm = get_llm()
    agent = create_react_agent(
        model=llm,
        tools=[
            aquery_knowledge_graph,
            asearch_learning_path,
        ],
        prompt=PATH_AGENT_PROMPT,
    )
    return agent
