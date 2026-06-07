import logging
import re
import threading
import uuid
from difflib import SequenceMatcher

from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent

from app.config import settings
from app.rag.evidence import TextEvidence
from app.rag.rag_utils import get_llm
from app.rag.schemas import QuestionList
from app.rag.parse_utils import parse_llm_json
from app.agents.kg_tools import aquery_knowledge_graph
from app.agents.prompts import QUESTION_AGENT_SYSTEM_PROMPT as QUESTION_AGENT_PROMPT

logger = logging.getLogger(__name__)


# ── 学科集合路由 ──────────────────────────────────────────────

def _subject_collection(query: str) -> str:
    if "数据结构" in query:
        return "data_structure"
    if "组成原理" in query or "计算机组成" in query:
        return "computer_organization"
    if "操作系统" in query:
        return "operating_system"
    if "计算机网络" in query or "网络" in query:
        return "computer_network"
    return ""


def _extract_topic(query: str) -> str:
    match = re.search(r"「([^」]+)」", query)
    if match:
        return match.group(1).strip()
    return query.strip()


# ── Q3b: 难度标注提取 ──────────────────────────────────────────

_DIFFICULTY_KEYWORDS = {
    1.0: ["基础", "入门", "概述", "概念", "基本", "初识"],
    1.3: ["理解", "掌握", "原理", "特征", "性质", "定义"],
    1.6: ["综合", "应用", "分析", "设计", "实现", "计算"],
    2.0: ["创新", "优化", "拓展", "高级", "深入", "探究"],
}


def _has_difficulty_keyword(heading_path: str) -> bool:
    """检查 heading_path 是否包含难度关键词"""
    for keywords in _DIFFICULTY_KEYWORDS.values():
        for kw in keywords:
            if kw in heading_path:
                return True
    return False


def _difficulty_label(d: float) -> str:
    if d <= 1.1:
        return "基础"
    elif d <= 1.4:
        return "理解"
    elif d <= 1.7:
        return "综合"
    else:
        return "高级"


def _lookup_registry_difficulty(kp_name: str) -> float | None:
    """从 KnowledgePointRegistry 查询知识点难度"""
    try:
        from app.db.session import SessionLocal
        from app.db.models import KnowledgePointRegistry
        with SessionLocal() as db:
            reg = db.query(KnowledgePointRegistry).filter(
                KnowledgePointRegistry.name == kp_name,
            ).first()
            if reg and reg.difficulty_source == "manual":
                return reg.difficulty
            if reg and _has_difficulty_keyword(reg.heading_path or ""):
                return reg.difficulty
            return None  # 未标注
    except Exception:
        return None


def _extract_difficulty_annotations(evidences: list[TextEvidence], subject: str) -> str:
    """从 TextEvidence metadata 和 Registry 提取知识点难度标注，注入出题 prompt"""
    annotations: dict[str, str] = {}

    for ev in evidences:
        kp_name = ev.metadata.get("knowledge_point") or ev.metadata.get("heading", "")
        if not kp_name or kp_name in annotations:
            continue

        diff_value = ev.metadata.get("difficulty")
        diff_source = ev.metadata.get("difficulty_source", "auto")

        if diff_value is not None:
            d = float(diff_value)
            # auto 且无关键词 → 标"未知"
            if diff_source == "auto" and d == 1.0:
                heading_path = ev.metadata.get("heading_path", "")
                if not _has_difficulty_keyword(heading_path):
                    annotations[kp_name] = "未知"
                    continue
            label = _difficulty_label(d)
            annotations[kp_name] = f"{label}({d:.1f})"
        else:
            reg_diff = _lookup_registry_difficulty(kp_name)
            if reg_diff is not None:
                annotations[kp_name] = f"{_difficulty_label(reg_diff)}({reg_diff:.1f})"
            else:
                annotations[kp_name] = "未知"

    if not annotations:
        return "难度信息未知，请按混合难度出题。"

    lines = [f"  - {name}：{anno}" for name, anno in annotations.items()]
    return "【知识点难度标注】\n" + "\n".join(lines) + "\n请按标注难度生成对应题目；标注「未知」的按中等难度出题。"


