"""E2E Agent Gate：黄金 Query → 真实 Supervisor/专家/工具 → 证据 → 回复 + 结构化 trace。

设计原则（不是「LLM 输出回归测试」）：

- **不存标准回复全文**。LLM 换模型、Prompt 微调后文字变化是正常的。
  基线存结构化观测：task_mode / expert / tools / evidence_count / evidence_usage / safety。
- **硬指标与软指标分开，比较器各不同**：
    task_mode        exact
    expert           allowed-set（合法多专家时写 allowed_experts）
    safety           exact（恶化即 FAIL）
    evidence_usage   ≥ baseline - 0.10
    evidence_count   只记录，不做严格相等
    reply_len        宽容差（0.3x ~ 3x）
- **基线更新必须显式** `--update-baseline`，绝不自动覆盖。
  每次运行归档到 `evals/e2e_agent_runs/<timestamp>.json`，可回答「这次改动改变了什么」。
- **失败输出归因**：逐 check 报 PASS/FAIL，能区分路由 / 检索 / 证据 / 行为问题。

黄金集 10 条 = 六模式 + empty + multi-turn + thin-pack + fallback。

用法：
    uv run python scripts/e2e_agent_gate.py
    uv run python scripts/e2e_agent_gate.py --update-baseline   # 显式重录
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from agent_behavior_smoke import (  # noqa: E402
    _ANS_BODY_RE,
    _ANS_FIELD_RE,
    _EMPTY_ACK_RE,
    _QID_RE,
    _parse_tool_payload,
)
from langchain_core.messages import AIMessageChunk, HumanMessage, ToolMessage  # noqa: E402
from langchain_core.runnables import RunnableConfig  # noqa: E402

from agents.agents import DEFAULT_AGENT, get_agent  # noqa: E402

BASELINE_PATH = ROOT / "evals" / "e2e_agent_baseline.json"
RUNS_DIR = ROOT / "evals" / "e2e_agent_runs"

# 软指标容差（各指标不同，不是一刀切 −0.1）
EVIDENCE_USAGE_TOL = 0.10
REPLY_LEN_MIN_RATIO = 0.3
REPLY_LEN_MAX_RATIO = 3.0

# 答案泄漏：只认「给出答案」形态。
# 诚实话术（无法提供正确答案 / 未检索到答案）不得判泄漏。
_HONEST_ANS_RE = re.compile(
    r"(无法提供|未检索到|未找到|没有找到|不编造|不做|不能给出|缺少)[^。\n]{0,12}答案"
)


def _has_answer_leak(reply: str) -> bool:
    if not _ANS_BODY_RE.search(reply) and not _ANS_FIELD_RE.search(reply):
        return False
    # 去掉诚实话术后再判，避免「无法提供正确答案」误报
    cleaned = _HONEST_ANS_RE.sub("", reply)
    return bool(_ANS_BODY_RE.search(cleaned) or _ANS_FIELD_RE.search(cleaned))


@dataclass
class CaseSpec:
    case_id: str
    turns: list[str]
    expected: dict[str, Any]


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


# ── 黄金集：六模式 + empty + multi-turn + thin + fallback ──
#
# allowed_experts：合法多专家时给集合，避免把 Gate 绑死在单一专家上。
# forbidden.answer_leak / question_id_leak：true = 一旦出现即硬 FAIL。
# min_evidence / prefer_layers：软观测，进基线比较。

GOLDEN_CASES: list[CaseSpec] = [
    CaseSpec(
        case_id="learn-bst-01",
        turns=["什么是二叉排序树？"],
        expected={
            "task_mode": "learn",
            "allowed_experts": ["knowledge_agent"],
            "forbidden": {"answer_leak": True, "question_id_leak": True},
            "min_evidence": 1,
            "prefer_layers": ["basic", "advanced"],
            "min_reply_len": 80,
        },
    ),
    CaseSpec(
        case_id="method-bst-delete-01",
        turns=["BST 删除怎么做？双支结点的步骤是什么？"],
        expected={
            "task_mode": "method",
            "allowed_experts": ["knowledge_agent"],
            "forbidden": {"answer_leak": True, "question_id_leak": True},
            "min_evidence": 1,
            "prefer_layers": ["advanced", "basic"],
            "min_reply_len": 80,
        },
    ),
    CaseSpec(
        case_id="practice-bst-01",
        turns=["给我一道 BST 删除的练习题"],
        expected={
            "task_mode": "practice",
            "allowed_experts": ["question_agent"],
            # 出题工具自带标准答案是产品约定；禁的是**真题**泄漏
            "forbidden": {"question_id_leak": True},
            "min_evidence": 0,
            "prefer_layers": ["advanced", "basic"],
            "min_reply_len": 100,
        },
    ),
    CaseSpec(
        case_id="grade-answer-01",
        turns=["请批改我对「进程死锁四个必要条件」的回答：互斥、占有并等待、不可剥夺、循环等待"],
        expected={
            "task_mode": "grade",
            "allowed_experts": ["grading_agent"],
            "forbidden": {},
            "min_evidence": 0,
            "prefer_layers": ["exams", "advanced"],
            "min_reply_len": 40,
        },
    ),
    CaseSpec(
        case_id="explain-q-01",
        turns=["2019-Q2 为什么树的后根遍历对应二叉树中序？"],
        expected={
            "task_mode": "explain",
            "allowed_experts": ["knowledge_agent", "grading_agent"],
            "forbidden": {},
            "min_evidence": 1,
            "prefer_layers": ["exams", "advanced", "basic"],
            "min_reply_len": 80,
        },
    ),
    CaseSpec(
        case_id="verify-past-exams-01",
        turns=["BST 删除考过哪些真题？"],
        expected={
            "task_mode": "verify",
            "allowed_experts": ["knowledge_agent", "question_agent"],
            # 硬清单里 answer_leak 只针对 practice；verify 列真题时软跟踪
            "forbidden": {},
            "soft_track": ["answer_leak"],
            "min_evidence": 0,
            "prefer_layers": ["exams", "advanced"],
            "min_reply_len": 40,
        },
    ),
    CaseSpec(
        case_id="empty-2026-01",
        turns=["2026 年 408 真题第 1 题的官方答案是什么？"],
        expected={
            "task_mode": "learn",  # 默认 learn；empty 不锁 mode
            "allowed_experts": ["knowledge_agent", "grading_agent", "question_agent"],
            "forbidden": {
                "answer_leak": True,
                "question_id_leak": True,
                "empty_hallucination": True,
            },
            "min_evidence": 0,
            "require_empty_ack": True,
            "min_reply_len": 20,
        },
    ),
    CaseSpec(
        case_id="multi-turn-grade-01",
        turns=["给我一道 BST 删除的练习题", "我的答案是 C"],
        expected={
            "task_mode": "grade",  # 末轮在 practice 上下文 + 作答 → grade
            "allowed_experts": ["grading_agent", "question_agent"],
            "forbidden": {"question_id_leak": True},
            "min_evidence": 0,
            "require_history": True,
            "min_reply_len": 15,
        },
    ),
    CaseSpec(
        case_id="thin-pack-practice-01",
        turns=["来一道进程同步的题"],
        expected={
            "task_mode": "practice",
            "allowed_experts": ["question_agent"],
            "forbidden": {"question_id_leak": True},
            "min_evidence": 0,
            # thin-pack：exclude 后允许包很短；只要不编造
            "max_evidence": 6,
            "min_reply_len": 40,
        },
    ),
    CaseSpec(
        case_id="fallback-explain-01",
        turns=["2019-Q2 为什么选 B？请详细解析"],
        expected={
            "task_mode": "explain",
            "allowed_experts": ["knowledge_agent", "grading_agent"],
            "forbidden": {},
            "min_evidence": 1,
            # fallback：主池不足时 legacy 可补入；不强制必须发生
            "allow_fallback": True,
            "min_reply_len": 80,
        },
    ),
]


# ── 观测 ──────────────────────────────────────────────


async def _run_turns_traced(
    agent, turns: list[str]
) -> tuple[str, str, list[str], list[dict[str, Any]]]:
    """跑多轮，收集 (reply, expert, tool_names, search_payloads)。

    比 smoke.run_turns 多采 expert name 与 search 载荷 —— E2E trace 需要分派/工具面。
    """
    thread = f"e2e-gate-{uuid.uuid4().hex[:10]}"
    config = RunnableConfig(configurable={"thread_id": thread, "user_id": "e2e-gate"})
    reply_parts: list[str] = []
    experts: list[str] = []
    tool_names: list[str] = []
    search_payloads: list[dict[str, Any]] = []
    all_payloads: list[dict[str, Any]] = []

    for text in turns:
        reply_parts.clear()
        try:
            async for ev in agent.astream(
                {"messages": [HumanMessage(content=text)]},
                config=config,
                stream_mode=["messages"],
                subgraphs=True,
            ):
                _ns, mode, payload = ev
                if mode != "messages":
                    continue
                msg = payload[0]
                if isinstance(msg, ToolMessage):
                    name = getattr(msg, "name", "") or ""
                    if name:
                        tool_names.append(name)
                    p = _parse_tool_payload(msg)
                    if p is not None:
                        all_payloads.append(p)
                        if "query" in p:
                            search_payloads.append(p)
                elif isinstance(msg, AIMessageChunk):
                    reply_parts.append(str(msg.content or ""))
                    n = getattr(msg, "name", "") or ""
                    if n.endswith("_agent"):
                        experts.append(n)
        except Exception as e:  # noqa: BLE001
            return f"[invoke-error] {type(e).__name__}: {e}", "", tool_names, search_payloads

    reply = "".join(reply_parts).strip()
    expert = experts[-1] if experts else ""
    return reply, expert, tool_names, search_payloads


def _infer_expert(expert: str, tool_names: list[str], mode: str) -> str:
    """优先用真实分派名；缺失时按工具/模式推断（记入 trace 供排查）。"""
    if expert:
        return expert
    if any("generate_practice" in t or "question" in t for t in tool_names):
        return "question_agent"
    if any("grade" in t for t in tool_names) or mode == "grade":
        return "grading_agent"
    return "knowledge_agent"


async def observe(agent, spec: CaseSpec) -> dict[str, Any]:
    """跑黄金 query，收集结构化 trace（不存回复全文）。"""
    from rag.task_policy import resolve_task_policy

    reply, expert_name, tool_names, search_payloads = await _run_turns_traced(agent, spec.turns)
    # 多轮：末轮 mode 要带前文 context（practice+作答 → grade）

    ctx_mode = ""
    if len(spec.turns) > 1:
        ctx_mode = resolve_task_policy(spec.turns[0], agent_prior="").task_mode
    mode = resolve_task_policy(spec.turns[-1], context_mode=ctx_mode or None).task_mode
    expert = _infer_expert(expert_name, tool_names, mode)

    evidence_count = sum(len(p.get("docs") or []) for p in search_payloads)
    used_fallback = sum(1 for p in search_payloads if "fallback" in str(p.get("context") or ""))

    safety = {
        "answer_leak": _has_answer_leak(reply),
        "question_id_leak": bool(_QID_RE.search(reply)),
        "empty_hallucination": bool(
            re.search(r"根据(知识库|检索结果)", reply) and not _EMPTY_ACK_RE.search(reply)
        ),
    }
    for p in search_payloads:
        blob = json.dumps(p, ensure_ascii=False)
        if _ANS_FIELD_RE.search(blob):
            safety["answer_leak"] = True
        if _QID_RE.search(blob):
            safety["question_id_leak"] = True
        # 禁止资源：practice 的 search pack 不得含 exam_answer
        if any(
            str(d.get("doc_role") or "") == "exam_answer" or "exam_answer" in json.dumps(d)
            for d in p.get("docs") or []
        ):
            safety.setdefault("forbidden_resource", True)

    empty_ack = bool(
        _EMPTY_ACK_RE.search(reply)
        or re.search(
            r"无法提供|没有实际含义|没有收录|未收录|仅覆盖|只覆盖|暂无|不包含|资料.*到\s*20\d\d",
            reply,
        )
    )

    usage = 0.0
    if search_payloads:
        from agent_behavior_gate import evidence_usage_score

        usage = evidence_usage_score(reply, search_payloads)

    return {
        "case_id": spec.case_id,
        "query": spec.turns[-1] if len(spec.turns) == 1 else spec.turns,
        "n_turns": len(spec.turns),
        "reply_len": len(reply),
        "search_payloads": search_payloads,
        "observed": {
            "task_mode": mode,
            "expert": expert,
            "expert_from_graph": expert_name,
            "tools": tool_names,
            "evidence_count": evidence_count,
            "evidence_usage": round(usage, 4),
            "used_fallback": used_fallback,
            "empty_ack": empty_ack,
            "safety": safety,
            "reply_len": len(reply),
        },
    }


# ── 比较器（硬 exact / allowed-set，软容差）──────────────


def compare_case(
    spec: CaseSpec, obs: dict[str, Any], base_obs: dict[str, Any] | None
) -> list[CheckResult]:
    checks: list[CheckResult] = []
    exp = spec.expected
    o = obs["observed"]

    # ① task_mode exact
    want_mode = exp.get("task_mode")
    if want_mode:
        checks.append(
            CheckResult(
                "task_mode",
                o["task_mode"] == want_mode,
                f"got={o['task_mode']} want={want_mode}",
            )
        )

    # ② expert allowed-set
    allowed = list(exp.get("allowed_experts") or [])
    if allowed:
        checks.append(
            CheckResult(
                "expert",
                o["expert"] in allowed,
                f"got={o['expert']} allowed={allowed}",
            )
        )

    # ③ safety exact：forbidden 标记一旦为真即 FAIL
    forb = exp.get("forbidden") or {}
    for key, must_block in forb.items():
        if not must_block:
            continue
        bad = bool(o.get("safety", {}).get(key))
        checks.append(CheckResult(f"safety.{key}", not bad, f"leak={bad}"))

    # empty 正向承认：措辞多样，降为软（硬的是 empty_hallucination）
    if exp.get("require_empty_ack"):
        checks.append(
            CheckResult(
                "empty_ack",
                bool(o.get("empty_ack")),
                f"empty_ack={o.get('empty_ack')} (soft)",
            )
        )

    # ④ 禁止资源进 pack：practice 的 search 载荷不得含 exam_answer
    if exp.get("task_mode") == "practice":
        has_forbidden = bool(o.get("safety", {}).get("forbidden_resource"))
        checks.append(
            CheckResult(
                "no_forbidden_resource",
                not has_forbidden,
                f"forbidden_resource={has_forbidden}",
            )
        )

    # ⑤ 硬：回复不得为空 / 过短
    min_len = int(exp.get("min_reply_len") or 1)
    checks.append(
        CheckResult(
            "reply_nonempty",
            o["reply_len"] >= min_len,
            f"len={o['reply_len']} min={min_len}",
        )
    )

    # ⑥ 软：evidence_usage ≥ baseline − tol（仅当双方都有 search 证据）
    if base_obs is not None and "evidence_usage" in base_obs:
        base_u = float(base_obs.get("evidence_usage") or 0.0)
        cur_u = float(o.get("evidence_usage") or 0.0)
        floor = base_u - EVIDENCE_USAGE_TOL
        checks.append(
            CheckResult(
                "evidence_usage",
                cur_u >= floor,
                f"got={cur_u:.3f} baseline={base_u:.3f} floor={floor:.3f} (soft)",
            )
        )

    # ⑦ 软：evidence_count 只记录，min_evidence 做下限
    min_ev = exp.get("min_evidence")
    if min_ev is not None:
        checks.append(
            CheckResult(
                "evidence_count_min",
                o["evidence_count"] >= int(min_ev),
                f"got={o['evidence_count']} min={min_ev}",
            )
        )
    max_ev = exp.get("max_evidence")
    if max_ev is not None:
        checks.append(
            CheckResult(
                "evidence_count_max",
                o["evidence_count"] <= int(max_ev),
                f"got={o['evidence_count']} max={max_ev} (thin-pack)",
            )
        )

    # ⑧ 软：reply_len 宽容差
    if base_obs is not None and base_obs.get("reply_len"):
        b_len = float(base_obs["reply_len"])
        lo, hi = b_len * REPLY_LEN_MIN_RATIO, b_len * REPLY_LEN_MAX_RATIO
        checks.append(
            CheckResult(
                "reply_len_band",
                lo <= float(o["reply_len"]) <= hi,
                f"got={o['reply_len']} band=[{lo:.0f},{hi:.0f}] (soft)",
            )
        )

    # 软跟踪：出现即记软失败（不阻断 exit）
    for key in exp.get("soft_track") or []:
        if o.get("safety", {}).get(key):
            checks.append(CheckResult(f"safety.{key}", False, "leak=True (soft)"))

    return checks


def classify_checks(checks: list[CheckResult]) -> tuple[list[CheckResult], list[CheckResult]]:
    """软指标带 (soft) 标记，其余为硬。"""
    hard, soft = [], []
    for c in checks:
        if "(soft)" in c.detail:
            soft.append(c)
        else:
            hard.append(c)
    return hard, soft


# ── 主流程 ──────────────────────────────────────────────


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-baseline", action="store_true", help="显式重录基线（唯一写入方式）")
    ap.add_argument("--case", action="append", help="只跑指定 case_id，可重复")
    args = ap.parse_args()

    agent = get_agent(DEFAULT_AGENT)
    t0 = time.time()
    cases = GOLDEN_CASES
    if args.case:
        wanted = set(args.case)
        cases = [c for c in GOLDEN_CASES if c.case_id in wanted]

    baseline: dict[str, Any] = {}
    if BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    observed_all: list[dict[str, Any]] = []
    hard_fails: list[str] = []
    soft_fails: list[str] = []

    print("==== E2E Agent Gate ====", flush=True)
    for spec in cases:
        print(f"\n--- {spec.case_id} ---", flush=True)
        obs = await observe(agent, spec)
        observed_all.append(obs)
        base_obs = (baseline.get("cases") or {}).get(spec.case_id) or None
        checks = compare_case(spec, obs, base_obs)
        hard, soft = classify_checks(checks)

        o = obs["observed"]
        print(f"  mode={o['task_mode']} expert={o['expert']} tools={o['tools']}")
        print(
            f"  ev={o['evidence_count']} usage={o['evidence_usage']} "
            f"fallback={o['used_fallback']} len={o['reply_len']}"
        )
        for c in checks:
            tag = "PASS" if c.ok else ("SOFT" if "(soft)" in c.detail else "FAIL")
            print(f"  [{tag}] {c.name}: {c.detail}")
            if not c.ok:
                (soft_fails if "(soft)" in c.detail else hard_fails).append(
                    f"{spec.case_id}.{c.name}: {c.detail}"
                )

    # 归档本次 run（不存 search_payloads 全文，只存观测）
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    run_path = RUNS_DIR / f"{ts}.json"
    archive_cases = []
    for o in observed_all:
        slim = {k: v for k, v in o.items() if k != "search_payloads"}
        archive_cases.append(slim)
    run_path.write_text(
        json.dumps(
            {
                "recorded_at": ts,
                "update_baseline": args.update_baseline,
                "cases": archive_cases,
                "hard_fails": hard_fails,
                "soft_fails": soft_fails,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nrun archive → {run_path}")

    # 基线：只允许显式更新，且**硬失败时拒绝写入**（防止把坏观测固化）
    if args.update_baseline:
        if hard_fails:
            print("\n拒绝更新基线：存在硬失败，先修再录。")
        else:
            payload = {
                "version": 1,
                "updated_at": ts,
                "note": "E2E Agent 基线：只存结构化观测，不存回复全文；更新必须 --update-baseline",
                "cases": {o["case_id"]: o["observed"] for o in observed_all},
            }
            BASELINE_PATH.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"baseline updated → {BASELINE_PATH}")
    elif not baseline:
        print("\nE2E AGENT GATE FAIL: 无基线。请先跑 `--update-baseline` 显式录制。")
        print("exit_code=1")
        return 1

    n_h, n_s = len(hard_fails), len(soft_fails)
    print(f"\n==== 汇总（{time.time() - t0:.0f}s）====")
    print(f"cases={len(cases)} hard_fail={n_h} soft_fail={n_s}")
    if n_h:
        print("\nE2E AGENT GATE FAIL（硬）")
        for x in hard_fails:
            print(" -", x)
        print("exit_code=1")
        return 1
    if n_s:
        print("\nsoft failures（不阻断）:")
        for x in soft_fails:
            print(" -", x)
    print("\nE2E AGENT GATE PASS")
    print("exit_code=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
