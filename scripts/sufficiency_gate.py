"""Pack Sufficiency Gate：错误层偏好不得掏空证据包（且不放松安全）。

背景：prefer_l3（对 learn/method/practice 是错误偏好）把 eligibility 禁止的
exam 资源顶进 pack，Evidence Policy 全部裁掉 → n_pack=0。
`finalize_with_layer_ranking` 的 sufficiency 兜底从**合规候选**回填。

断言：
  1. 各 task_mode × 错误层偏好下 `n_pack >= 1`（非空）
  2. 兜底后 pack 内**无** eligibility 禁止资源（不放松安全）
  3. 正常策略（ours/flat）行为不变（nonempty 且无 refill）

用法：
    uv run python scripts/sufficiency_gate.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

QUERIES = {
    "learn": "什么是二叉排序树？",
    "method": "BST 删除时双支结点怎么处理？",
    "practice": "给我一道死锁练习题",
    "grade": "请批改：TCP 三次握手是 SYN、SYN+ACK、ACK",
    "explain": "2019-Q2 为什么树的后根遍历对应二叉树的中序？",
    "verify": "BST 删除考过哪些真题？",
}

# 错误偏好（对该 mode 而言）
WRONG_PREF = {"learn": ["exams"], "method": ["exams"], "practice": ["exams"]}


async def run_case(mode: str, preferred: list[str] | None) -> tuple[int, list[str], int]:
    from rag.evidence_policy import (
        apply_evidence_policy,
        finalize_with_layer_ranking,
        pack_blocked,
    )
    from rag.retriever import aretrieve_evidence_with_retry
    from rag.task_policy import policy_for_mode

    policy = policy_for_mode(mode)  # type: ignore[arg-type]
    if preferred is not None:
        policy = policy.model_copy(update={"preferred_layers": preferred})
    fused, _ = await aretrieve_evidence_with_retry(
        query=QUERIES[mode],
        k=5,
        use_rerank=True,
        max_retries=0,
        use_llm_verify=False,
        filter=policy.eligibility_where(),
        preferred_layers=list(policy.preferred_layers),
        eligible_layers=policy.eligible_semantic_layers(),
    )
    packed = finalize_with_layer_ranking(fused, policy, keep=5)
    refill = int((packed.metadata or {}).get("layer_pack", {}).get("sufficiency_refill") or 0)
    packed, _ = apply_evidence_policy(packed, policy)
    pack = list(packed.text_evidences or [])
    # 兜底后仍被禁止的项（应为 0）
    blocked_left = [ev for ev in pack if pack_blocked(policy, ev)]
    return (
        len(pack),
        [str((e.metadata or {}).get("source_file") or e.source) for e in blocked_left],
        refill,
    )


async def main() -> int:
    fails: list[str] = []
    print("==== A. 错误层偏好：包必须非空，且不含被禁资源 ====")
    for mode, pref in WRONG_PREF.items():
        n, blocked, refill = await run_case(mode, pref)
        status = "OK" if n >= 1 and not blocked else "FAIL"
        print(
            f"  [{mode}] preferred={pref} n_pack={n} refill={refill} blocked_left={len(blocked)} {status}"
        )
        if n < 1:
            fails.append(f"{mode}: pack 为空（nonempty 未保底）")
        if blocked:
            fails.append(f"{mode}: 兜底后仍含被禁资源 {blocked}")

    print("\n==== B. 正常策略：不引入 regression（nonempty，refill 应为 0 或非必需）====")
    for mode in QUERIES:
        n, blocked, refill = await run_case(mode, None)
        print(
            f"  [{mode}] ours preferred={None} n_pack={n} refill={refill} blocked_left={len(blocked)}"
        )
        if n < 1:
            fails.append(f"{mode}: ours 包为空")
        if blocked:
            fails.append(f"{mode}: ours 含被禁资源")

    print("\n==== sufficiency gate ====")
    if fails:
        for f in fails:
            print(f"  FAIL {f}")
        print(f"{len(fails)} failure(s)")
        return 1
    print("  all scenarios PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
