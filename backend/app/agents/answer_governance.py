"""回答后治理模块：对 Agent 输出进行校验、降级和标注"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class GovernanceResult:
    """治理结果"""
    answer: str
    passed: bool = True
    warnings: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    has_source: bool = False
    confidence: str = "high"  # high / medium / low


# 各 Agent 期望的来源关键词
_SOURCE_KEYWORDS = {
    "knowledge_agent": ["来源", "来源依据", "来源文件", "来源片段", "Sources", "[来自", "参考", "根据教材", "依据"],
    "grading_agent": ["评分依据", "依据", "标准答案"],
    "path_agent": ["依据来源", "知识图谱", "学习路径文档"],
    "question_agent": [],  # question generation doesn't require source fields
}

# 疑似伪造来源的模式
_FORGED_SOURCE_PATTERNS = [
    r"根据教材第\s*\d+\s*章",
    r"根据第\s*\d+\s*章",
    r"教材第\s*\d+\s*节",
    r"课本第\s*\d+\s*页",
]

# 常见废话/寒暄模式（仅匹配独立语气词，不匹配教学标题）
_FILLER_PATTERNS = [
    r"^(当然可以|好的|没问题|当然|下面我来|我来帮你|让我来|作为)",
]

# 废话前缀的完整匹配模式（用于移除整个废话前缀句）
# 注意："以下是…："和"下面是…："是教学回答的标准标题格式，不删除
_FILLER_STRIP_RE = re.compile(
    r"^(当然可以[。！？\s]*|好的[。！？\s]*|没问题[。！？\s]*"
    r"|当然[。！？\s]*|下面我来[^\n]*?[。！？]\s*"
    r"|我来帮你[^\n]*?[。！？]\s*|让我来[^\n]*?[。！？]\s*"
    r"|作为[^\n]*?[，。！？]\s*)"
)


def _check_source(answer: str, agent_name: str) -> tuple[bool, list[str]]:
    """检查回答是否包含来源依据"""
    warnings = []
    keywords = _SOURCE_KEYWORDS.get(agent_name, [])
    has_source = any(kw in answer for kw in keywords) if keywords else True

    if not has_source and keywords:
        warnings.append("回答缺少来源依据字段")

    return has_source, warnings


def _check_forged_sources(answer: str, tool_outputs: list[str] | None = None) -> list[str]:
    """Cross-reference chapter references with evidence to avoid false positives."""
    warnings = []
    for pattern in _FORGED_SOURCE_PATTERNS:
        matches = re.finditer(pattern, answer)
        for match in matches:
            ref_text = match.group()
            # Verify: does this chapter reference appear in any tool output?
            verified = False
            if tool_outputs:
                for output in tool_outputs:
                    # Check if the referenced chapter name/number appears in evidence
                    ref_key = re.sub(r'[第章节页]', '', ref_text).strip()
                    if ref_key and ref_key in output:
                        verified = True
                        break
            if not verified:
                warnings.append(f"疑似伪造来源引用: {ref_text}（未在检索证据中验证）")
    return warnings


def _ngram_similarity(a: str, b: str, n: int = 3) -> float:
    """计算两个字符串的 n-gram Jaccard 相似度"""
    if len(a) < n or len(b) < n:
        return 0.0
    set_a = {a[i:i+n] for i in range(len(a) - n + 1)}
    set_b = {b[i:i+n] for i in range(len(b) - n + 1)}
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _check_citation_fingerprint(answer: str, tool_outputs: list[str] | None = None) -> list[str]:
    """引用指纹验证：检查回答中的引用声明是否能在证据中找到

    仅在 tool_outputs 可用时执行，纯规则计算 <10ms。
    """
    if not tool_outputs:
        return []

    # 提取回答中的引用声明模式
    citation_patterns = [
        r'根据([^，。！？\n]{2,30})[，。]',
        r'([^，。！？\n]{2,30})中指出[，。]',
        r'([^，。！？\n]{2,30})中提到[，。]',
        r'依据([^，。！？\n]{2,30})[，。]',
    ]
    citations = []
    for pattern in citation_patterns:
        for match in re.finditer(pattern, answer):
            citation = match.group(1).strip()
            if re.search(r"(来源|Source|\.md|第\s*\d+\s*[章节页]|教材|知识图谱)", citation, re.IGNORECASE):
                citations.append(citation)

    if not citations:
        return []

    evidence_text = " ".join(tool_outputs)
    unverified = []
    for citation in citations:
        best_score = _ngram_similarity(citation, evidence_text)
        if best_score < 0.3:
            unverified.append(citation)

    warnings = []
    if unverified:
        warnings.append(f"引用验证：{len(unverified)}/{len(citations)} 条引用未在证据中找到匹配")
    return warnings


def _check_filler(answer: str) -> list[str]:
    """检查回答是否以废话开头"""
    warnings = []
    for pattern in _FILLER_PATTERNS:
        if re.search(pattern, answer[:50]):
            warnings.append("回答以寒暄/废话开头")
            break
    return warnings


def _check_format_compliance(answer: str, agent_name: str) -> list[str]:
    """检查回答是否符合该 Agent 的输出格式"""
    warnings = []

    if agent_name == "knowledge_agent":
        structured_patterns = [
            r"概念解释[：:]",
            r"核心要点[：:]?",
            r"定义",
            r"核心",
            r"要点",
            r"来源依据[：:]?",
            r"\[来源\s*\d+",
            r"\[Source\s*\d+",
        ]
        if not any(re.search(pattern, answer, re.IGNORECASE) for pattern in structured_patterns):
            warnings.append("知识问答建议补充结构化字段（如概念解释、核心要点）以提升可读性")

    elif agent_name == "grading_agent":
        if not re.search(r"评分[：:]", answer) and "评分（参考）" not in answer:
            warnings.append("批改结果缺少评分字段")
        if "评分依据" not in answer and "参考评分" not in answer:
            warnings.append("批改结果缺少评分依据字段")

    elif agent_name == "path_agent":
        if not re.search(r"学习路径[：:]", answer) and "学习路径" not in answer:
            warnings.append("学习路径推荐缺少路径字段")

    elif agent_name == "question_agent":
        if "题目" not in answer and "题干" not in answer:
            warnings.append("题目生成结果缺少题目字段")

    return warnings


def _determine_confidence(
    has_source: bool, forged_warnings: list[str], format_warnings: list[str],
    filler_warnings: list[str] | None = None,
    answer: str = "",
) -> str:
    """Determine confidence from governance checks.
    Semantic evidence overlap is handled by Reflection agent (reflection_agent._rule_signals).
    """
    filler_warnings = filler_warnings or []
    if forged_warnings:
        return "low"
    if answer and len(answer.strip()) < 20:
        return "low"
    if not has_source or len(format_warnings) >= 2:
        return "medium"
    if filler_warnings:
        return "medium"
    return "high"


def _apply_disclaimer(answer: str, agent_name: str, warnings: list[str], confidence: str) -> str:
    """根据治理结果追加降级标注"""
    suffix_parts = []

    if confidence == "low":
        suffix_parts.append("⚠️ 系统提示：此回答可能包含未经验证的内容，请谨慎参考。")

    elif confidence == "medium":
        if "工具返回无结果，但回答未说明依据不足" in warnings:
            suffix_parts.append("补充说明：知识库未检索到充分相关依据，以上内容仅供参考。")

        source_keywords = _SOURCE_KEYWORDS.get(agent_name, [])
        has_explicit_source = any(kw in answer for kw in source_keywords) if source_keywords else False

        if not suffix_parts and not has_explicit_source and agent_name in ("knowledge_agent", "grading_agent", "path_agent"):
            suffix_parts.append("📌 补充说明：以上回答未检索到充分依据，部分内容为模型推断，仅供参考。")

        if agent_name == "grading_agent" and "参考评分" not in answer and "评分依据" not in answer:
            # 在评分行后插入"参考评分"标记
            answer = answer.replace("评分：", "评分（参考）：", 1)

    if suffix_parts:
        answer = answer.rstrip() + "\n\n" + "\n".join(suffix_parts)

    return answer


def govern_answer(answer: str, agent_name: str, tool_outputs: list[str] | None = None) -> GovernanceResult:
    """对 Agent 回答进行后治理

    Args:
        answer: Agent 原始回答
        agent_name: Agent 名称
        tool_outputs: 工具调用返回的内容列表（用于交叉验证来源）

    Returns:
        GovernanceResult: 治理结果，包含修正后的回答和校验信息
    """
    if not answer or not answer.strip():
        return GovernanceResult(
            answer="系统未能生成有效回答，请稍后重试。",
            passed=False,
            warnings=["Agent 返回了空回答"],
            flags=["empty_answer"],
            has_source=False,
            confidence="low",
        )

    timeout_signals = (
        "当前智能体响应超时",
        "检索重试超时",
        "基于证据重写答案超时",
        "响应超时，请稍后重试",
        "timed out",
        "timeout",
    )
    if any(signal in answer for signal in timeout_signals):
        return GovernanceResult(
            answer=answer,
            passed=False,
            warnings=["Agent 响应超时"],
            flags=["timeout_response"],
            has_source=False,
            confidence="low",
        )

    warnings = []
    flags = []

    # 1. 来源依据检查
    has_source, source_warnings = _check_source(answer, agent_name)
    warnings.extend(source_warnings)
    if not has_source:
        flags.append("no_source")

    # 初始置信度：有来源→high，无来源→low（后续根据更多信号调整）
    confidence: str = "high" if has_source else "low"

    # 2. 伪造来源检查
    forged_warnings = _check_forged_sources(answer, tool_outputs)
    warnings.extend(forged_warnings)
    if forged_warnings:
        flags.append("forged_source")

    # 3. 废话检查
    filler_warnings = _check_filler(answer)
    warnings.extend(filler_warnings)
    if filler_warnings:
        flags.append("has_filler")

    # 4. 格式合规检查
    format_warnings = _check_format_compliance(answer, agent_name)
    warnings.extend(format_warnings)
    if format_warnings:
        flags.append("format_violation")

    # 5. 引用指纹验证（检查回答中的引用是否能在证据中找到）
    citation_warnings = _check_citation_fingerprint(answer, tool_outputs)
    warnings.extend(citation_warnings)
    if citation_warnings:
        flags.append("unverified_citation")

    # 6. 工具输出交叉验证（如果提供了工具输出）
    if tool_outputs:
        tool_text = " ".join(tool_outputs)
        if "未在知识库中找到" in tool_text or "暂无相关" in tool_text:
            if "依据不足" not in answer and "信息不足" not in answer:
                warnings.append("工具返回无结果，但回答未说明依据不足")
                flags.append("missing_disclaimer")

    # 7. 移除废话前缀（移除后再判定置信度，避免已修正的废话影响置信度）
    cleaned_answer = _FILLER_STRIP_RE.sub("", answer, count=1)
    filler_was_stripped = cleaned_answer != answer
    if filler_was_stripped:
        answer = cleaned_answer
        logger.info("Stripped filler prefix from answer")

    # 8. 综合判定置信度（综合来源、伪造、格式、长度等信号）
    # 废话已移除则不降级，未移除则降级
    effective_filler_warnings = [] if filler_was_stripped else filler_warnings
    confidence = _determine_confidence(has_source, forged_warnings, format_warnings, effective_filler_warnings, answer)
    if "missing_disclaimer" in flags and confidence == "high":
        confidence = "medium"

    # 9. 判定是否通过
    passed = confidence != "low" and "forged_source" not in flags

    # 10. 追加降级标注
    governed_answer = _apply_disclaimer(answer, agent_name, warnings, confidence)

    # 日志
    if warnings:
        logger.debug(
            "Answer governance agent=%s confidence=%s flags=%s warnings=%s",
            agent_name, confidence, flags, warnings,
        )
    else:
        logger.debug("Answer governance agent=%s confidence=%s passed", agent_name, confidence)

    return GovernanceResult(
        answer=governed_answer,
        passed=passed,
        warnings=warnings,
        flags=flags,
        has_source=has_source,
        confidence=confidence,
    )
