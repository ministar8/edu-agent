"""检索前置守卫模块：在 Agent 生成回答前校验检索结果，从源头防幻觉

核心思路：
  传统方案：Agent 生成 → 后治理（打补丁/拦截）→ 浪费计算资源
  本方案：  检索结果 → 前置守卫 → [通过] → Agent 生成
                                  → [拦截] → 强制声明"依据不足"，阻止幻觉产生

两层防线：
  1. 检索结果预审（pre_audit）：校验工具返回内容是否足够支撑回答
  2. Grounding 约束注入（inject_grounding）：将检索结果作为硬约束注入 prompt
"""

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ── 检索结果预审 ──────────────────────────────────────

# 工具返回中表示"无结果"的关键词
_NO_RESULT_KEYWORDS = [
    "未在知识库中找到",
    "暂无相关",
    "未找到相关",
    "检索失败",
    "知识库检索失败",
    "题库中暂无",
    "学习路径检索未找到",
    "标准答案检索未找到",
]

# 工具返回中表示"有结果"的正面信号
_POSITIVE_SIGNALS = [
    "来源依据",
    "来源文件",
    "来源片段",
    "xxx.md",
    "知识图谱",
    ".md",
    "章节",
    "节选",
    "原文",
]


@dataclass
class GuardResult:
    """守卫校验结果"""
    passed: bool = True
    has_sufficient_evidence: bool = False
    all_no_result: bool = False
    evidence_snippets: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    should_inject_grounding: bool = True
    grounding_context: str = ""


def pre_audit_tool_outputs(tool_outputs: list[str], agent_name: str) -> GuardResult:
    """检索结果预审：判断工具返回是否足以支撑回答

    Args:
        tool_outputs: Agent 所有工具调用的返回内容列表
        agent_name: Agent 名称

    Returns:
        GuardResult: 守卫结果，决定是否允许 Agent 继续生成
    """
    if not tool_outputs:
        return GuardResult(
            passed=True,
            has_sufficient_evidence=False,
            warnings=["Agent 未调用任何检索工具"],
            should_inject_grounding=True,
            grounding_context="",
        )

    # 统计有效检索结果
    has_any_result = False
    all_no_result = True
    evidence_snippets: list[str] = []

    for output in tool_outputs:
        if not output or not output.strip():
            continue

        # 检查是否为"无结果"返回
        is_no_result = any(kw in output for kw in _NO_RESULT_KEYWORDS)

        if not is_no_result:
            all_no_result = False
            has_any_result = True
            # 提取正面信号
            for signal in _POSITIVE_SIGNALS:
                if signal in output and output not in evidence_snippets:
                    evidence_snippets.append(output[:200])
                    break

    # 判定证据充分性
    has_sufficient = has_any_result and not all_no_result

    warnings = []
    if all_no_result:
        warnings.append("所有检索工具均返回无结果，Agent 不应编造知识库中不存在的内容")
    elif not has_any_result:
        warnings.append("未获取到有效检索结果")

    return GuardResult(
        passed=True,  # 不阻止执行，但通过 grounding 约束限制生成
        has_sufficient_evidence=has_sufficient,
        all_no_result=all_no_result,
        evidence_snippets=evidence_snippets[:3],
        warnings=warnings,
        should_inject_grounding=True,
        grounding_context="\n\n".join(tool_outputs) if tool_outputs else "",
    )


# ── Grounding 约束注入 ──────────────────────────────────

# 证据充分时的 Grounding 约束
_GROUNDING_PROMPT_SUFFICIENT = """\
【系统强制约束 — 必须严格遵守】
1. 你必须基于上方检索结果回答，不得编造检索结果中没有的知识点、章节、页码或实验数据。
2. 若需要补充检索结果以外的常识，必须明确标注"补充说明（非知识库直接内容）"。
3. 回答中引用的任何来源，必须能在检索结果中找到对应内容。
4. 若检索结果不足以完整回答，必须明确说明"依据不足"，不要用推测填充。
"""

# 证据不足时的 Grounding 约束（更严格）
_GROUNDING_PROMPT_INSUFFICIENT = """\
【系统强制约束 — 证据不足，必须严格遵守】
1. 检索结果未找到充分依据，你不得编造任何知识点、章节、页码或实验数据。
2. 你必须在回答开头明确说明"知识库中暂无充分相关内容"。
3. 可以基于通用常识给出保守参考，但每一部分都必须标注"（通用常识，非知识库内容）"。
4. 不得声称自己看到了不存在的教材章节或来源文件。
5. 不得将推测说成事实。
"""

# 证据完全缺失时的 Grounding 约束（最严格）
_GROUNDING_PROMPT_EMPTY = """\
【系统强制约束 — 无检索结果，严格限制】
1. 所有检索工具均未返回相关内容，你不得编造任何具体知识点或来源。
2. 你必须在回答开头说明"知识库中暂无相关内容，以下为通用参考"。
3. 所有内容均须标注为通用参考，不得伪装为知识库内容。
4. 不得伪造任何教材章节、页码、文件名或实验结果。
"""


