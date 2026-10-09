"""Memory 任务判据：唯一公式仍在 `metrics.memory_correct_use_from_record`，这里只翻成 verdict。

★ `None` 必须能分辨「读链坏了 / 没尝试读 / **根本没记**」（`missing_premise`，供 Task 1 的
  `memory_read_status` 与 Task 8 归因门追责）与「样本本身不适用」（`not_applicable`）。
"""

from __future__ import annotations

from evaluation.task_eval import metrics
from evaluation.task_eval.cases import Gold
from evaluation.task_eval.predicates.common import Verdict, has_path
from evaluation.task_eval.predicates.registry import Predicate, register

# ★ 修复轮 F6：`not_applicable` **只**留给「样本本身不适用」——即 gold 不是可机械判定的
#   memory 样本。判定用**既有谓词** `Gold.memory_mechanizable()`（= `ExpectedMemory.is_valid()`
#   ∧ `ExpectedAnswerProperty.is_valid()`，`cases.py:117/146/278`），**不**用字段真值猜。
#   旧写法 `... if rec.get("memory_read_status") in ("failed","not_attempted","") else
#   "not_applicable"` 把「**键不存在**」（老归档从没写过这个字段，`get` 返回 `None`）
#   划进了 `else` ⇒ 「没有这个证据」被说成「这个样本不适用」，与同包
#   `predicates/common.py:20-27` 的「reason 不明 ⇒ 保守取 `missing_premise`」直接矛盾：
#   实测 `cli._backfill` 会把 **37 条** memory 老归档（三维全 None、无 `memory_read_status`
#   键）的 `item_reasons["memory_correct_use"]` 写成 `not_applicable` —— 那是用 backfill
#   **掩盖缺失前提**（`missing_premise` 的含义正是「证据不足，必须重测/补记」）。
_MISSING_PREMISE_READ_STATUS: frozenset[str] = frozenset({"", "failed", "not_attempted"})


def _correct_use(rec: dict) -> Verdict:
    v = metrics.memory_correct_use_from_record(rec)
    if v is not None:
        return "pass" if v else "fail"
    # —— 三维算不出（None）：先问「样本适不适用」，再问「证据在不在」——
    # ① 样本本身不适用：gold 不是可机械判定的 memory 样本 ⇒ 这才是 `not_applicable`。
    if not Gold.from_dict(rec.get("gold")).memory_mechanizable():
        return "not_applicable"
    # ② 样本适用，但读链证据**缺席**（键根本没有）⇒ `missing_premise`。
    #    ★ 用 `common.has_path` 区分「没有这个键」与「有键且值为空串」——
    #      `rec.get(k)` 两者都给 falsy 值，光看真值分不开（这正是本条 bug 的成因）。
    if not has_path(rec, "memory_read_status"):
        return "missing_premise"  # 键缺失：这条归档从没记过读链状态，无从追责也无从宣布不适用
    # ③ 有键但值为 `""`（未测量）/ `failed`（读链故障）/ `not_attempted`（没 user_id，没读）
    #    ⇒ 同样 `missing_premise`（测不到 ≠ 不适用）。
    if str(rec.get("memory_read_status")) in _MISSING_PREMISE_READ_STATUS:
        return "missing_premise"
    # ④ 读链报「测到了」（`success` / `empty`）却仍算不出三维 ⇒ 前置本身不完整
    #    （例如三维字段没落盘）。★ 依旧保守取 `missing_premise`：本函数**不许**在
    #    「样本不适用」和「证据不足」之间凭猜挑选，而「样本适用 + 声称测到了 + 结果为空」
    #    明显是后者。
    return "missing_premise"


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
