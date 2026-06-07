"""Reflection Agent — 生成后语义层证据校验

在后置治理（answer_governance）之后运行，检查：
1. 回答中的关键断言是否能在检索证据中找到支撑
2. 是否存在证据之间的矛盾
3. 是否遗漏了查询的关键方面

与 answer_governance 互补：
- governance：格式检查、来源字段、伪造引用、废话过滤（规则层）
- reflection：语义层证据支撑判断、矛盾检测、完整性评估（LLM + 规则）

设计要点：
- 不做自评（不让 Agent 评自己的输出），Reflection 是独立节点
- LLM 层仅规则不确定时触发，优先用规则信号降低延迟
- 输出追加到回答末尾作为提醒，不阻止回答
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.config import settings
from app.agents.prompts import REFLECTION_PROMPT

logger = logging.getLogger(__name__)


@dataclass
class ReflectionResult:
    answer: str              # 可能追加提醒后的回答
    confidence: str          # high / medium / low
    issues: list[str]        # 发现的问题
    evidence_sufficient: bool
    contradictions: list[str]
    suggestion: str          # 给用户的提示（追加到回答末尾）


# ── 规则层信号（零延迟） ──────────────────────────────

def _rule_signals(answer: str, evidence_text: str, query: str) -> dict:
    """从回答和证据中提取规则信号，不依赖 LLM"""
    result = {
        "answer_len": len(answer),
        "evidence_len": len(evidence_text),
        "has_term_overlap": False,
        "overlap_ratio": 0.0,
        "has_numeric_claims": False,
        "has_chapter_refs": False,
    }

    if not answer or not evidence_text:
        return result

    # 关键词重叠：回答中的关键术语是否出现在证据中
    answer_terms = set(re.findall(r"[一-鿿A-Za-z]{2,}", answer.lower()))
    evidence_terms = set(re.findall(r"[一-鿿A-Za-z]{2,}", evidence_text.lower()))
    if answer_terms:
        overlap = answer_terms & evidence_terms
        result["overlap_ratio"] = len(overlap) / len(answer_terms)
        result["has_term_overlap"] = result["overlap_ratio"] > 0.3

    # 数字/量词声称（易凭空编造）
    result["has_numeric_claims"] = bool(re.search(r"\d+\s*[个次种条层级别]", answer))

    # 章节引用（常见伪造）
    result["has_chapter_refs"] = bool(re.search(r"第[一二三四五六七八九十\d]+章", answer))

    return result


def _rule_reflection(evidence_text: str, answer: str, query: str) -> ReflectionResult:
    """纯规则反射（LLM 不可用时的回退）"""
    signals = _rule_signals(answer, evidence_text, query)
    issues: list[str] = []

    # 答案过短
    if signals["answer_len"] < 20:
        issues.append("回答过于简短，可能未完整覆盖问题")

    # 术语重叠过低
    if not signals["has_term_overlap"] and signals["answer_len"] > 50:
        issues.append("回答与证据的术语重叠率低，可能存在推断")

    # 数字声称但证据不足
    if signals["has_numeric_claims"] and signals["evidence_len"] < 100:
        issues.append("回答包含数值/量化表述但证据较短，请核实")

    # 章节引用
    if signals["has_chapter_refs"]:
        issues.append("回答包含章节引用，无法验证其真实性")

    confidence = "high" if len(issues) == 0 else ("medium" if len(issues) <= 2 else "low")
    suggestion = ""
    if issues:
        suggestion = "⚠️ 部分回答内容无法在知识库中充分验证，仅供参考。" if confidence in ("medium", "low") else ""

    return ReflectionResult(
        answer=answer,
        confidence=confidence,
        issues=issues,
        evidence_sufficient=len(issues) <= 2,
        contradictions=[],
        suggestion=suggestion,
    )


# ── LLM 层（规则不确定时触发） ──────────────────────────

# (prompt content moved to prompts.py)


async def _allm_reflection(evidence_text: str, answer: str, query: str) -> ReflectionResult:
    """LLM 语义层反思（异步，不阻塞事件循环）"""
    try:
        from app.rag.rag_utils import get_llm
        import json as _json

        llm = get_llm(streaming=False, temperature=settings.TEMP_PRECISE)
        prompt = REFLECTION_PROMPT.format(
            query=query,
            evidence=evidence_text[:4000],
            answer=answer[:3000],
        )
        raw = await llm.ainvoke(prompt)
        text = raw.content if hasattr(raw, "content") else str(raw)
        text = str(text or "").strip()

        # 提取 JSON
        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= start:
            logger.warning("Reflection LLM: cannot parse JSON, falling back to rule")
            return _rule_reflection(evidence_text, answer, query)

        parsed = _json.loads(text[start:end])
        issues = [str(i) for i in parsed.get("issues", [])]
        return ReflectionResult(
            answer=answer,
            confidence=str(parsed.get("confidence", "medium")),
            issues=issues,
            evidence_sufficient=bool(parsed.get("evidence_sufficient", True)),
            contradictions=[str(c) for c in parsed.get("contradictions", [])],
            suggestion=str(parsed.get("suggestion", "")),
        )
    except Exception as e:
        logger.warning("Reflection LLM failed: %s, falling back to rule", e)
        return _rule_reflection(evidence_text, answer, query)


def _llm_reflection(evidence_text: str, answer: str, query: str) -> ReflectionResult:
    """同步 LLM 反思已禁用；LLM 反思请使用 await areflect()。"""
    logger.warning("Sync LLM reflection skipped; use areflect() in async context")
    return _rule_reflection(evidence_text, answer, query)


# ── 公开 API ──────────────────────────────────────────

async def areflect(
    answer: str,
    evidence_text: str,
    query: str,
    agent_name: str = "",
    use_llm: bool = True,
) -> ReflectionResult:
    """异步 Reflection：对 Agent 回答做语义层证据校验"""
    if agent_name == "question_agent":
        return ReflectionResult(
            answer=answer, confidence="high", issues=[],
            evidence_sufficient=True, contradictions=[], suggestion="",
        )

    if not answer or not answer.strip():
        return ReflectionResult(
            answer=answer, confidence="low",
            issues=["Agent 未生成回答"],
            evidence_sufficient=False, contradictions=[], suggestion="",
        )

    # 1. 规则层
    rule_result = _rule_reflection(evidence_text, answer, query)

    # 2. 规则置信度足够时跳过 LLM
    if rule_result.confidence == "high" and not rule_result.issues:
        logger.info("Reflection: rule confidence=high, skipping LLM for agent=%s", agent_name)
        return rule_result

    # 3. LLM 层（异步）
    if use_llm and evidence_text and len(evidence_text) > 50:
        return await _allm_reflection(evidence_text, answer, query)

    return rule_result


def reflect(
    answer: str,
    evidence_text: str,
    query: str,
    agent_name: str = "",
    use_llm: bool = True,
) -> ReflectionResult:
    """对 Agent 回答做语义层证据校验

    Args:
        answer: Agent 生成的回答文本
        evidence_text: 检索工具返回的内容（合并后的证据文本）
        query: 用户原始查询
        agent_name: Agent 名称（knowledge_agent 等）
        use_llm: 是否启用 LLM 层（False 时纯规则）

    Returns:
        ReflectionResult 含 issues / confidence / suggestion
    """
    # question_agent 不校验（出题不依赖证据支撑）
    if agent_name == "question_agent":
        return ReflectionResult(
            answer=answer, confidence="high", issues=[],
            evidence_sufficient=True, contradictions=[], suggestion="",
        )

    if not answer or not answer.strip():
        return ReflectionResult(
            answer=answer, confidence="low",
            issues=["Agent 未生成回答"],
            evidence_sufficient=False, contradictions=[], suggestion="",
        )

    # 1. 规则层
    rule_result = _rule_reflection(evidence_text, answer, query)

    # 2. 规则置信度足够时跳过 LLM（省 token）
    if rule_result.confidence == "high" and not rule_result.issues:
        logger.info("Reflection: rule confidence=high, skipping LLM for agent=%s", agent_name)
        return rule_result

    # 3. LLM 层（仅在规则不确定或有明确的证据内容时启用）
    if use_llm and evidence_text and len(evidence_text) > 50:
        return _llm_reflection(evidence_text, answer, query)

    return rule_result


def apply_reflection_to_answer(answer: str, reflection: ReflectionResult) -> str:
    """将 Reflection 的建议追加到回答末尾"""
    if not reflection.suggestion:
        return answer
    return answer.rstrip() + "\n\n" + reflection.suggestion
