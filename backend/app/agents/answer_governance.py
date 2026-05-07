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
    "knowledge_agent": ["来源依据", "来源", "来源文件", "来源片段", "xxx.md"],
    "grading_agent": ["评分依据", "依据", "标准答案"],
    "path_agent": ["依据来源", "知识图谱", "学习路径文档"],
    "question_agent": [],  # 出题不强制来源字段
}

# 疑似伪造来源的模式
_FORGED_SOURCE_PATTERNS = [
    r"根据教材第\s*\d+\s*章",
    r"根据第\s*\d+\s*章",
    r"教材第\s*\d+\s*节",
    r"课本第\s*\d+\s*页",
]

# 常见废话/寒暄模式
_FILLER_PATTERNS = [
    r"^(当然可以|好的|没问题|当然|下面我来|我来帮你|让我来|以下是|下面是|作为)",
]


def _check_source(answer: str, agent_name: str) -> tuple[bool, list[str]]:
    """检查回答是否包含来源依据"""
    warnings = []
    keywords = _SOURCE_KEYWORDS.get(agent_name, [])
    has_source = any(kw in answer for kw in keywords) if keywords else True

    if not has_source and keywords:
        warnings.append("回答缺少来源依据字段")

    return has_source, warnings


def _check_forged_sources(answer: str) -> list[str]:
    """检查回答是否包含伪造的教材引用"""
    warnings = []
    for pattern in _FORGED_SOURCE_PATTERNS:
        if re.search(pattern, answer):
            warnings.append(f"疑似伪造来源引用: 匹配到 '{pattern}'")
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
        required = ["概念解释", "核心要点"]
        missing = [r for r in required if r not in answer]
        if missing:
            warnings.append(f"知识问答缺少必要字段: {', '.join(missing)}")

    elif agent_name == "grading_agent":
        if "评分" not in answer:
            warnings.append("批改结果缺少评分字段")
        if "评分依据" not in answer and "参考评分" not in answer:
            warnings.append("批改结果缺少评分依据字段")

    elif agent_name == "path_agent":
        if "学习路径" not in answer:
            warnings.append("学习路径推荐缺少路径字段")

    elif agent_name == "question_agent":
        if "题目" not in answer and "题干" not in answer:
            warnings.append("题目生成结果缺少题目字段")

    return warnings


def _determine_confidence(
    has_source: bool, forged_warnings: list[str], format_warnings: list[str]
) -> str:
    """根据校验结果判定置信度"""
    if forged_warnings:
        return "low"
    if not has_source or len(format_warnings) >= 2:
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

    warnings = []
    flags = []

    # 1. 来源依据检查
    has_source, source_warnings = _check_source(answer, agent_name)
    warnings.extend(source_warnings)
    if not has_source:
        flags.append("no_source")

    # 2. 伪造来源检查
    forged_warnings = _check_forged_sources(answer)
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

    # 5. 工具输出交叉验证（如果提供了工具输出）
    if tool_outputs:
        tool_text = " ".join(tool_outputs)
        if "未在知识库中找到" in tool_text or "暂无相关" in tool_text:
            if "依据不足" not in answer and "信息不足" not in answer:
                warnings.append("工具返回无结果，但回答未说明依据不足")
                flags.append("missing_disclaimer")

    # 6. 判定置信度
    confidence = _determine_confidence(has_source, forged_warnings, format_warnings)
    if "missing_disclaimer" in flags and confidence == "high":
        confidence = "medium"

    # 7. 判定是否通过
    passed = confidence != "low" and "forged_source" not in flags

    # 8. 追加降级标注
    governed_answer = _apply_disclaimer(answer, agent_name, warnings, confidence)

    # 日志
    if warnings:
        logger.warning(
            "Answer governance agent=%s confidence=%s flags=%s warnings=%s",
            agent_name, confidence, flags, warnings,
        )
    else:
        logger.info("Answer governance agent=%s confidence=%s passed", agent_name, confidence)

    return GovernanceResult(
        answer=governed_answer,
        passed=passed,
        warnings=warnings,
        flags=flags,
        has_source=has_source,
        confidence=confidence,
    )
