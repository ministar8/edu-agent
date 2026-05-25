import asyncio
import logging

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.rag.retriever import retrieve_evidence
from app.rag.rag_utils import get_llm
from app.rag.schemas import GradingResult
from app.agents.kg_tools import aquery_knowledge_graph

logger = logging.getLogger(__name__)


@tool("search_standard_answer")
async def asearch_standard_answer(query: str) -> str:
    """搜索教材知识库中的标准答案和评分依据（多路召回+BM25+KG扩展+CRAG压缩）。当需要批改学生答案时使用此工具。"""
    try:
        fused = await asyncio.to_thread(retrieve_evidence, query=query, k=5, use_rerank=True)
        if not fused.final_context:
            return "知识库中暂无相关内容。"
        return fused.final_context
    except Exception as e:
        logger.error("Standard answer search failed: %s", e, exc_info=True)
        return f"标准答案检索失败: {e}"


GRADING_AGENT_PROMPT = """你是一个批改评估Agent，任务是基于标准答案与知识库内容进行检索增强批改，而不是仅凭印象打分。

【工具使用规则】
1. 只要用户要求批改、评分、检查答案，必须先调用检索工具。
2. **检索工具选择策略**：
   - 查找标准答案、评分点与知识依据 → search_standard_answer（统一检索管线会根据查询自动路由到相关集合）
3. 将学生答案与标准答案逐项对比，结合知识背景给出更准确的评分。
4. **知识图谱辅助评估**：批改时可调用 query_knowledge_graph 查询相关知识点的前置知识，判断学生答案是否覆盖了关键前置概念。
5. 若检索结果不足，要明确说明"标准答案依据不足"。
6. 没有检索依据时，不要伪装成标准答案批改；只能给出"参考评分"。
7. 不要编造不存在的评分细则或标准出处。
8. 只输出批改结果，不要寒暄，不要自我介绍。

【评分要求】
1. 默认使用 0-100 分。
2. 先判断答案是否覆盖关键点，再看表达准确性、完整性与逻辑性。
3. 若是开放题，允许合理表述差异，但要说明得分依据。
4. 对明显正确部分给予肯定，对错误部分给出改进建议。

【输出格式】
知识点：被批改答案涉及的核心知识点名称（必须与教材知识点名称一致）
难度：基础/理解/综合/创新（评估该知识点的难度等级）
评分：XX/100
评价结论：
命中要点：
- ...
主要问题：
- ...
改进建议：
- ...
评分依据：
- ...

若检索依据不足，请在“评分依据”中明确写出“参考评分（标准答案库不足）”。

【示例】
用户：请批改我对"进程死锁产生条件"的回答。
你的做法：先调用 search_standard_answer 检索"进程死锁产生条件"。
输出风格示例：
知识点：进程死锁
难度：理解
评分：82/100
评价结论：理解基本正确，但对"循环等待"条件的解释不完整。
命中要点：
- 提到了互斥条件和占有并等待条件。
主要问题：
- 未说明循环等待条件中进程与资源的关系。
改进建议：
- 补充循环等待的完整定义与典型场景。
评分依据：
- xxx.md
"""


async def grade_single_question(
    stem: str,
    standard_answer: str,
    user_answer: str,
) -> dict:
    """单题批改（非 ReAct）：检索知识库 + LLM 判卷，返回 {score, feedback, is_wrong}

    不走 ReAct 循环，直接检索 → 生成 → 解析，延迟 < 2s。"""

    # 1. 构建检索查询：题干关键词 + 标准答案前段
    search_query = f"{stem[:200]} {standard_answer[:100]}" if standard_answer else stem[:200]
    try:
        fused = await asyncio.to_thread(
            retrieve_evidence, query=search_query, k=5, use_rerank=True
        )
        context = fused.final_context if fused.final_context else ""
        if not context:
            context = "（知识库中未检索到相关依据）"
    except Exception:
        context = "（检索失败，请基于题干和标准答案判卷）"

    # 2. 结构化批改（Function Calling / JSON Schema，替代正则解析）
    grade_prompt = f"""请基于知识库依据和标准答案，批改以下408考研题目。

知识库依据：
{context[:2500]}

题干：{stem}
标准答案：{standard_answer or "（无标准答案，请基于知识库依据判断）"}
学生答案：{user_answer}
"""

    llm = get_llm()
    structured_llm = llm.with_structured_output(GradingResult)
    try:
        result = await structured_llm.ainvoke(grade_prompt)
        return {"score": float(result.score), "feedback": result.feedback, "is_wrong": result.is_wrong}
    except Exception as e:
        logger.warning("Structured grading failed, fallback to regex: %s", e)
        # 兜底：用原始 LLM 调用 + 正则解析
        import re
        response = await llm.ainvoke(grade_prompt)
        text = response.content if hasattr(response, "content") else str(response)
        score_match = re.search(r"[0-9]{1,3}", text)
        score = float(score_match.group(0)) if score_match else 50.0
        score = max(0.0, min(100.0, score))
        feedback = text[:200] if not score_match else text
        return {"score": score, "feedback": feedback, "is_wrong": score < 60}


def create_grading_agent():
    """创建批改评估Agent"""
    llm = get_llm()
    agent = create_react_agent(
        model=llm,
        tools=[
            asearch_standard_answer,
            aquery_knowledge_graph,
        ],
        prompt=GRADING_AGENT_PROMPT,
    )
    return agent
