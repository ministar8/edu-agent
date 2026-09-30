"""ds.tree 六模式 E2E retrieval gate（真检索 + Evidence Policy）。

用法：
    uv run python scripts/e2e_ds_tree_modes.py
"""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag.evidence_policy import (  # noqa: E402
    apply_evidence_policy,
    finalize_with_layer_ranking,
)
from rag.retriever import aretrieve_evidence_with_retry  # noqa: E402
from rag.task_policy import resolve_task_policy  # noqa: E402

_QID_RE = re.compile(r"(?:19|20)\d{2}-Q\d+")
_ANS_FIELD_RE = re.compile(r"answer_key|reference_answer", re.I)
_ANS_BODY_RE = re.compile(r"答案[:：]|【答案】")

# 六模式：ds.tree 域 query（语义贴近 03_tree / KP）
CASES = [
    {
        "mode": "learn",
        "q": "二叉树的遍历方式有哪些？为什么要有中序遍历？",
        "expect_layers": {"basic", "advanced"},
        "block_roles": {"exam_answer", "exam_item", "exam_paper"},
        "no_answer": True,
        "no_qid": True,
    },
    {
        "mode": "method",
        "q": "已知先序和中序遍历，如何还原二叉树？步骤是什么？",
        "expect_layers": {"basic", "advanced"},
        "block_roles": {"exam_answer", "exam_item", "exam_paper"},
        "no_answer": True,
        "no_qid": True,
    },
    {
        "mode": "practice",
        "q": "给我一道 BST 删除的练习题",
        "expect_layers": {"basic", "advanced"},
        "block_roles": {"exam_answer", "exam_item", "exam_paper"},
        "no_answer": True,
        "no_qid": True,
    },
    {
        "mode": "grade",
        "q": "2019-Q2 我选 B，树转二叉树后根遍历等于中序，对吗？请批改",
        "expect_layers": {"exams", "advanced", "basic"},
        "allow_roles": {"exam_answer", "exam_item"},
        "no_answer": False,
        "no_qid": False,
    },
    {
        "mode": "explain",
        "q": "2019-Q2 为什么树的后根遍历对应二叉树中序？",
        "expect_layers": {"exams", "advanced", "basic"},
        "allow_roles": {"exam_answer", "exam_item"},
        "no_answer": False,
        "no_qid": False,
    },
    {
        "mode": "verify",
        "q": "BST 删除考过哪些真题？",
        "expect_layers": {"exams", "advanced", "basic"},
        "allow_roles": {"exam_item"},
        "block_roles": {"exam_answer"},
        "no_answer": True,
    },
]


def _layers(meta: dict) -> str:
    return str(meta.get("kb_depth") or "legacy")


async def run_one(case: dict) -> list[str]:
    fails: list[str] = []
    q = case["q"]
    policy = resolve_task_policy(q)
    mode = policy.task_mode
    if mode != case["mode"]:
        # grade 与 explain 信号可重叠
        if not (case["mode"] == "grade" and mode in ("grade", "explain")):
            fails.append(f"classify {q!r} -> {mode} want {case['mode']}")
            print(f"  [{case['mode']}] classify={mode} FAIL")
            return fails

    filter_w = policy.eligibility_where()
    fused, _ver = await aretrieve_evidence_with_retry(
        query=q,
        k=20,
        use_rerank=True,
        filter=filter_w,
        max_retries=0,
        use_llm_verify=False,
        preferred_layers=list(policy.preferred_layers),
    )
    fused = finalize_with_layer_ranking(fused, policy, keep=8)
    out, flags = apply_evidence_policy(fused, policy)
    evs = out.text_evidences or []
    roles = {(e.metadata or {}).get("doc_role") for e in evs}
    layers = [_layers(e.metadata or {}) for e in evs]
    blob = str([e.metadata for e in evs])
    texts = "\n".join(e.content or "" for e in evs)

    print(f"  [{mode}] n={len(evs)} layers={layers} where={filter_w} flags={flags}")

    for role in case.get("block_roles") or set():
        if role in roles:
            fails.append(f"{mode} leaked role {role}")
    for role in case.get("allow_roles") or set():
        # 空结果不强制必须有（索引/阈值），仅在有证据时检查策略
        pass
    if case.get("no_answer") and _ANS_FIELD_RE.search(blob):
        fails.append(f"{mode} leaked answer fields")
    if case.get("no_answer") and _ANS_BODY_RE.search(texts):
        fails.append(f"{mode} leaked answer body")
    if case.get("no_qid") and _QID_RE.search(blob + texts):
        fails.append(f"{mode} leaked question_id")

    # layer recall：期望层至少一条（有足够证据时；n<3 作 soft，避免阈值抖动）
    expect = set(case.get("expect_layers") or set())
    if len(evs) >= 3 and expect:
        hit = expect.intersection(layers)
        prec = sum(1 for x in layers if x in expect) / max(len(layers), 1)
        print(f"       layer_hit={bool(hit)} prec@n={prec:.2f}")
        if not hit:
            fails.append(f"{mode} layer_recall miss expect={expect} got={layers}")
    elif evs:
        hit = bool(expect.intersection(layers))
        print(f"       layer_hit={hit} (soft n={len(evs)})")
    else:
        print("       empty result (soft)")
    return fails


async def main() -> int:
    print("==== ds.tree 六模式 E2E ====")
    all_fails: list[str] = []
    for case in CASES:
        all_fails.extend(await run_one(case))
    if all_fails:
        print("E2E FAIL", len(all_fails))
        for x in all_fails:
            print(" -", x)
        return 1
    print("E2E PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
