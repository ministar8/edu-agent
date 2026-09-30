"""Answer Leakage Gate（安全门）：practice 证据包不得含答案/题号。

用法：
    uv run python scripts/leakage_gate.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from rag.evidence import FusedEvidence, TextEvidence  # noqa: E402
from rag.evidence_policy import apply_evidence_policy  # noqa: E402
from rag.task_policy import resolve_task_policy  # noqa: E402

_PRACTICE_QUERIES = [
    "给我一道死锁练习题",
    "给我一道 BST 删除练习",
    "出一道哈夫曼编码的计算题",
    "来一道进程同步的题",
]

_QID_RE = re.compile(r"(?:19|20)\d{2}-Q\d+")
_ANS_FIELD_RE = re.compile(r"answer_key|reference_answer", re.I)
_ANS_BODY_RE = re.compile(r"答案[:：]|【答案】")


def _fixture_pack() -> FusedEvidence:
    """构造含真题/答案/解析的候选包（模拟泄漏面）。"""
    return FusedEvidence(
        text_evidences=[
            TextEvidence(
                evidence_id="i1",
                content="## 2019-Q11\n**题干**：BST 删除…\n- A. …\n- B. …",
                source="items.md",
                chunk_id="exam-2019-Q11-items-001",
                metadata={
                    "doc_role": "exam_item",
                    "question_id": "2019-Q11",
                    "answer_key": "B",
                    "reference_answer": "…",
                    "kb_depth": "exams",
                },
            ),
            TextEvidence(
                evidence_id="a1",
                content="解析：故选 B。",
                source="answer.md",
                chunk_id="exam-2019-Q11-answer-001",
                metadata={
                    "doc_role": "exam_answer",
                    "explanation_status": "scan",
                    "answer_key": "B",
                },
            ),
            TextEvidence(
                evidence_id="b1",
                content="BST 删除分三种情况。",
                source="basic.md",
                chunk_id="basic-ds-tree-bst-001",
                metadata={"doc_role": "textbook", "kb_depth": "basic"},
            ),
            TextEvidence(
                evidence_id="m1",
                content="方法：先看孩子数。",
                source="method.md",
                chunk_id="advanced-ds-tree-bst_ops-001",
                metadata={"doc_role": "method", "kb_depth": "advanced"},
            ),
        ],
        final_context="…\n答案：B\n…",
    )


def main() -> int:
    fails: list[str] = []
    fused = _fixture_pack()
    for q in _PRACTICE_QUERIES:
        policy = resolve_task_policy(q)
        if policy.task_mode != "practice":
            fails.append(f"{q!r} classified {policy.task_mode}")
            continue
        out, _flags = apply_evidence_policy(fused, policy)
        blob = str([e.metadata for e in out.text_evidences])
        texts = "\n".join(e.content for e in out.text_evidences)
        ctx = out.final_context or ""
        checks = {
            "no exam_answer chunk": all(
                e.metadata.get("doc_role") != "exam_answer" for e in out.text_evidences
            ),
            "no answer_key meta": not _ANS_FIELD_RE.search(blob),
            "no question_id": not _QID_RE.search(texts + blob),
            "no 答案 body": not _ANS_BODY_RE.search(ctx + "\n" + texts),
        }
        print(f"[practice] {q!r}")
        for name, ok in checks.items():
            print(f"  {name}: {'OK' if ok else 'FAIL'}")
            if not ok:
                fails.append(f"{q}: {name}")
    # 反向：explain 应放行
    p = resolve_task_policy("2019-Q11 为什么选 B？")
    out, _ = apply_evidence_policy(fused, p)
    if not any(e.metadata.get("doc_role") == "exam_answer" for e in out.text_evidences):
        fails.append("explain should keep exam_answer")
    else:
        print("[explain] keeps exam_answer: OK")

    if fails:
        print("LEAKAGE GATE FAIL", len(fails))
        for x in fails:
            print(" -", x)
        return 1
    print("LEAKAGE GATE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
