"""Verify 任务的行为层判据（D14 三条）：全部是 `metrics` 既有函数的 verdict 化。

★ `ver_fabricated` 是 EFFECT_PLAN.md §6 的**硬条件**（必须 0），所以它 required；
  L1/L2 是质量分层诊断（optional），不是硬条件。公式仍只在 `metrics.py` 一处。
"""

from __future__ import annotations

from evaluation.task_eval import metrics
from evaluation.task_eval.predicates.common import Verdict
from evaluation.task_eval.predicates.registry import Predicate, register


def _no_reply(rec: dict) -> bool:
    """探针没跑（无回复）或检索状态未知 ⇒ 判据无前提（`missing_premise`）。"""
    return rec.get("reply") is None or rec.get("retrieval_status") == ""


def _fabricated(rec: dict) -> Verdict:
    if _no_reply(rec):
        return "missing_premise"  # 探针跑/无回复：没测，不是「没编题」
    return "fail" if metrics.verify_fabricated(str(rec["reply"])) else "pass"


def _exam_item_cited(rec: dict) -> Verdict:
    if _no_reply(rec):
        return "missing_premise"
    return "pass" if metrics.verify_exam_item_cited(str(rec["reply"])) else "fail"


def _exam_year_only(rec: dict) -> Verdict:
    if _no_reply(rec):
        return "missing_premise"
    return "pass" if metrics.verify_exam_year_only(str(rec["reply"])) else "fail"


def _required_always(_rec: object) -> bool:
    return True


register(
    Predicate(
        name="ver_fabricated",
        task="verify",
        tier=1,
        contract_ref="EFFECT_PLAN.md §6 编造真题（硬条件，必须 0）",
        contract_inputs=("reply", "retrieval_status"),
        required_when=_required_always,
        fn=_fabricated,
        falsifier="rewrite_reply_part",
    )
)
register(
    Predicate(
        name="ver_exam_item_cited",
        task="verify",
        tier=1,
        contract_ref="EFFECT_PLAN.md §6 真题条目可核对（L1）",
        contract_inputs=("reply", "retrieval_status"),
        required_when=_required_always,
        fn=_exam_item_cited,
        falsifier="rewrite_reply_part",
        optional=True,  # 质量分层诊断，非硬条件
    )
)
register(
    Predicate(
        name="ver_exam_year_only",
        task="verify",
        tier=1,
        contract_ref="EFFECT_PLAN.md §6 年份/来源归属（L2）",
        contract_inputs=("reply", "retrieval_status"),
        required_when=_required_always,
        fn=_exam_year_only,
        falsifier="rewrite_reply_part",
        optional=True,  # 质量分层诊断，非硬条件
    )
)
