"""Memory 任务判据：唯一公式仍在 `metrics.memory_correct_use_from_record`，这里只翻成 verdict。

★ `None` 必须能分辨「读链坏了 / 没尝试读」（`missing_premise`，供 Task 1 的
  `memory_read_status` 与 Task 8 归因门追责）与「样本不适用」（`not_applicable`）。
"""

from __future__ import annotations

from evaluation.task_eval import metrics
from evaluation.task_eval.predicates.common import Verdict
from evaluation.task_eval.predicates.registry import Predicate, register


def _correct_use(rec: dict) -> Verdict:
    v = metrics.memory_correct_use_from_record(rec)
    if v is None:
        return (
            "missing_premise"
            if rec.get("memory_read_status") in ("failed", "not_attempted", "")
            else "not_applicable"
        )
    return "pass" if v else "fail"


def _required_always(_rec: object) -> bool:
    return True


register(
    Predicate(
        name="memory_correct_use",
        task="memory",
        tier=1,
        tier_reason=("§1.3-tier1",),
        contract_ref="EFFECT_PLAN.md §3.1 记忆正确使用",
        contract_inputs=(
            "gold.expected_memory",
            "memory_recalled_actual",
            "memory_used",
            "memory_correct",
            "memory_retrieved",
            "memory_forbidden_hits",
        ),
        required_when=_required_always,
        fn=_correct_use,
        falsifier="drop_path:gold.expected_memory",
    )
)