# ── Q1: 完整 RAG 管线检索 ──────────────────────────────────────

# 线程安全的缓存：存储最近一次检索的 evidences，供 generate_and_persist_questions 复用
_local = threading.local()


def _get_cached_evidences() -> list[TextEvidence]:
    return getattr(_local, "last_evidences", [])


def _set_cached_evidences(evidences: list[TextEvidence]) -> None:
    _local.last_evidences = evidences


@tool("search_question_templates")
async def asearch_question_templates(query: str) -> str:
    """异步搜索题库和教材中与指定知识点相关的题目模板、例题和知识点内容（多路召回+Reranker+KG扩展完整管线）。"""
    try:
        subject = _subject_collection(query)
        all_evidences: list[TextEvidence] = []
        context_parts: list[str] = []

        # 学科集合：retrieve_evidence 完整管线（含 KG 补充）
        if subject:
            from app.rag.retriever import aretrieve_evidence
            subject_fused = await aretrieve_evidence(
                query=query, collection_name=subject, k=5, use_rerank=True
            )
            if subject_fused.final_context:
                context_parts.append(subject_fused.final_context)
            all_evidences.extend(subject_fused.text_evidences)

        # questions 集合：retrieve_evidence 完整管线
        from app.rag.retriever import aretrieve_evidence as _are
        q_fused = await _are(
            query=query, collection_name="questions", k=3, use_rerank=True
        )
        if q_fused.final_context:
            context_parts.append(q_fused.final_context)
        all_evidences.extend(q_fused.text_evidences)

        # 缓存供下游复用
        _set_cached_evidences(all_evidences)

        if not context_parts:
            return "题库和教材中暂无相关内容。"

        context = "\n\n".join(context_parts)

        # 难度标注注入（从 TextEvidence metadata 提取）
        difficulty_annotation = _extract_difficulty_annotations(all_evidences, subject)
        if difficulty_annotation and not difficulty_annotation.startswith("难度信息未知"):
            context = difficulty_annotation + "\n\n" + context

        max_context_chars = 4500
        if len(context) > max_context_chars:
            context = context[:max_context_chars] + "\n\n[上下文已截断：仅保留最相关的题库模板与知识依据。]"
        return context
    except Exception as e:
        logger.error("Question template search failed: %s", e, exc_info=True)
        return f"题库检索失败: {e}"


# ── Q2b: 题目解析（正则快速路径 + LLM 兜底）─────────────────────

def _regex_parse_questions(raw: str) -> list[dict]:
    """正则快速路径：从自由格式文本提取结构化题目

    兼容格式变异：
    - 题目1：/ 题目一：/ 第1题：/ 第一题：
    - 中文冒号（：）和英文冒号（:）
    """
    # 按题目分割符切分
    splits = re.split(r'(?:题目|第)[\d一二三四五六七八九十]+[题：:]', raw)
    if len(splits) < 2:
        return []

    questions = []
    for part in splits[1:]:
        q: dict = {}
        # 类型
        m = re.search(r'类型[：:]\s*(选择|填空|简答|综合应用|综合|计算)', part)
        if m:
            q["question_type"] = m.group(1)
        # 难度
        m = re.search(r'难度[：:]\s*(基础|简单|中等|较难|困难|高级|入门|理解|综合)', part)
        if m:
            q["difficulty_label"] = m.group(1)
            q["difficulty"] = _label_to_difficulty(m.group(1))
        # 题干
        m = re.search(r'题干[：:]\s*(.+?)(?=\n(?:标准答案|答案|解析)[：:]|\Z)', part, re.DOTALL)
        if m:
            q["stem"] = m.group(1).strip()
        # 标准答案
        m = re.search(r'(?:标准答案|答案)[：:]\s*(.+?)(?=\n(?:解析|题目|第)[：:]|\Z)', part, re.DOTALL)
        if m:
            q["answer"] = m.group(1).strip()
        # 解析
        m = re.search(r'解析[：:]\s*(.+?)(?=\n(?:题目|第)[\d一二三四五六七八九十]+[题：:]|\Z)', part, re.DOTALL)
        if m:
            q["explanation"] = m.group(1).strip()

        if q.get("stem"):
            q.setdefault("question_type", "简答")
            q.setdefault("difficulty", 1.0)
            q.setdefault("answer", "")
            q.setdefault("explanation", "")
            questions.append(q)

    return questions


