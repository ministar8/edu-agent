"""R1/R2 冒烟：policy 分类 + Evidence Policy 裁剪 + Answer Leakage 检查。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag.evidence import FusedEvidence, TextEvidence  # noqa: E402
from rag.evidence_policy import apply_evidence_policy  # noqa: E402
from rag.retrieval_policy import classify_task_mode, resolve_retrieval_policy  # noqa: E402


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


if __name__ == "__main__":
    print("==== classify ====")
    test_classify()
    print("==== policy leak ====")
    test_policy_leak()
    print("SMOKE DONE")
