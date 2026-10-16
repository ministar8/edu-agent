"""EvidenceVerifier — 对 aretrieve_evidence 返回的 FusedEvidence 做质量校验

规则层校验（零延迟）：证据数量、分数阈值、来源多样性、内容长度、覆盖率

校验结果驱动后续决策：
- pass → 直接使用
- soft_fail → 可用但建议重试（如来源单一）
- hard_fail → 必须重试（如零证据或全部低分）

★ 2026-10-15 owner 裁定 B5：原「LLM 层（可选）相关性判断 / 完整性评估」**整层删除**
  （`_arun_llm_relevance_check` + `use_llm` 开关 + `llm_relevance` 权重及其重分配逻辑）。
  删除前全部调用点恒 `use_llm=False`，该层从未启用；`llm_relevance` 权重在未执行时
  恒定重分配给规则层，留之只会让「可选层」读起来像存在的能力。恢复需按
  EFFECT_PLAN §6 走「新版本 + 全量重跑 + 门禁重录」并重新过冻结清单，不在本轮范围。
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from core.settings import settings
from rag.retrieval.evidence import FusedEvidence, TextEvidence

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════
#  数据结构
# ════════════════════════════════════════════════════════


class Verdict(StrEnum):
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
_MIN_AVG_SCORE = 0.3
_MIN_SOURCE_DIVERSITY = 0.2  # 至少 20% 来源不同
_MIN_CONTENT_LENGTH = 50  # 单条证据最少字符
_MIN_TOTAL_CONTENT_LENGTH = 200  # 总内容最少字符
_MAX_DUPLICATE_RATIO = 0.7  # 重复内容占比上限
_MIN_RERANK_SCORE = 0.1  # rerank 最低分


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
        return CheckResult(name="evidence_count", passed=False, score=0.0, detail="零条文本证据")
    # 1-3 条: 0.5, 4-5: 0.8, 6+: 1.0
    score = min(1.0, 0.3 + 0.15 * n)
    return CheckResult(name="evidence_count", passed=True, score=score, detail=f"证据数: {n}")


def _check_score_quality(fused: FusedEvidence) -> CheckResult:
    """检查证据分数质量"""
    if not fused.text_evidences:
        return CheckResult(name="score_quality", passed=False, score=0.0, detail="无证据可评估")

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
        return CheckResult(
            name="score_quality",
            passed=False,
            score=normalized_avg,
            detail=f"平均分过低: {avg_score:.3f} < {min_avg_score:.3f}",
        )

    # 低分占比惩罚
    low_ratio = low_count / len(scores)
    score = normalized_avg * (1.0 - 0.3 * low_ratio)
    passed = low_ratio < 0.8
    return CheckResult(
        name="score_quality",
        passed=passed,
        score=min(1.0, score),
        detail=f"avg={avg_score:.3f}, max={max_score:.3f}, low_ratio={low_ratio:.1%}",
    )


def _check_source_diversity(fused: FusedEvidence) -> CheckResult:
    """检查来源多样性"""
    if not fused.text_evidences:
        return CheckResult(name="source_diversity", passed=False, score=0.0, detail="无证据")

    sources = [ev.source for ev in fused.text_evidences]
    unique = len(set(sources))
    total = len(sources)
    diversity = unique / total if total > 0 else 0.0

    passed = diversity >= _MIN_SOURCE_DIVERSITY
    # 单一来源 soft_fail
    if unique == 1 and total > 2:
        return CheckResult(
            name="source_diversity",
            passed=False,
            score=diversity * 0.5,
            detail=f"来源单一: 全部来自 '{sources[0]}'",
        )

    return CheckResult(
        name="source_diversity",
        passed=passed,
        score=diversity,
        detail=f"unique={unique}/{total}, diversity={diversity:.1%}",
    )


def _check_content_sufficiency(fused: FusedEvidence) -> CheckResult:
    """检查内容充分性（长度 + 非空）"""
    if not fused.text_evidences:
        return CheckResult(name="content_sufficiency", passed=False, score=0.0, detail="无证据")

    empty_count = sum(
        1 for ev in fused.text_evidences if len(ev.content.strip()) < _MIN_CONTENT_LENGTH
    )
    total_len = sum(len(ev.content) for ev in fused.text_evidences)
    n = len(fused.text_evidences)

    # 空内容占比
    empty_ratio = empty_count / n
    if empty_ratio > 0.5:
        return CheckResult(
            name="content_sufficiency",
            passed=False,
            score=0.2,
            detail=f"空内容占比过高: {empty_ratio:.1%}",
        )

    # 总长度不足
    if total_len < _MIN_TOTAL_CONTENT_LENGTH:
        return CheckResult(
            name="content_sufficiency",
            passed=False,
            score=total_len / _MIN_TOTAL_CONTENT_LENGTH,
            detail=f"总内容过短: {total_len} < {_MIN_TOTAL_CONTENT_LENGTH} 字符",
        )

    score = min(1.0, 0.5 + total_len / 3000)
    return CheckResult(
        name="content_sufficiency",
        passed=True,
        score=score,
        detail=f"total_len={total_len}, empty_ratio={empty_ratio:.1%}",
    )


def _check_duplication(fused: FusedEvidence) -> CheckResult:
    """检查内容重复度"""
    if len(fused.text_evidences) <= 1:
        return CheckResult(name="duplication", passed=True, score=1.0, detail="单条证据无需去重")

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
    return CheckResult(
        name="duplication",
        passed=passed,
        score=1.0 - dup_ratio,
        detail=f"dup_ratio={dup_ratio:.1%} ({dup_count}/{len(fused.text_evidences)})",
    )


def _check_final_context(fused: FusedEvidence) -> CheckResult:
    """检查 final_context 是否为空或过短"""
    ctx = fused.final_context
    if not ctx or not ctx.strip():
        return CheckResult(
            name="final_context", passed=False, score=0.0, detail="final_context 为空"
        )
    if len(ctx) < _MIN_TOTAL_CONTENT_LENGTH:
        return CheckResult(
            name="final_context",
            passed=False,
            score=len(ctx) / _MIN_TOTAL_CONTENT_LENGTH,
            detail=f"final_context 过短: {len(ctx)} 字符",
        )
    return CheckResult(name="final_context", passed=True, score=1.0, detail=f"len={len(ctx)}")


# ── 规则层入口 ──

_RULE_CHECKS = [
    _check_evidence_count,
    _check_score_quality,
    _check_source_diversity,
    _check_content_sufficiency,
    _check_duplication,
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
            results.append(
                CheckResult(name=name, passed=True, score=0.5, detail=f"check error: {e}")
            )
    return results


# ════════════════════════════════════════════════════════
#  综合判定 + 重试建议
# ════════════════════════════════════════════════════════

# 各检查项权重（用于计算 overall_score）
#
# ★ 2026-09-23：随 KG 遗留移除删掉了 `"kg_support": 0.05`。
# **这不是纯删除，会改变 overall_score** —— 该检查在 KG 下线后恒返回
# `passed=True, score=0.5`（常量），占权重 0.05，等于把总分**恒定稀释**向 0.5。
# 删掉后其余权重按比例重新归一化，总分更贴近剩余检查的真实水平。
# 边界效应：当其余检查的加权均值恰在 0.6（PASS 阈值）附近时，判定可能从
# SOFT_FAIL 翻为 PASS。
#
# ★ 复验（2026-09-23，KG 删除完成后）：三条门禁路由**全部通过**，且
#   重排路由 / 真实 embedding 路由的六项指标与基线**逐位相同**；
#   只有默认路由出现确定性差异（category_precision 0.9559→0.9561、
#   mean_evidence_count 5.1000→5.1250）—— 同一命令重跑两次结果**逐位相同**，
#   故跨进程极差为 0，不是抖动。方向为改善，量级为「40 条查询里多出 1 条证据」。
#   ⚠️ 该差异**可归因到改动区间，但无法区分是「工程化归档」还是「KG 移除」所致**
#   （归档后那次复跑未留存具体数值）。最可能路径：overall_score 变化 → 判定变化
#   → 重试分支不同 → 证据条数变化。未进一步定位到具体 query。
_CHECK_WEIGHTS: dict[str, float] = {
    "evidence_count": 0.20,
    "score_quality": 0.20,
    "source_diversity": 0.10,
    "content_sufficiency": 0.15,
    "duplication": 0.05,
    "final_context": 0.15,
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
) -> VerificationResult:
    """异步校验 FusedEvidence 质量（原生 async，一路 await）

    在 async 上下文中使用此函数，避免 asyncio.run() 嵌套风险。

    ★ 2026-10-15 owner 裁定 B5：原 `use_llm` 开关随 LLM 校验层整层删除（调用点恒
      False、从未启用）；函数保留 `query` 形参以稳教既有调用方签名，但不再消费它。

    Args:
        fused: aretrieve_evidence 返回的 FusedEvidence
        query: 原始查询（历史形参，保留兼容；LLM 层删除后不再使用）

    Returns:
        VerificationResult 含 verdict / checks / retry_hints
    """
    # 1. 规则层
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


def _compute_verification(
    fused: FusedEvidence, checks: list[CheckResult]
) -> tuple[float, Verdict, list[str], dict]:
    """从 checks 计算综合分数、判定、原因、重试建议（纯计算，无 I/O）"""
    check_map = {c.name: c for c in checks}
    weighted_sum = 0.0
    weight_total = 0.0
    for name, weight in _CHECK_WEIGHTS.items():
        if name in check_map:
            weighted_sum += check_map[name].score * weight
            weight_total += weight

    overall_score = weighted_sum / weight_total if weight_total > 0 else 0.0
    verdict = _compute_verdict(checks, overall_score)
    reasons = [f"{c.name}: {c.detail}" for c in checks if not c.passed]
    retry_hints = _compute_retry_hints(fused, checks, verdict) if verdict != Verdict.PASS else {}
    return overall_score, verdict, reasons, retry_hints