def _label_to_difficulty(label: str) -> float:
    mapping = {
        "基础": 1.0, "简单": 1.0, "入门": 1.0,
        "理解": 1.3, "中等": 1.3,
        "综合": 1.6, "较难": 1.6, "综合应用": 1.6,
        "困难": 2.0, "高级": 2.0,
    }
    return mapping.get(label, 1.3)


def _llm_parse_questions(raw: str) -> list[dict]:
    """LLM 兜底解析：从自由格式文本提取结构化题目列表"""
    llm = get_llm()
    prompt = f"""请从以下题目文本中提取所有题目，输出 JSON 列表。每道题包含字段：
type(选择/填空/简答/综合), difficulty(1.0-2.0浮点数), stem(题干全文), answer(标准答案), explanation(解析)。
只输出 JSON 数组，不要其他内容。

题目文本：
{raw}
"""
    try:
        response = llm.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        questions = parse_llm_json(text.strip(), fallback_default=[])
        if isinstance(questions, list):
            return [
                {
                    "question_type": q.get("type", "简答"),
                    "difficulty": float(q.get("difficulty", 1.3)),
                    "stem": q.get("stem", ""),
                    "answer": q.get("answer", ""),
                    "explanation": q.get("explanation", ""),
                }
                for q in questions if isinstance(q, dict) and q.get("stem")
            ]
        return []
    except Exception as e:
        logger.warning("LLM parse failed for questions: %s", e)
        return []


def parse_questions_from_raw(raw: str) -> list[dict]:
    """解析 LLM 输出为结构化题目列表：正则快速路径 + LLM 兜底"""
    questions = _regex_parse_questions(raw)
    if questions:
        return questions
    return _llm_parse_questions(raw)


# ── Q2c: 出题质量自动评估 ──────────────────────────────────────

def compute_quality_scores(questions: list[dict], template_texts: list[str]) -> list[dict]:
    """批级别计算每题 quality_score

    因子：
    - 模板重叠度：题干与检索模板 Jaccard > 0.8 → -0.3
    - 解析长度：explanation < 20 字 → -0.3
    - 类型多样性：同类型 >= 5 题 → -0.2
    """
    type_counts: dict[str, int] = {}
    for q in questions:
        t = q.get("question_type", "简答")
        type_counts[t] = type_counts.get(t, 0) + 1

    for q in questions:
        score = 1.0

        # 模板重叠检查
        stem = q.get("stem", "")
        if stem and template_texts:
            max_sim = max(
                SequenceMatcher(None, stem, t).ratio() for t in template_texts
            )
            if max_sim > 0.8:
                score -= 0.3

        # 解析长度检查
        explanation = q.get("explanation", "")
        if len(explanation) < 20:
            score -= 0.3

        # 类型多样性检查
        qtype = q.get("question_type", "简答")
        if type_counts.get(qtype, 0) >= 5:
            score -= 0.2

        q["quality_score"] = max(0.0, score)

    return questions


# ── 题目生成主流程 ──────────────────────────────────────────────

