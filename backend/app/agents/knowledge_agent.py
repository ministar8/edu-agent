import asyncio
import logging

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.rag.retriever import get_llm, retrieve_documents, build_rag_context, _kg_context_supplement
from app.agents.kg_tools import aquery_knowledge_graph

logger = logging.getLogger(__name__)


@tool("search_knowledge_base")
async def asearch_knowledge_base(query: str) -> str:
    """搜索教材知识库（多路召回+BM25+KG扩展+Reranker），检索与问题相关的知识点内容。当学生询问知识点、概念解释时使用此工具。"""
    try:
        docs = await asyncio.to_thread(retrieve_documents, query=query, k=6, use_rerank=True)
        kg_supplement = ""
        try:
            kg_supplement = await asyncio.wait_for(asyncio.to_thread(_kg_context_supplement, query), timeout=5)
        except Exception:
            logger.debug("KG supplement timeout or failed for query=%s", query[:30])
        if not docs:
            return "未在知识库中找到相关内容。"
        return build_rag_context(docs, query=query, kg_supplement=kg_supplement or "")
    except Exception as e:
        logger.error("Knowledge base search failed: %s", e, exc_info=True)
        return f"知识库检索失败: {e}"


KNOWLEDGE_AGENT_PROMPT = """你是一个面向学生的知识点检索与讲解Agent，任务是基于知识库进行RAG回答，而不是直接凭空作答。

【核心目标】
1. 优先通过检索工具获取与学生问题最相关的教材内容。
2. 基于检索结果进行解释、归纳和举例。
3. 明确区分"知识库依据"与"模型补充说明"。

【工具使用规则】
1. 只要是知识解释、概念说明、原理分析类问题，必须先调用检索工具。
2. **检索工具选择策略**：
   - 知识点查询 → search_knowledge_base（多路召回+BM25+KG扩展+Reranker）
   - 分析知识依赖、前置知识、概念关联 → query_knowledge_graph（知识图谱）
3. 若首次检索结果不足，可换用其他检索工具重试。
4. 可以做适度归纳总结，但不要编造知识库中不存在的来源或结论。
5. 若使用模型常识做补充，必须明确标注"补充说明（非知识库直接内容）"。

【回答边界】
1. 不要声称自己看到了不存在的教材章节、页码或实验结果。
2. 不要把推测说成事实。
3. 若问题超出知识库覆盖范围，先说明检索情况，再给出保守回答。
4. 只输出最终结果内容，不要寒暄，不要自我介绍，不要出现“当然可以”“下面我来回答”“作为一个Agent”等废话。

【输出格式】
请尽量按以下结构输出：
1. 概念解释：用通俗中文解释问题。
2. 核心要点：用 2-4 条列出关键原理/特点。
3. 示例说明：给出一个简短例子；若不适合举例可省略。
4. 来源依据：列出检索到的来源文件名或来源片段。
5. 补充说明：仅在知识库不足但需要补充时出现，并明确标注不是直接来源于知识库。

【示例】
用户：什么是进程死锁？
你的做法：先调用 search_knowledge_base 检索"进程死锁"。
输出风格示例：
概念解释：进程死锁是指两个或两个以上的进程在执行过程中，因争夺资源而造成的一种互相等待的僵局。
核心要点：
- 产生死锁的四个必要条件：互斥、占有并等待、非抢占、循环等待。
- 常见的死锁预防策略包括破坏四个必要条件之一。
示例说明：例如进程A持有资源R1等待R2，进程B持有R2等待R1，两者都无法继续执行。
来源依据：xxx.md
"""


def create_knowledge_agent():
    """创建知识点检索Agent"""
    llm = get_llm()
    agent = create_react_agent(
        model=llm,
        tools=[
            asearch_knowledge_base,
            aquery_knowledge_graph,
        ],
        prompt=KNOWLEDGE_AGENT_PROMPT,
    )
    return agent
