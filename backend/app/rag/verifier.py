"""EvidenceVerifier — 对 retrieve_evidence 返回的 FusedEvidence 做质量校验

两层校验：
1. 规则层（零延迟）：证据数量、分数阈值、来源多样性、内容长度、覆盖率
2. LLM 层（可选）：相关性判断、完整性评估

校验结果驱动后续决策：
- pass → 直接使用
- soft_fail → 可用但建议重试（如来源单一）
- hard_fail → 必须重试（如零证据或全部低分）
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.config import settings
from app.rag.evidence import FusedEvidence, TextEvidence

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════
#  数据结构
# ════════════════════════════════════════════════════════

class Verdict(str, Enum):
    PASS = "pass"
    SOFT_FAIL = "soft_fail"
    HARD_FAIL = "hard_fail"


class CheckResult(BaseModel):
    """单项检查结果"""
    name: str = Field(description="检查项名称")
    passed: bool = Field(description="是否通过")
    score: float = Field(default=0.0, description="0-1 分数，1=完美")
    detail: str = Field(default="", description="说明")


class VerificationResult(BaseModel):
    """EvidenceVerifier 最终输出"""
    verdict: Verdict = Field(description="综合判定")
    overall_score: float = Field(default=0.0, description="0-1 综合分数")
    checks: list[CheckResult] = Field(default_factory=list, description="各检查项结果")
    reasons: list[str] = Field(default_factory=list, description="失败原因摘要")
    retry_hints: dict[str, Any] = Field(default_factory=dict, description="重试建议参数")


# ════════════════════════════════════════════════════════
#  规则层校验（零延迟）
# ════════════════════════════════════════════════════════

# ── 阈值常量 ──
_MIN_EVIDENCE_COUNT = 1
_MIN_AVG_SCORE = 0.3
_MIN_SOURCE_DIVERSITY = 0.2          # 至少 20% 来源不同
_MIN_CONTENT_LENGTH = 50             # 单条证据最少字符
_MIN_TOTAL_CONTENT_LENGTH = 200      # 总内容最少字符
_MAX_DUPLICATE_RATIO = 0.7          # 重复内容占比上限
_MIN_RERANK_SCORE = 0.1             # rerank 最低分
_MIN_KG_CONFIDENCE = 0.3            # KG 最低置信度


def _primary_score(ev: TextEvidence) -> float:
    """取证据的主分数（避免 or falsy 陷阱）"""
    if ev.rerank_score > 0:
        return ev.rerank_score
    if ev.recall_score > 0:
        return ev.recall_score
    return ev.score or 0.0


def _check_evidence_count(fused: FusedEvidence) -> CheckResult:
    """检查证据数量是否足够"""
    n = len(fused.text_evidences)
    if n == 0:
        if fused.kg_evidences and fused.final_context.strip():
            return CheckResult(name="evidence_count", passed=True, score=0.45,
                                detail=f"无文本证据，使用 KG 证据: {len(fused.kg_evidences)}")
        return CheckResult(name="evidence_count", passed=False, score=0.0,
                            detail="零条文本证据")
    # 1-3 条: 0.5, 4-5: 0.8, 6+: 1.0
    score = min(1.0, 0.3 + 0.15 * n)
    return CheckResult(name="evidence_count", passed=True, score=score,
                        detail=f"证据数: {n}")


def _check_score_quality(fused: FusedEvidence) -> CheckResult:
    """检查证据分数质量"""
    if not fused.text_evidences:
        if fused.kg_evidences:
            avg_conf = sum(ev.confidence for ev in fused.kg_evidences) / len(fused.kg_evidences)
            return CheckResult(name="score_quality", passed=avg_conf >= _MIN_KG_CONFIDENCE,
                                score=avg_conf, detail=f"KG-only avg_conf={avg_conf:.2f}")
        return CheckResult(name="score_quality", passed=False, score=0.0,
                            detail="无证据可评估")

    scores = [_primary_score(ev) for ev in fused.text_evidences]
    has_rerank_score = any(ev.rerank_score > 0 for ev in fused.text_evidences)
    avg_score = sum(scores) / len(scores)
    max_score = max(scores)
    if has_rerank_score:
        min_avg_score = _MIN_AVG_SCORE
        min_single_score = _MIN_RERANK_SCORE
        normalized_avg = avg_score
    else:
        score_threshold = float(fused.metadata.get("score_threshold") or 0.06)
        min_avg_score = max(0.01, score_threshold * 0.8)
        min_single_score = max(0.005, score_threshold * 0.5)
        normalized_avg = min(1.0, avg_score / max(score_threshold * 2.0, 0.01))
    low_count = sum(1 for s in scores if s < min_single_score)

    if avg_score < min_avg_score:
        return CheckResult(name="score_quality", passed=False, score=normalized_avg,
                            detail=f"平均分过低: {avg_score:.3f} < {min_avg_score:.3f}")

    # 低分占比惩罚
    low_ratio = low_count / len(scores)
    score = normalized_avg * (1.0 - 0.3 * low_ratio)
    passed = low_ratio < 0.8
    return CheckResult(name="score_quality", passed=passed, score=min(1.0, score),
                        detail=f"avg={avg_score:.3f}, max={max_score:.3f}, low_ratio={low_ratio:.1%}")


def _check_source_diversity(fused: FusedEvidence) -> CheckResult:
    """检查来源多样性"""
    if not fused.text_evidences:
        if fused.kg_evidences:
            return CheckResult(name="source_diversity", passed=True, score=0.5,
                                detail="KG-only 来源")
        return CheckResult(name="source_diversity", passed=False, score=0.0,
                            detail="无证据")

    sources = [ev.source for ev in fused.text_evidences]
    unique = len(set(sources))
    total = len(sources)
    diversity = unique / total if total > 0 else 0.0

    passed = diversity >= _MIN_SOURCE_DIVERSITY
    # 单一来源 soft_fail
    if unique == 1 and total > 2:
        return CheckResult(name="source_diversity", passed=False, score=diversity * 0.5,
                            detail=f"来源单一: 全部来自 '{sources[0]}'")

    return CheckResult(name="source_diversity", passed=passed, score=diversity,
                        detail=f"unique={unique}/{total}, diversity={diversity:.1%}")


def _check_content_sufficiency(fused: FusedEvidence) -> CheckResult:
    """检查内容充分性（长度 + 非空）"""
    if not fused.text_evidences:
        if fused.kg_evidences and fused.final_context.strip():
            total_len = len(fused.final_context)
            min_len = _MIN_CONTENT_LENGTH
            return CheckResult(name="content_sufficiency",
                                passed=total_len >= min_len,
                                score=min(1.0, total_len / min_len),
                                detail=f"KG-only final_context len={total_len}")
        return CheckResult(name="content_sufficiency", passed=False, score=0.0,
                            detail="无证据")

    empty_count = sum(1 for ev in fused.text_evidences if len(ev.content.strip()) < _MIN_CONTENT_LENGTH)
    total_len = sum(len(ev.content) for ev in fused.text_evidences)
    n = len(fused.text_evidences)

    # 空内容占比
    empty_ratio = empty_count / n
    if empty_ratio > 0.5:
        return CheckResult(name="content_sufficiency", passed=False, score=0.2,
                            detail=f"空内容占比过高: {empty_ratio:.1%}")

    # 总长度不足
    if total_len < _MIN_TOTAL_CONTENT_LENGTH:
        return CheckResult(name="content_sufficiency", passed=False, score=total_len / _MIN_TOTAL_CONTENT_LENGTH,
                            detail=f"总内容过短: {total_len} < {_MIN_TOTAL_CONTENT_LENGTH} 字符")

    score = min(1.0, 0.5 + total_len / 3000)
    return CheckResult(name="content_sufficiency", passed=True, score=score,
                        detail=f"total_len={total_len}, empty_ratio={empty_ratio:.1%}")


def _check_duplication(fused: FusedEvidence) -> CheckResult:
    """检查内容重复度"""
    if len(fused.text_evidences) <= 1:
        return CheckResult(name="duplication", passed=True, score=1.0,
                            detail="单条证据无需去重")

    # 基于前 120 字符的快速去重检测
    seen: set[str] = set()
    dup_count = 0
    for ev in fused.text_evidences:
        key = ev.content[:120].strip()
        if key in seen:
            dup_count += 1
        else:
            seen.add(key)

    dup_ratio = dup_count / len(fused.text_evidences)
    passed = dup_ratio <= _MAX_DUPLICATE_RATIO
    return CheckResult(name="duplication", passed=passed, score=1.0 - dup_ratio,
                        detail=f"dup_ratio={dup_ratio:.1%} ({dup_count}/{len(fused.text_evidences)})")


def _check_kg_support(fused: FusedEvidence) -> CheckResult:
    """检查 KG 证据补充（bonus check，不决定 pass/fail）"""
    if not fused.kg_evidences:
        return CheckResult(name="kg_support", passed=True, score=0.5,
                            detail="无 KG 证据（非必须）")

    avg_conf = sum(ev.confidence for ev in fused.kg_evidences) / len(fused.kg_evidences)
    low_kg = sum(1 for ev in fused.kg_evidences if ev.confidence < _MIN_KG_CONFIDENCE)

    score = min(1.0, 0.5 + avg_conf * 0.5)
    return CheckResult(name="kg_support", passed=True, score=score,
                        detail=f"kg_count={len(fused.kg_evidences)}, avg_conf={avg_conf:.2f}, low={low_kg}")


def _check_final_context(fused: FusedEvidence) -> CheckResult:
    """检查 final_context 是否为空或过短"""
    ctx = fused.final_context
    if not ctx or not ctx.strip():
        return CheckResult(name="final_context", passed=False, score=0.0,
                            detail="final_context 为空")
    if fused.kg_evidences and not fused.text_evidences:
        min_len = _MIN_CONTENT_LENGTH
        if len(ctx) < min_len:
            return CheckResult(name="final_context", passed=False,
                                score=len(ctx) / min_len,
                                detail=f"KG-only final_context 过短: {len(ctx)} 字符")
        return CheckResult(name="final_context", passed=True, score=1.0,
                            detail=f"KG-only len={len(ctx)}")
    if len(ctx) < _MIN_TOTAL_CONTENT_LENGTH:
        return CheckResult(name="final_context", passed=False,
                            score=len(ctx) / _MIN_TOTAL_CONTENT_LENGTH,
                            detail=f"final_context 过短: {len(ctx)} 字符")
    return CheckResult(name="final_context", passed=True, score=1.0,
                        detail=f"len={len(ctx)}")


# ── 规则层入口 ──

_RULE_CHECKS = [
    _check_evidence_count,
    _check_score_quality,
    _check_source_diversity,
    _check_content_sufficiency,
    _check_duplication,
    _check_kg_support,
    _check_final_context,
]


def _run_rule_checks(fused: FusedEvidence) -> list[CheckResult]:
    """执行所有规则检查"""
    results: list[CheckResult] = []
    for check_fn in _RULE_CHECKS:
        try:
            results.append(check_fn(fused))
        except Exception as e:
            name = getattr(check_fn, "__name__", "unknown")
            logger.warning("Rule check %s failed: %s", name, e)
            results.append(CheckResult(name=name, passed=True, score=0.5,
                                        detail=f"check error: {e}"))
    return results


# ════════════════════════════════════════════════════════
#  LLM 层校验（可选，有 token 成本）
# ════════════════════════════════════════════════════════

_LLM_RELEVANCE_PROMPT = """请判断以下检索证据是否与用户查询相关。

