"""R1/R2 冒烟：policy 分类 + Evidence Policy 裁剪 + Answer Leakage 检查。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag.evidence import FusedEvidence, TextEvidence  # noqa: E402
from rag.evidence_policy import (  # noqa: E402
    apply_evidence_policy,
    finalize_with_layer_ranking,
)
from rag.retrieval_policy import (  # noqa: E402
    classify_task_mode,
    policy_for_mode,
    resolve_retrieval_policy,
)


def test_classify() -> None:
    cases = [
        ("什么是死锁？", "learn"),
        ("BST 删除怎么做？", "method"),
        ("给我一道死锁练习题", "practice"),
        ("学生答案是 A，请批改", "grade"),
        ("2019 年第 11 题为什么选 B？", "explain"),
        ("BST 删除考过哪些真题？", "verify"),
    ]
    for q, want in cases:
        got = classify_task_mode(q)
        status = "OK" if got == want else f"FAIL want={want}"
        print(f"  classify {q!r} -> {got} {status}")


def test_policy_leak() -> None:
    item = TextEvidence(
        evidence_id="e1",
        content="## 2019-Q11\n**题干**：…\n- A. …\n- B. …",
        source="items.md",
        chunk_id="exam-2019-Q11-items-001",
        metadata={
            "doc_role": "exam_item",
            "question_id": "2019-Q11",
            "answer_key": "B",
            "reference_answer": "因为…",
            "kb_depth": "exams",
        },
    )
    ans = TextEvidence(
        evidence_id="e2",
        content="解析：故选 B。",
        source="answer.md",
        chunk_id="exam-2019-Q11-answer-001",
        metadata={"doc_role": "exam_answer", "explanation_status": "scan"},
    )
    basic = TextEvidence(
        evidence_id="e3",
        content="BST 中序有序。",
        source="basic.md",
        chunk_id="basic-ds-tree-bst-001",
        metadata={"doc_role": "textbook", "kb_depth": "basic"},
    )
    fused = FusedEvidence(
        text_evidences=[item, ans, basic],
        final_context="…\n答案：B\n…",
    )

    # practice：禁答案、禁题号、禁 exam_answer
    p = resolve_retrieval_policy("给我一道 BST 练习题")
    assert p.task_mode == "practice", p.task_mode
    out, flags = apply_evidence_policy(fused, p)
    texts = " ".join(e.content for e in out.text_evidences)
    meta_blob = str([e.metadata for e in out.text_evidences])
    checks = [
        (
            "no exam_answer",
            all(e.metadata.get("doc_role") != "exam_answer" for e in out.text_evidences),
        ),
        ("no answer_key", "answer_key" not in meta_blob),
        ("no question_id", "2019-Q11" not in texts and "2019-Q11" not in meta_blob),
        ("no 答案：", "答案：" not in (out.final_context or "")),
    ]
    print("[practice leak]", flags)
    for name, ok in checks:
        print(f"  {name}: {'OK' if ok else 'FAIL'}")

    # explain：应保留答案与题
    p2 = resolve_retrieval_policy("2019-Q11 为什么选 B？")
    out2, flags2 = apply_evidence_policy(fused, p2)
    meta2 = str([e.metadata for e in out2.text_evidences])
    print("[explain]", flags2)
    print(f"  answer_key kept: {'OK' if 'answer_key' in meta2 or 'B' in meta2 else 'FAIL'}")
    print(
        f"  exam_answer kept: {'OK' if any(e.metadata.get('doc_role') == 'exam_answer' for e in out2.text_evidences) else 'FAIL'}"
    )


def test_legacy_drop() -> None:
    """legacy 是资产状态不是层：exclude 真删 / fallback 主池不足才补。"""

    # 池策略映射冻结：learn/method/practice/verify exclude；grade/explain fallback
    expect_pool = {
        "learn": "exclude",
        "method": "exclude",
        "practice": "exclude",
        "grade": "fallback",
        "explain": "fallback",
        "verify": "exclude",
    }
    for mode, want in expect_pool.items():
        got = policy_for_mode(mode).legacy_pool_policy  # type: ignore[arg-type]
        print(f"  legacy_pool[{mode}]={got} want={want} {'OK' if got == want else 'FAIL'}")

    def _ev(eid: str, layer: str | None, score: float) -> TextEvidence:
        meta: dict = {"score": score}
        if layer is not None:
            meta["kb_depth"] = layer
        return TextEvidence(
            evidence_id=eid,
            content=f"content-{eid}",
            source="s.md",
            chunk_id=eid,
            score=score,
            metadata=meta,
        )

    # 2 条主池 + 4 条 legacy：exclude 后只剩 2 条，必须标降级
    fused = FusedEvidence(
        text_evidences=[
            _ev("a1", "basic", 0.9),
            _ev("a2", "advanced", 0.8),
            _ev("l1", None, 0.95),
            _ev("l2", "legacy", 0.85),
            _ev("l3", None, 0.7),
            _ev("l4", "legacy", 0.6),
        ],
        final_context="raw",
    )
    p = resolve_retrieval_policy("给我一道 BST 练习题")
    assert p.legacy_pool_policy == "exclude", p.legacy_pool_policy

    out = finalize_with_layer_ranking(fused, p, keep=5)
    layers = [str((e.metadata or {}).get("kb_depth") or "") for e in out.text_evidences]
    lp = (out.metadata or {}).get("layer_pack") or {}
    checks = [
        ("exclude 真删 legacy", all(x in ("basic", "advanced", "exams") for x in layers)),
        ("保留主池 2 条", len(out.text_evidences) == 2),
        ("dropped_legacy=4", lp.get("dropped_legacy") == 4),
        ("不足 keep 显式降级", lp.get("degraded") is True),
        ("used_fallback=0", lp.get("used_fallback") == 0),
    ]
    print("[legacy exclude]", layers, lp)
    for name, ok in checks:
        print(f"  {name}: {'OK' if ok else 'FAIL'}")

    # fallback：主池不足才补 legacy
    fused_fb = FusedEvidence(
        text_evidences=[
            _ev("a1", "basic", 0.9),
            _ev("l1", None, 0.95),
            _ev("l2", None, 0.8),
        ],
        final_context="raw",
    )
    p_fb = policy_for_mode("explain")
    assert p_fb.legacy_pool_policy == "fallback", p_fb.legacy_pool_policy
    out_fb = finalize_with_layer_ranking(fused_fb, p_fb, keep=3)
    layers_fb = [str((e.metadata or {}).get("kb_depth") or "") for e in out_fb.text_evidences]
    lp_fb = (out_fb.metadata or {}).get("layer_pack") or {}
    checks_fb = [
        ("fallback 满包", len(out_fb.text_evidences) == 3),
        ("used_fallback=2", lp_fb.get("used_fallback") == 2),
        ("不降级（已补满）", lp_fb.get("degraded") is False),
        ("主池优先占位", layers_fb[0] == "basic"),
    ]
    print("[legacy fallback]", layers_fb, lp_fb)
    for name, ok in checks_fb:
        print(f"  {name}: {'OK' if ok else 'FAIL'}")

    # 主池够填满：fallback 不启用
    fused_full = FusedEvidence(
        text_evidences=[
            _ev("a1", "basic", 0.9),
            _ev("a2", "advanced", 0.8),
            _ev("a3", "exams", 0.7),
            _ev("l1", None, 0.95),
        ],
        final_context="raw",
    )
    out_full = finalize_with_layer_ranking(fused_full, p_fb, keep=3)
    layers_full = [str((e.metadata or {}).get("kb_depth") or "") for e in out_full.text_evidences]
    lp_full = (out_full.metadata or {}).get("layer_pack") or {}
    ok_full = (
        all(x in ("basic", "advanced", "exams") for x in layers_full)
        and len(out_full.text_evidences) == 3
        and lp_full.get("used_fallback") == 0
        and not lp_full.get("degraded")
    )
    print(f"[fallback 未启用] {layers_full} {lp_full}")
    print(f"  满包不降级: {'OK' if ok_full else 'FAIL'}")


if __name__ == "__main__":
    print("==== classify ====")
    test_classify()
    print("==== policy leak ====")
    test_policy_leak()
    print("==== legacy pool policy ====")
    test_legacy_drop()
    print("SMOKE DONE")
