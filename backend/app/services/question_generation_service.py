from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

from app.agents.question_tools import asearch_question_templates, get_cached_evidences
from app.rag.parse_utils import parse_llm_json
from app.rag.rag_utils import get_llm
from app.rag.schemas import QuestionList

logger = logging.getLogger(__name__)


def extract_topic(query: str) -> str:
    match = re.search(r"「([^」]+)」", query)
    if match:
        return match.group(1).strip()
    return query.strip()


def parse_questions_from_raw(raw: str) -> list[dict]:
    questions = _regex_parse_questions(raw)
    if questions:
        return questions
    return _llm_parse_questions(raw)


def compute_quality_scores(questions: list[dict], template_texts: list[str]) -> list[dict]:
    type_counts: dict[str, int] = {}
    for question in questions:
        question_type = question.get("question_type", "简答")
        type_counts[question_type] = type_counts.get(question_type, 0) + 1

    for question in questions:
        score = 1.0
        stem = question.get("stem", "")
        if stem and template_texts:
            max_similarity = max(
                SequenceMatcher(None, stem, template).ratio()
                for template in template_texts
            )
            if max_similarity > 0.8:
                score -= 0.3

        if len(question.get("explanation", "")) < 20:
            score -= 0.3

        question_type = question.get("question_type", "简答")
        if type_counts.get(question_type, 0) >= 5:
            score -= 0.2

        question["quality_score"] = max(0.0, score)

    return questions


async def generate_questions_with_retrieval(prompt: str) -> QuestionList | str:
    retrieval_query = extract_topic(prompt)
    retrieval_context = await asearch_question_templates.ainvoke({"query": retrieval_query})
    if _is_empty_retrieval(retrieval_context):
        return retrieval_context or "题库和教材中暂无相关内容。"

    llm = get_llm()
    generation_prompt = build_generation_prompt(retrieval_context, prompt)
    structured_llm = llm.with_structured_output(QuestionList)
    try:
        return await structured_llm.ainvoke(generation_prompt)
    except Exception as exc:
        logger.warning("Structured question generation failed, fallback to free-text: %s", exc)
        response = await llm.ainvoke(generation_prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        return raw.strip()


async def generate_questions_from_prompt(prompt: str) -> list[dict]:
    retrieval_query = extract_topic(prompt)
    retrieval_context = await asearch_question_templates.ainvoke({"query": retrieval_query})
    if _is_empty_retrieval(retrieval_context):
        return [{"error": retrieval_context or "题库和教材中暂无相关内容。"}]

    template_texts = [evidence.content for evidence in get_cached_evidences()]
    llm = get_llm()
    generation_prompt = build_generation_prompt(retrieval_context, prompt)
    try:
        structured_llm = llm.with_structured_output(QuestionList)
        result = await structured_llm.ainvoke(generation_prompt)
        questions = [
            {
                "question_type": question.question_type,
                "difficulty": question.difficulty,
                "stem": question.stem,
                "answer": question.answer,
                "explanation": question.explanation,
            }
            for question in result.questions
            if question.stem
        ]
        if not questions:
            return []
    except Exception as exc:
        logger.warning("Structured question generation failed, fallback to free-text: %s", exc)
        response = await llm.ainvoke(generation_prompt)
        raw = response.content if hasattr(response, "content") else str(response)
        questions = parse_questions_from_raw(raw.strip())
        if not questions:
            return [{"raw_text": raw.strip()}]

    return compute_quality_scores(questions, template_texts)


def build_generation_prompt(retrieval_context: str, prompt: str) -> str:
    return "\n\n".join([
        "请基于已检索到的题库模板与知识库内容生成练习题。",
        "生成规则：严格基于检索依据，不要编造；解析不超过80字；不要寒暄。",
        "【已检索到的题库模板与知识依据】",
        retrieval_context,
        "【用户出题需求】",
        prompt,
        "请以JSON格式输出。",
    ])


def _is_empty_retrieval(retrieval_context: str) -> bool:
    return (
        not retrieval_context
        or "暂无相关内容" in retrieval_context
        or "题库检索失败" in retrieval_context
    )


def _regex_parse_questions(raw: str) -> list[dict]:
    splits = re.split(r'(?:题目|第)[\d一二三四五六七八九十]+[题：:]', raw)
    if len(splits) < 2:
        return []

    questions = []
    for part in splits[1:]:
        question: dict = {}
        match = re.search(r'类型[：:]\s*(选择|填空|简答|综合应用|综合|计算)', part)
        if match:
            question["question_type"] = match.group(1)
        match = re.search(r'难度[：:]\s*(基础|简单|中等|较难|困难|高级|入门|理解|综合)', part)
        if match:
            question["difficulty_label"] = match.group(1)
            question["difficulty"] = _label_to_difficulty(match.group(1))
        match = re.search(r'题干[：:]\s*(.+?)(?=\n(?:标准答案|答案|解析)[：:]|\Z)', part, re.DOTALL)
        if match:
            question["stem"] = match.group(1).strip()
        match = re.search(r'(?:标准答案|答案)[：:]\s*(.+?)(?=\n(?:解析|题目|第)[：:]|\Z)', part, re.DOTALL)
        if match:
            question["answer"] = match.group(1).strip()
        match = re.search(r'解析[：:]\s*(.+?)(?=\n(?:题目|第)[\d一二三四五六七八九十]+[题：:]|\Z)', part, re.DOTALL)
        if match:
            question["explanation"] = match.group(1).strip()

        if question.get("stem"):
            question.setdefault("question_type", "简答")
            question.setdefault("difficulty", 1.0)
            question.setdefault("answer", "")
            question.setdefault("explanation", "")
            questions.append(question)

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
                    "question_type": question.get("type", "简答"),
                    "difficulty": float(question.get("difficulty", 1.3)),
                    "stem": question.get("stem", ""),
                    "answer": question.get("answer", ""),
                    "explanation": question.get("explanation", ""),
                }
                for question in questions
                if isinstance(question, dict) and question.get("stem")
            ]
        return []
    except Exception as exc:
        logger.warning("LLM parse failed for questions: %s", exc)
        return []
