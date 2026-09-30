"""Mode / Layer Gate：策略驱动的模式行为与层召回质量。

用法：
    uv run python scripts/mode_layer_gate.py
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

_QID_RE = re.compile(r"(?:19|20)\d{2}-Q\d+")
_ANS_FIELD_RE = re.compile(r"answer_key|reference_answer", re.I)


def _pack() -> FusedEvidence:
    def ev(eid, content, role, layer, **meta):
        m = {"doc_role": role, "kb_depth": layer}
        m.update(meta)
        return TextEvidence(
            evidence_id=eid,
            content=content,
            source=f"{eid}.md",
            chunk_id=f"{eid}-001",
            metadata=m,
        )

    return FusedEvidence(
        text_evidences=[
            ev(
                "ex-item",
                "## 2019-Q11\nBST 删除…",
                "exam_item",
                "exams",
                question_id="2019-Q11",
                answer_key="B",
            ),
            ev("ex-ans", "解析：故选 B。", "exam_answer", "exams", answer_key="B"),
            ev("ex-pap", "2019 整卷语境", "exam_paper", "exams"),
            ev("l1", "BST 定义与性质。", "textbook", "basic"),
            ev("l2", "删除三种情况。", "method", "advanced"),
        ],
        final_context="…",
    )


def _layer_of(ev) -> str:
    return str((ev.metadata or {}).get("kb_depth") or "legacy")


def check_mode_gate() -> list[str]:
    fails: list[str] = []
    fused = _pack()

    cases = {
        "learn": {
            "q": "什么是二叉排序树？",
            "block_roles": {"exam_answer", "exam_item", "exam_paper"},
            "no_answer_fields": True,
        },
        "method": {
            "q": "BST 删除怎么做？",
            "block_roles": {"exam_answer", "exam_item", "exam_paper"},
            "no_answer_fields": True,
        },
        "practice": {
            "q": "给我一道 BST 练习题",
            "block_roles": {"exam_answer", "exam_item", "exam_paper"},
            "no_answer_fields": True,
            "no_qid": True,
        },
        "grade": {
            "q": "2019-Q11 我选 C 对吗？",
            "allow_roles": {"exam_answer"},
            "no_answer_fields": False,
        },
        "explain": {
            "q": "2019-Q11 为什么选 B？",
            "allow_roles": {"exam_answer"},
            "no_answer_fields": False,
        },
        "verify": {
            "q": "BST 删除考过哪些真题？",
            "block_roles": {"exam_answer"},
            "no_answer_fields": True,
        },
    }

    print("==== Mode Gate ====")
    for mode, spec in cases.items():
        p = resolve_task_policy(spec["q"])
        if p.task_mode != mode:
            # grade/explain/verify 依赖信号；容忍并记录
            if not (mode == "grade" and p.task_mode in ("grade", "explain")):
                fails.append(f"mode classify {spec['q']!r} -> {p.task_mode} want {mode}")
                print(f"  [{mode}] classify {p.task_mode} FAIL")
                continue
        out, _ = apply_evidence_policy(fused, p)
        roles = {e.metadata.get("doc_role") for e in out.text_evidences}
        blob = str([e.metadata for e in out.text_evidences])
        texts = "\n".join(e.content for e in out.text_evidences)
        ok = True
        for role in spec.get("block_roles") or set():
            if role in roles:
                fails.append(f"{mode} leaked role {role}")
                ok = False
        for role in spec.get("allow_roles") or set():
            if role not in roles:
                fails.append(f"{mode} missing role {role}")
                ok = False
        if spec.get("no_answer_fields") and _ANS_FIELD_RE.search(blob):
            fails.append(f"{mode} leaked answer fields")
            ok = False
        if spec.get("no_qid") and _QID_RE.search(blob + texts):
            fails.append(f"{mode} leaked question_id")
            ok = False
        # where 前置
        w = p.eligibility_where()
        print(f"  [{p.task_mode}] where={w} {'OK' if ok else 'FAIL'}")
        if spec.get("block_roles") and not w:
            fails.append(f"{mode} eligibility_where empty")
    return fails


def check_layer_gate() -> list[str]:
    """layer recall/precision：按 preferred_layers 与黄金层标注。"""
    fails: list[str] = []
    fused = _pack()
    # 期望层：query → 期望进入 top 的层（简化：以 policy.preferred 与标注为准）
    cases = [
        ("BST 删除怎么做？", "method", {"advanced"}),
        ("什么是二叉排序树？", "learn", {"basic"}),
        ("2019-Q11 为什么选 B？", "explain", {"exams"}),
    ]
    print("==== Layer Gate ====")
    for q, want_mode, expect_layers in cases:
        p = resolve_task_policy(q)
        out, _ = apply_evidence_policy(fused, p)
        layers = [_layer_of(e) for e in out.text_evidences]
        # layer_recall@k：期望层是否出现在结果
        hit = expect_layers.intersection(layers)
        recall = 1.0 if hit else 0.0
        # layer_precision@5：目标偏好层占比
        preferred = set(p.preferred_layers)
        prec = sum(1 for x in layers if x in preferred) / max(len(layers), 1)
        print(
            f"  [{p.task_mode}] {q!r} layers={layers} "
            f"recall@k={recall:.0f} prec@n={prec:.2f} preferred={p.preferred_layers}"
        )
        if recall < 1.0:
            fails.append(f"layer_recall miss {q!r} expect {expect_layers}")
        # 诊断：目标层 chunk 至少有一条
        if not any(x in expect_layers for x in layers):
            fails.append(f"layer target absent {q!r}")
    return fails


def check_eligibility_where() -> list[str]:
    fails: list[str] = []
    print("==== Eligibility Where ====")
    p = resolve_task_policy("给我一道 BST 练习题")
    w = p.eligibility_where()
    blob = str(w)
    for role in ("exam_item", "exam_answer", "exam_paper"):
        if role not in blob:
            fails.append(f"practice where missing block {role}")
    print(f"  practice where={w}")
    p2 = resolve_task_policy("2019-Q11 为什么选 B？")
    w2 = p2.eligibility_where()
    print(f"  explain where={w2}")
    if w2 and "exam_answer" in str(w2) and "$ne" in str(w2):
        # explain 允许 answer，不应 $ne exam_answer
        if re.search(r"exam_answer.*\$ne|\$ne.*exam_answer", str(w2)):
            fails.append("explain where should not block exam_answer")
    return fails


def main() -> int:
    fails = []
    fails += check_eligibility_where()
    fails += check_mode_gate()
    fails += check_layer_gate()
    if fails:
        print("MODE/LAYER GATE FAIL", len(fails))
        for x in fails:
            print(" -", x)
        return 1
    print("MODE/LAYER GATE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