def build_grounding_message(guard_result: GuardResult, query: str = "") -> str:
    """根据守卫结果构建 Grounding 约束消息

    Args:
        guard_result: 预审结果
        query: 用户原始查询（用于相关性截断）

    Returns:
        注入到 Agent 输入中的 SystemMessage 内容
    """
    parts: list[str] = []

    # 注入检索结果原文（让 Agent 知道有哪些可用证据）
    if guard_result.grounding_context:
        parts.append("【检索结果原文】\n" + guarding_context_truncate(guard_result.grounding_context, query=query))

    # 根据证据充分性选择约束强度
    if not guard_result.has_sufficient_evidence:
        if not guard_result.evidence_snippets:
            parts.append(_GROUNDING_PROMPT_EMPTY)
        else:
            parts.append(_GROUNDING_PROMPT_INSUFFICIENT)
    else:
        parts.append(_GROUNDING_PROMPT_SUFFICIENT)

    return "\n\n".join(parts)


def guarding_context_truncate(context: str, max_chars: int = 3000, query: str = "") -> str:
    """截断过长的检索结果上下文，优先保留与 query 最相关的片段

    策略：
    1. 将上下文按工具输出边界拆分为独立片段
    2. 按 query 关键词命中数对每个片段评分
    3. 贪心选取得分最高的片段，直到字符预算耗尽
    4. 恢复原始顺序拼接，保证上下文连贯
    """
    if len(context) <= max_chars:
        return context

    chunks = [c.strip() for c in context.split("\n\n") if c.strip()]
    if not chunks or (not query and len(chunks) == 1):
        return context[:max_chars] + "\n\n[...检索结果过长，已截断]"

    # 提取 query 关键词用于相关性评分
    query_terms: set[str] = set()
    if query:
        for m in re.findall(r"[A-Za-z_][A-Za-z0-9_\.]{1,}|[\u4e00-\u9fff]{2,12}", query.lower()):
            query_terms.add(m)
        # 补充原始 query 中的连续片段（2-4字）
        for m in re.findall(r"[\u4e00-\u9fff]{2,4}", query):
            query_terms.add(m.lower())

    def _relevance_score(chunk: str) -> int:
        """计算片段与 query 的相关性分数"""
        if not query_terms:
            return 1  # 无 query 信息时均等对待
        chunk_lower = chunk.lower()
        return sum(1 for t in query_terms if t in chunk_lower)

    # 按相关性评分排序（降序），同分保留原始顺序
    scored = [(i, chunk, _relevance_score(chunk)) for i, chunk in enumerate(chunks)]
    scored.sort(key=lambda x: (-x[2], x[0]))

    # 贪心选取高相关片段，直到字符预算耗尽
    selected: list[tuple[int, str]] = []
    total_chars = 0
    for i, chunk, score in scored:
        if score == 0 and total_chars > 0:
            # 跳过零相关片段（除非还没选任何片段）
            continue
        chunk_len = len(chunk) + 2  # +2 for "\n\n" separator
        if total_chars + chunk_len > max_chars:
            continue  # 超预算则跳过该片段
        selected.append((i, chunk))
        total_chars += chunk_len

    # 如果没有选中任何片段（所有片段都超长），取第一个片段截断
    if not selected and chunks:
        selected.append((0, chunks[0][:max_chars]))

    # 恢复原始顺序
    selected.sort(key=lambda x: x[0])
    result = "\n\n".join(chunk for _, chunk in selected)

    if total_chars < len(context):
        result += "\n\n[...部分检索结果已按相关性筛选截断]"
    return result


# ── 工具输出提取器 ──────────────────────────────────────

def extract_tool_outputs_from_messages(messages: list) -> list[str]:
    """从 Agent 执行结果的消息列表中提取工具调用返回内容

    LangGraph ReAct Agent 的消息格式：
    - HumanMessage / SystemMessage: 输入
    - AIMessage(tool_calls=[...]): Agent 决定调用工具
    - ToolMessage(content=...): 工具返回结果
    - AIMessage(content=...): 最终回答

    Args:
        messages: Agent 执行后的消息列表

    Returns:
        工具返回内容列表
    """
    tool_outputs: list[str] = []
    from langchain_core.messages import ToolMessage
    for msg in messages:
        if isinstance(msg, ToolMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            if content:
                tool_outputs.append(content)
    return tool_outputs


# ── 完整守卫流程 ──────────────────────────────────────

def run_retrieval_guard(tool_outputs: list[str], agent_name: str) -> GuardResult:
    """执行完整的检索前置守卫流程

    Args:
        tool_outputs: 工具调用返回列表
        agent_name: Agent 名称

    Returns:
        GuardResult: 包含预审结果和 Grounding 约束
    """
    guard = pre_audit_tool_outputs(tool_outputs, agent_name)

    if guard.warnings:
        logger.warning(
            "Retrieval guard agent=%s has_evidence=%s warnings=%s",
            agent_name, guard.has_sufficient_evidence, guard.warnings,
        )
    else:
        logger.info(
            "Retrieval guard agent=%s has_evidence=%s passed",
            agent_name, guard.has_sufficient_evidence,
        )

    return guard
