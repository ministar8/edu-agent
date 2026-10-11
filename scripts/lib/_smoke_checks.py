"""Agent 行为冒烟的软断言检查器（各自读 `CaseResult` 追加 soft_fail/note）。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from _smoke_model import (  # noqa: F401
    _ANS_BODY_RE,
    _ANS_FIELD_RE,
    _EMPTY_ACK_RE,
    _FAB_PAGE_RE,
    _SELF_SCORE_RE,
    _SOURCE_RE,
    CaseResult,
)


def _all_tool_sources(payloads: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for p in payloads:
        for d in p.get("docs") or []:
            src = str(d.get("source") or "")
            if src:
                names.add(src)
                names.add(Path(src).name)
    return names


def check_empty_not_taught(case: CaseResult, query: str) -> None:
    """检索为空时必须如实说未检索到，不得硬着头皮开讲。

    两种诚实形态都算过：
    - 工具返回 empty 且回复转述「未检索到」
    - 专家直接判定超出知识库 / 不在 408 范围（可不调工具）
    """
    payloads = case.tool_payloads
    empties = [p for p in payloads if p.get("status") == "empty"]
    reply = case.reply
    acked = bool(_EMPTY_ACK_RE.search(reply)) or bool(
        re.search(r"无关|不在.{0,6}范围|无法回答|不确定|不展开|没有实际含义", reply)
    )
    if empties:
        if not acked:
            case.soft_fails.append("empty 未被回复如实转述（缺「未检索到」类措辞）")
        if len(reply) > 500 and re.search(r"\*\*核心要点\*\*|## ", reply):
            case.soft_fails.append("empty 却输出讲义式长文（疑似硬答）")
        return
    if not payloads and not acked:
        case.soft_fails.append("既未检索也未拒答（疑似幻觉作答）")
    else:
        case.notes.append("无 empty 载荷（已诚实拒答或检索有命中）")


def check_no_fabricated_sources(case: CaseResult) -> None:
    """来源标注必须对得上 ToolMessage docs；不得编造页码。"""
    reply = case.reply
    if _FAB_PAGE_RE.search(reply):
        case.soft_fails.append(f"回复含编造页码/教材章节: {_FAB_PAGE_RE.search(reply).group(0)!r}")

    sources = _all_tool_sources(case.tool_payloads)
    if not sources:
        return
    for m in _SOURCE_RE.finditer(reply):
        blob = m.group(1)
        # 来源行可能写「06_tree.md（[二叉排序树]）」——取文件名片段核对
        tokens = re.findall(r"[\w一-鿿]+\.md", blob)
        if not tokens:
            continue
        for tok in tokens:
            if not any(tok in s or s.endswith(tok) for s in sources):
                case.soft_fails.append(f"来源标注 {tok!r} 不在 docs 中（疑似编造）")


def check_search_no_answer_leak(case: CaseResult, mode_hint: str) -> None:
    """search 路径（knowledge/text_search）不得泄答案；generate_practice_questions 例外。"""
    has_search_tool = any(p.get("query") is not None for p in case.tool_payloads)
    has_gen = any(
        str(p.get("status")) in ("raw",) or "practice" in str(p)[:200].lower() and "query" not in p
        for p in case.tool_payloads
    )
    # 仅当本轮走的是检索类载荷（有 query 字段）才做泄漏断言
    search_payloads = [p for p in case.tool_payloads if "query" in p]
    if not search_payloads:
        return
    for p in search_payloads:
        msg = json.dumps(p, ensure_ascii=False)
        if _ANS_FIELD_RE.search(msg):
            case.soft_fails.append("search 载荷含答案字段")
        # practice/learn/search 的 context 不得有答案正文
        if mode_hint in ("practice", "learn", "method") and _ANS_BODY_RE.search(
            str(p.get("context") or "")
        ):
            case.soft_fails.append("search context 含答案正文")
    if has_gen:
        case.notes.append("含 generate_practice_questions（题目带标准答案属预期，跳过泄漏断言）")
    if not has_search_tool and not search_payloads:
        case.notes.append("本轮未见 search 载荷")


def check_no_self_score(case: CaseResult) -> None:
    """批改不得自行给分（应走 grade_student_answer 工具）。"""
    m = _SELF_SCORE_RE.search(case.reply)
    if m and case.tool_payloads:
        # 有工具分时，回复里再写一个不同的自由分数要警惕；只做软提示
        case.notes.append(f"回复含分数字样: {m.group(0)!r}（请人工确认是否工具返回）")


def check_tool_errors_honestly_reported(case: CaseResult) -> None:
    """工具失败必须如实转述（prompt 约定）。

    口径收紧：仅当**没有可用证据**（全错 / 空 context）时才要求回复说明失败；
    有成功载荷时，不必叙述每一个工具抖动。
    """
    if not case.tool_payloads:
        return
    ok_payloads = [
        p
        for p in case.tool_payloads
        if p.get("status") in ("ok", "raw") and str(p.get("context") or "").strip()
    ]
    err_payloads = [
        p
        for p in case.tool_payloads
        if p.get("status") == "error" or "失败" in str(p.get("context") or "")
    ]
    if not err_payloads or ok_payloads:
        return
    if not re.search(r"失败|不可用|未能|无法|错误", case.reply):
        case.soft_fails.append("工具全错但回复未如实转述")
    else:
        case.notes.append("工具全错且回复已如实转述（行为符合预期）")