用户查询：{query}

检索证据（前5条）：
{evidence_list}

请输出 JSON：
{{"relevant_count": 数字, "irrelevant_count": 数字, "completeness": 0-1浮点数, "reason": "简短说明"}}

只输出 JSON，不要其他内容。"""


async def _arun_llm_relevance_check(
    query: str,
    fused: FusedEvidence,
) -> CheckResult | None:
    """LLM 判断证据相关性与完整性（异步）"""
    if not fused.text_evidences:
        return None

    # 只取前 5 条证据，控制 token
    evidences = fused.text_evidences[:5]
    lines = []
    for i, ev in enumerate(evidences, 1):
        snippet = ev.content[:200].replace("\n", " ")
        lines.append(f"{i}. [{ev.source}] {snippet}")
    evidence_list = "\n".join(lines)

    prompt = _LLM_RELEVANCE_PROMPT.format(query=query, evidence_list=evidence_list)

    try:
        from app.rag.rag_utils import get_llm
        import json as _json

        llm = get_llm(streaming=False, temperature=settings.TEMP_PRECISE)
        raw = await llm.ainvoke(prompt)
        text = str(raw.content if hasattr(raw, "content") else raw).strip()

        # 尝试提取 JSON
        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= start:
            logger.warning("LLM relevance check: 无法解析 JSON")
            return None

        parsed = _json.loads(text[start:end])
        relevant_count = int(parsed.get("relevant_count", 0))
        irrelevant_count = int(parsed.get("irrelevant_count", 0))
        completeness = float(parsed.get("completeness", 0.5))
        reason = str(parsed.get("reason", ""))

        total = relevant_count + irrelevant_count
        if total == 0:
            return None

        relevance_ratio = relevant_count / total
        score = (relevance_ratio * 0.6 + completeness * 0.4)
        passed = relevance_ratio >= 0.5 and completeness >= 0.3

        return CheckResult(
            name="llm_relevance",
            passed=passed,
            score=score,
            detail=f"relevant={relevant_count}/{total}, completeness={completeness:.2f}, {reason}",
        )
    except Exception as e:
        logger.warning("LLM relevance check failed: %s", e)
        return None


# ════════════════════════════════════════════════════════
#  综合判定 + 重试建议
# ════════════════════════════════════════════════════════

# 各检查项权重（用于计算 overall_score）
_CHECK_WEIGHTS: dict[str, float] = {
    "evidence_count": 0.20,
    "score_quality": 0.20,
    "source_diversity": 0.10,
    "content_sufficiency": 0.15,
    "duplication": 0.05,
    "kg_support": 0.05,
    "final_context": 0.15,
    "llm_relevance": 0.10,     # LLM 层可选，未执行时权重重分配
}


def _compute_verdict(checks: list[CheckResult], overall_score: float) -> Verdict:
    """根据检查结果和综合分数判定"""
    # 硬性条件：evidence_count 或 final_context 不通过 → hard_fail
    critical_names = {"evidence_count", "final_context", "score_quality"}
    for c in checks:
        if c.name in critical_names and not c.passed:
            return Verdict.HARD_FAIL

    # 综合分数判定
    if overall_score >= 0.6:
        return Verdict.PASS
    elif overall_score >= 0.35:
        return Verdict.SOFT_FAIL
    else:
        return Verdict.HARD_FAIL


def _compute_retry_hints(
    fused: FusedEvidence,
    checks: list[CheckResult],
    verdict: Verdict,
) -> dict[str, Any]:
    """根据失败原因生成重试参数建议"""
    hints: dict[str, Any] = {}

    failed_checks = {c.name for c in checks if not c.passed}
    base_k = fused.metadata.get("k") or 5
    base_max_tokens = fused.metadata.get("max_tokens") or settings.CONTEXT_TOKEN_BUDGET

    # ── k 值合并：取所有增/减建议的合理值 ──
    k_candidates: list[int] = [base_k]
    if "evidence_count" in failed_checks:
        k_candidates.append(min(10, base_k + 3))
    if "source_diversity" in failed_checks:
        k_candidates.append(min(10, base_k + 2))
    if "final_context" in failed_checks:
        k_candidates.append(min(10, base_k + 3))
    if "duplication" in failed_checks:
        k_candidates.append(max(3, base_k - 1))

    # 如果有增有减，取增的最大值（证据不足比重复更严重）
    increase = [k for k in k_candidates if k > base_k]
    decrease = [k for k in k_candidates if k < base_k]
    if increase:
        hints["k"] = max(increase)
    elif decrease:
        hints["k"] = min(decrease)

    if "score_quality" in failed_checks:
        hints["score_threshold"] = max(0.01, (fused.metadata.get("score_threshold") or 0.012) * 0.5)
        hints["use_rerank"] = True

    if "content_sufficiency" in failed_checks or "final_context" in failed_checks:
        hints["max_tokens"] = min(8000, base_max_tokens + 2000)

    return hints


# ════════════════════════════════════════════════════════
#  公开 API
# ════════════════════════════════════════════════════════

async def averify_evidence(
    fused: FusedEvidence,
    query: str = "",
    use_llm: bool = False,
) -> VerificationResult:
    """异步校验 FusedEvidence 质量（原生 async，一路 await）

    在 async 上下文中使用此函数，避免 asyncio.run() 嵌套风险。

    Args:
        fused: retrieve_evidence 返回的 FusedEvidence
        query: 原始查询（LLM 层需要）
        use_llm: 是否启用 LLM 相关性检查（有 token 成本）

    Returns:
        VerificationResult 含 verdict / checks / retry_hints
    """
    # 1. 规则层
    checks = _run_rule_checks(fused)

    # 2. LLM 层（原生 await）
    if use_llm and query:
        llm_result = await _arun_llm_relevance_check(query, fused)
        if llm_result is not None:
            checks.append(llm_result)

    # 3. 计算综合分数
    overall_score, verdict, reasons, retry_hints = _compute_verification(fused, checks)

    return VerificationResult(
        verdict=verdict,
        overall_score=round(overall_score, 4),
        checks=checks,
        reasons=reasons,
        retry_hints=retry_hints,
    )


def _compute_verification(fused: FusedEvidence, checks: list[CheckResult]) -> tuple[float, Verdict, list[str], dict]:
    """从 checks 计算综合分数、判定、原因、重试建议（纯计算，无 I/O）"""
    active_weights = dict(_CHECK_WEIGHTS)
    has_llm = any(c.name == "llm_relevance" for c in checks)
    if not has_llm:
        llm_weight = active_weights.pop("llm_relevance", 0.10)
        remaining = sum(active_weights.values())
        if remaining > 0:
            for key in active_weights:
                active_weights[key] += llm_weight * (active_weights[key] / remaining)

    check_map = {c.name: c for c in checks}
    weighted_sum = 0.0
    weight_total = 0.0
    for name, weight in active_weights.items():
        if name in check_map:
            weighted_sum += check_map[name].score * weight
            weight_total += weight

    overall_score = weighted_sum / weight_total if weight_total > 0 else 0.0
    verdict = _compute_verdict(checks, overall_score)
    reasons = [f"{c.name}: {c.detail}" for c in checks if not c.passed]
    retry_hints = _compute_retry_hints(fused, checks, verdict) if verdict != Verdict.PASS else {}
    return overall_score, verdict, reasons, retry_hints


def verify_evidence(
    fused: FusedEvidence,
    query: str = "",
    use_llm: bool = False,
) -> VerificationResult:
    """同步校验 FusedEvidence 质量（LEGACY：LLM 校验请使用 await averify_evidence()）

    注意：同步版本不支持 LLM 相关性检查，use_llm 参数被忽略。
    如需 LLM 校验，请使用 await averify_evidence()。

    Args:
        fused: retrieve_evidence 返回的 FusedEvidence
        query: 原始查询（LLM 层需要）
        use_llm: 在同步版本中被忽略，始终仅使用规则层

    Returns:
        VerificationResult 含 verdict / checks / retry_hints
    """
    # 1. 规则层（同步版本不支持 LLM 层）
    checks = _run_rule_checks(fused)

    # 2. 计算综合分数
    overall_score, verdict, reasons, retry_hints = _compute_verification(fused, checks)

    return VerificationResult(
        verdict=verdict,
        overall_score=round(overall_score, 4),
        checks=checks,
        reasons=reasons,
        retry_hints=retry_hints,
    )


def is_retrieval_sufficient(
    fused: FusedEvidence,
    query: str = "",
    use_llm: bool = False,
    min_verdict: Verdict = Verdict.SOFT_FAIL,
) -> bool:
    """快捷判断：检索结果是否足够使用

    比 verify_evidence 更简洁，适合 Agent 内联调用。

    Args:
        fused: FusedEvidence
        query: 原始查询
        use_llm: 是否启用 LLM 校验
        min_verdict: 最低可接受判定（默认 SOFT_FAIL 即 soft_fail 也算通过）

    Returns:
        True 如果 verdict >= min_verdict
    """
    result = verify_evidence(fused, query=query, use_llm=use_llm)
    # Verdict 优先级: PASS > SOFT_FAIL > HARD_FAIL
    priority = {Verdict.PASS: 2, Verdict.SOFT_FAIL: 1, Verdict.HARD_FAIL: 0}
    return priority.get(result.verdict, 0) >= priority.get(min_verdict, 1)
