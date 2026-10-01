"""top-up eligibility 对齐回归门禁。

背景：`layer_recall.topup_preferred_layers` 曾只按 kb_depth 补层，
绕过 policy.eligibility_where()，把 verify 禁止的 exam_answer 拉进池
再被 Evidence Policy 裁掉（BST 真题 query 无 L3）。

结构约定：**policy 决定资格，layer_recall 只决定从哪些层补。**

场景：
  1. verify + exams top-up  → answer 不得进候选/最终包；items 可以
  2. grade  + exams        → answer 保持可进（原有行为）
  3. learn/method/practice → top-up 不得绕过 eligibility（禁 L3 全量）
  4. BST「考过哪些真题」    → final 不得含 exam_answer

用法：
    uv run python scripts/topup_eligibility_gate.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

BST_Q = "BST 删除考过哪些真题？"


def _src(ev) -> str:
    meta = ev.metadata or {}
    return str(meta.get("source_file") or meta.get("source") or ev.source or "")


def _role(ev) -> str:
    return str((ev.metadata or {}).get("doc_role") or "")


def _layer(ev) -> str:
    v = str((ev.metadata or {}).get("kb_depth") or "")
    return v if v in ("basic", "advanced", "exams") else "legacy"


def _has_answer(ev) -> bool:
    return _role(ev) == "exam_answer" or _src(ev).endswith("answer.md")


def _has_item(ev) -> bool:
    return _role(ev) == "exam_item" or "items.md" in _src(ev)


async def run_case(name: str, mode: str, query: str) -> list[str]:
    from rag.evidence_policy import apply_evidence_policy, finalize_with_layer_ranking
    from rag.retriever import aretrieve_evidence_with_retry
    from rag.task_policy import policy_for_mode

    fails: list[str] = []
    policy = policy_for_mode(mode)  # type: ignore[arg-type]
    fused, _ = await aretrieve_evidence_with_retry(
        query=query,
        k=5,
        use_rerank=True,
        max_retries=0,
        use_llm_verify=False,
        filter=policy.eligibility_where(),
        preferred_layers=list(policy.preferred_layers),
    )
    pool = list(fused.text_evidences or [])
    packed = finalize_with_layer_ranking(fused, policy, keep=5)
    packed, _ = apply_evidence_policy(packed, policy)
    pack = list(packed.text_evidences or [])

    pool_ans = [ev for ev in pool if _has_answer(ev)]
    pack_ans = [ev for ev in pack if _has_answer(ev)]
    pack_item = [ev for ev in pack if _has_item(ev)]

    print(f"\n[{name}] mode={mode} q={query[:36]}")
    print(f"  preferred={policy.preferred_layers}")
    print(
        f"  pool n={len(pool)} answer_in_pool={len(pool_ans)} item_in_pool={sum(1 for e in pool if _has_item(e))}"
    )
    print(f"  pack n={len(pack)} answer_in_pack={len(pack_ans)} item_in_pack={len(pack_item)}")
    for ev in pack:
        print(f"    pack {_layer(ev):<8} role={_role(ev) or '-':<12} {_src(ev)}")

    if mode == "verify":
        if pack_ans:
            fails.append(f"{name}: verify pack 含 exam_answer ({[_src(e) for e in pack_ans]})")
        if pool_ans:
            fails.append(f"{name}: verify top-up/池内含 exam_answer（应被 eligibility 挡下）")
        # items 允许：不要求必须有，只禁止 answer
    elif mode == "grade":
        # grade 允许 answer：不设为 fail；仅记录
        if not pack_ans and not pack_item:
            print("  (grade 无 answer/item，不判失败)")
    else:
        # learn/method/practice：不得有 exam_answer / exam_item
        if pack_ans:
            fails.append(f"{name}: {mode} pack 含 exam_answer")
        if any(_layer(ev) == "exams" and (_has_answer(ev) or _has_item(ev)) for ev in pack):
            fails.append(f"{name}: {mode} pack 含 exams 考试资源")
        if pool_ans:
            fails.append(f"{name}: {mode} pool 含 exam_answer（top-up 绕过）")

    return fails


async def main() -> int:
    cases = [
        ("verify_answer_blocked", "verify", "BST 删除考过哪些真题？"),
        ("verify_items_allowed", "verify", "Cache 映射方式考过几次？"),
        ("grade_answer_ok", "grade", "请批改：TCP 三次握手是 SYN、SYN+ACK、ACK"),
        ("learn_no_exam", "learn", "什么是死锁？"),
        ("method_no_exam", "method", "BST 删除时双支结点怎么处理？"),
        ("practice_no_exam", "practice", "给我一道死锁练习题"),
        ("bst_special", "verify", BST_Q),
    ]
    all_fails: list[str] = []
    for name, mode, q in cases:
        all_fails += await run_case(name, mode, q)

    print("\n==== top-up eligibility gate ====")
    if all_fails:
        for f in all_fails:
            print(f"  FAIL {f}")
        print(f"{len(all_fails)} failure(s)")
        return 1
    print("  all scenarios PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