async def generate_questions_with_retrieval(prompt: str) -> QuestionList | str:
    """结构化出题：检索 + with_structured_output(QuestionList)

    Returns:
        QuestionList 实例（成功）或错误字符串（检索无结果）
    """
    retrieval_query = _extract_topic(prompt)
    retrieval_context = await asearch_question_templates.ainvoke({"query": retrieval_query})
    if (
        not retrieval_context
        or "暂无相关内容" in retrieval_context
        or "题库检索失败" in retrieval_context
    ):
        return retrieval_context or "题库和教材中暂无相关内容。"

    llm = get_llm()
    generation_prompt = "\n\n".join([
        "请基于已检索到的题库模板与知识库内容生成练习题。",
        "生成规则：严格基于检索依据，不要编造；解析不超过80字；不要寒暄。",
        "【已检索到的题库模板与知识依据】",
        retrieval_context,
        "【用户出题需求】",
        prompt,
        "请以JSON格式输出。",
    ])
    structured_llm = llm.with_structured_output(QuestionList)
    try:
        result = await structured_llm.ainvoke(generation_prompt)
        return result
    except Exception as e:
        logger.warning("Structured question generation failed, fallback to free-text: %s", e)
        # 兜底：自由文本 + 正则解析
        response = await llm.ainvoke(generation_prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        return raw.strip()


async def generate_and_persist_questions(
    prompt: str,
    user_id: int,
    conversation_id: int | None = None,
) -> list[dict]:
    """出题 + 解析 + 质量评估 + 持久化，返回结构化题目列表"""
    # 一次检索，同时用于生成 + 质量评估
    retrieval_query = _extract_topic(prompt)
    retrieval_context = await asearch_question_templates.ainvoke({"query": retrieval_query})

    # 检索无结果
    if (
        not retrieval_context
        or "暂无相关内容" in retrieval_context
        or "题库检索失败" in retrieval_context
    ):
        return [{"error": retrieval_context or "题库和教材中暂无相关内容。"}]

    # 提取模板文本（复用 asearch_question_templates 缓存的 evidences，避免二次检索）
    template_texts: list[str] = [ev.content for ev in _get_cached_evidences()]

    # 生成题目
    llm = get_llm()
    generation_prompt = "\n\n".join([
        "请基于已检索到的题库模板与知识库内容生成练习题。",
        "生成规则：严格基于检索依据，不要编造；解析不超过80字；不要寒暄。",
        "【已检索到的题库模板与知识依据】",
        retrieval_context,
        "【用户出题需求】",
        prompt,
        "请以JSON格式输出。",
    ])
    try:
        structured_llm = llm.with_structured_output(QuestionList)
        result = await structured_llm.ainvoke(generation_prompt)
        questions = [
            {
                "question_type": q.question_type,
                "difficulty": q.difficulty,
                "stem": q.stem,
                "answer": q.answer,
                "explanation": q.explanation,
            }
            for q in result.questions
            if q.stem
        ]
        if not questions:
            return []
    except Exception as e:
        logger.warning("Structured question generation failed, fallback to free-text: %s", e)
        response = await llm.ainvoke(generation_prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        questions = parse_questions_from_raw(raw.strip())
        if not questions:
            return [{"raw_text": raw.strip()}]

    questions = compute_quality_scores(questions, template_texts)

    # 持久化
    batch_id = str(uuid.uuid4())
    _persist_questions(questions, user_id, conversation_id, batch_id)

    for q in questions:
        q["batch_id"] = batch_id

    return questions


def _persist_questions(
    questions: list[dict],
    user_id: int,
    conversation_id: int | None,
    batch_id: str,
) -> None:
    """将解析后的题目存入 QuestionRecord，并回写 DB id 到 question dict"""
    from app.db.session import SessionLocal
    from app.db.models import QuestionRecord

    with SessionLocal() as db:
        try:
            for q in questions:
                record = QuestionRecord(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    batch_id=batch_id,
                    question_type=q.get("question_type", "简答"),
                    difficulty=q.get("difficulty", 1.0),
                    stem=q.get("stem", ""),
                    standard_answer=q.get("answer", ""),
                    explanation=q.get("explanation", ""),
                    source="generated",
                    quality_score=q.get("quality_score"),
                )
                db.add(record)
                db.flush()  # flush to get record.id
                q["id"] = record.id
            db.commit()
        except Exception as e:
            logger.warning("Failed to persist questions: %s", e)
            db.rollback()


# ── Agent 定义 ──────────────────────────────────────────────────


def create_question_agent():
    """创建题目生成Agent（ReAct 模式，供 Supervisor 路由使用）"""
    llm = get_llm(temperature=settings.TEMP_CREATIVE, use_fast=True)  # ReAct 工具选择用 fast
    agent = create_react_agent(
        model=llm,
        tools=[
            asearch_question_templates,
            aquery_knowledge_graph,
        ],
        prompt=QUESTION_AGENT_PROMPT,
    )
    return agent
