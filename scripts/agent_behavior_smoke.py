"""Agent 输出行为冒烟（真 LLM，软断言）。

第 1 层 `agent_input_contract_gate` 验的是**进 Agent 的输入**；
本脚本验 **Agent 拿到 Evidence Pack 之后怎么说话**：

- empty 不硬答：检索为空时如实说「未检索到」，不开始硬教
- 不编造来源：`来源: X` 的 X 必须出现在 ToolMessage docs 里，且不得编造页码
- search 路径不泄答案：knowledge_search 的 ToolMessage / 回复不得含答案字段
- 多轮约束：practice → 提交作答 → 不崩、不自行给分

★ 这是**软断言冒烟**，不是硬门禁：LLM 有随机性（生产温度 0.3），
  默认宽松匹配以压低误报；`--strict` 把软失败升硬，供本地调提示词用。

用法：
    uv run python scripts/agent_behavior_smoke.py
    uv run python scripts/agent_behavior_smoke.py --strict
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage  # noqa: E402
from langchain_core.runnables import RunnableConfig  # noqa: E402

from agents.agents import DEFAULT_AGENT, get_agent  # noqa: E402

# —— 启发式模式（故意宽松，压低误报）——
_EMPTY_ACK_RE = re.compile(r"未检索到|未找到|没有找到|知识库.{0,6}(未|没有|无)|未覆盖|检索不到")
# 编造页码/教材章节（prompt 明令禁止）
_FAB_PAGE_RE = re.compile(r"第\s*\d+\s*页|P\s*\d{1,4}|《[^》]{1,20}》\s*第\s*\d+\s*章")
# 答案泄漏面（search 路径）
_ANS_FIELD_RE = re.compile(r"answer_key|reference_answer|correct_answer", re.I)
_ANS_BODY_RE = re.compile(r"答案[:：]|【答案】|正确答案|标准答案")
_QID_RE = re.compile(r"(?:19|20)\d{2}-Q\d+")
# 来源标注（prompt 要求末尾纯文本一次）
_SOURCE_RE = re.compile(r"来源[:：]\s*([^\n]+)")
# 自行给分（grading 应走工具，不许自由发挥分数）
_SELF_SCORE_RE = re.compile(r"(?:得分|评分|得分是|我给)\s*[:：]?\s*\d+\s*(?:/\s*\d+)?\s*分?")


@dataclass
class CaseResult:
    name: str
    reply: str = ""
    tool_payloads: list[dict[str, Any]] = field(default_factory=list)
    hard_fails: list[str] = field(default_factory=list)
    soft_fails: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _parse_tool_payload(msg: ToolMessage) -> dict[str, Any] | None:
    raw = msg.content if isinstance(msg.content, str) else json.dumps(msg.content)
    try:
        obj = json.loads(raw)
    except Exception:  # noqa: BLE001
        return None
    return obj if isinstance(obj, dict) else None


async def run_turns(agent, turns: list[str]) -> CaseResult:
    """跑一轮或多轮对话，收集最终回复与 ToolMessage 载荷。"""
    thread = f"smoke-{uuid.uuid4().hex[:10]}"
    config = RunnableConfig(configurable={"thread_id": thread, "user_id": "behavior-smoke"})
    case = CaseResult(name=" | ".join(t[:18] for t in turns))
    reply_parts: list[str] = []

    for text in turns:
        reply_parts.clear()
        try:
            async for ev in agent.astream(
                {"messages": [HumanMessage(content=text)]},
                config=config,
                stream_mode=["messages"],
                subgraphs=True,
            ):
                ns, mode, payload = ev
                if mode != "messages":
                    continue
                msg = payload[0]
                if isinstance(msg, ToolMessage):
                    p = _parse_tool_payload(msg)
                    if p is not None:
                        case.tool_payloads.append(p)
                elif isinstance(msg, AIMessageChunk):
                    reply_parts.append(str(msg.content or ""))
        except Exception as e:  # noqa: BLE001
            case.hard_fails.append(f"invoke 抛错: {type(e).__name__}: {e}")
            return case

    case.reply = "".join(reply_parts).strip()
    if not case.reply:
        case.hard_fails.append("最终回复为空")
    return case


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


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strict", action="store_true", help="软失败升硬（调提示词用）")
    args = ap.parse_args()

    agent = get_agent(DEFAULT_AGENT)
    t0 = time.time()
    results: list[CaseResult] = []

    cases = [
        (
            "empty 不硬答",
            ["2026 年 408 真题第 1 题的官方答案是什么？"],
            lambda c, qs: (check_empty_not_taught(c, qs[0]), check_no_fabricated_sources(c)),
        ),
        (
            "概念题·来源对账",
            ["什么是二叉排序树？"],
            lambda c, qs: (check_no_fabricated_sources(c), check_search_no_answer_leak(c, "learn")),
        ),
        (
            "method·不编造页码",
            ["BST 删除时双支结点怎么处理？"],
            lambda c, qs: (
                check_no_fabricated_sources(c),
                check_search_no_answer_leak(c, "method"),
            ),
        ),
        (
            "多轮 practice→作答",
            ["给我一道 BST 删除的练习题", "我的答案是 C"],
            lambda c, qs: (check_no_self_score(c), check_no_fabricated_sources(c)),
        ),
        (
            "verify·真题列表",
            ["BST 删除考过哪些真题？"],
            lambda c, qs: (
                check_no_fabricated_sources(c),
                check_tool_errors_honestly_reported(c),
            ),
        ),
    ]

    for name, turns, checkers in cases:
        print(f"==== {name} ====")
        case = await run_turns(agent, turns)
        case.name = name
        checkers(case, turns)
        check_tool_errors_honestly_reported(case)
        results.append(case)
        print(f"  reply_len={len(case.reply)} tools={len(case.tool_payloads)}")
        print(f"  reply[:120]={case.reply[:120]!r}")
        for n in case.notes:
            print(f"  note: {n}")
        for f in case.hard_fails:
            print(f"  HARD FAIL: {f}")
        for f in case.soft_fails:
            print(f"  soft-fail: {f}")

    hard = [f"{r.name}: {x}" for r in results for x in r.hard_fails]
    soft = [f"{r.name}: {x}" for r in results for x in r.soft_fails]

    print(f"\n==== 汇总（{time.time() - t0:.0f}s）====")
    print(f"  hard_fail={len(hard)} soft_fail={len(soft)}")
    if hard:
        print("\nAGENT BEHAVIOR HARD FAIL")
        for x in hard:
            print(" -", x)
        return 1
    if soft:
        print("\nsoft failures:")
        for x in soft:
            print(" -", x)
        if args.strict:
            print("AGENT BEHAVIOR FAIL (--strict)")
            return 1
        print("\nAGENT BEHAVIOR PASS（含软失败，未 --strict）")
        return 0
    print("\nAGENT BEHAVIOR PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
