"""Verify 任务的行为层判据（D14 三条）：全部是 `metrics` 既有函数的 verdict 化。

★ `ver_fabricated` 是 EFFECT_PLAN.md §6 的**硬条件**（必须 0），所以它 required；
  L1/L2 是质量分层诊断（optional），不是硬条件。公式仍只在 `metrics.py` 一处。
"""

from __future__ import annotations

from evaluation.task_eval import metrics
from evaluation.task_eval.predicates.common import Verdict, has_path
from evaluation.task_eval.predicates.registry import Predicate, register


def _no_reply(rec: dict) -> bool:
    """探针没跑（无回复）或检索状态**证据缺席** ⇒ 判据无前提（`missing_premise`）。

    ★ 修复批 Important-2（F6 裁定的镜像项，同包 `memory.py:36-43` 已落同样的区分）：
      旧写法 `rec.get("retrieval_status") == ""` 只把**空串**当未知 ——
      键**缺失**（老归档从没写过这个字段，`get` 返回 `None`）会漏进「可测」分支，
      于是「缺证据」被当成「测到了且通过」（实测：缺键 ⇒ `ver_fabricated = pass`）。
      这与 `predicates/common.py` 的「缺证据 ⇒ 保守取 `missing_premise`」直接矛盾。
    ★ `ok` / `error` / 空串三者的既有语义**不变**：`error` 仍属可测 ——
      reply 本身是可观测物证（tier-1），检索状态只说明证据等级，不使回复消失。
    """
    if rec.get("reply") is None:
        return True
    if not has_path(rec, "retrieval_status"):
        return True  # 键缺失：这条归档从没记过检索状态 ⇒ 无从判定，按缺失前提处理
    return str(rec.get("retrieval_status")) == ""


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
        tier_reason=("§1.3-tier1",),
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
        tier_reason=("§1.3-tier1",),
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
        tier_reason=("§1.3-tier1",),
        contract_ref="EFFECT_PLAN.md §6 年份/来源归属（L2）",
        contract_inputs=("reply", "retrieval_status"),
        required_when=_required_always,
        fn=_exam_year_only,
        falsifier="rewrite_reply_part",
        optional=True,  # 质量分层诊断，非硬条件
    )
)
