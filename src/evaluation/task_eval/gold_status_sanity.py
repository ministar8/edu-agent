"""gold 侧 `gold_answer_status` 校验（P−1-4 冻结清单 ① / EVIDENCE_CHAIN.md §4.4.7）。

为什么不并进 `gold_sanity.py`
----------------------------
`gold_sanity.py` 现 595 行、仓库自设 600 行上限 —— 与 Task 7 同一条裁定：
**宁可新建文件，也不把 600 行的文件撑爆**。本模块只做「答案状态」这一族检查，
错误形状与 `_check_gold_source_ref` 完全同构（`SanityIssue(case_id, task, ERROR, field, msg)`），
由 `gold_sanity.run_sanity` 在 `_check_gold_source_ref` 之后调用（同一条通道）。

三条检查（批 1 交付 2，逐字对应规格）
------------------------------------
① `gold_answer_status` 键集 **必须等于** `gold_source_ref` 键集 —— 两个方向都查：
   只查「status 有而 ref 无」或反之，都是单边检查（gate 判据 9q 的多一侧键夹具钉死）。
② 值 ∈ `ANSWER_STATUSES`，越界即 ERROR —— 越界值既不折成「没填」也不折成 present。
③ gold 字段有值而该字段在 `gold_answer_status` 里无键 ⇒ ERROR。
   ★ 不得默认 `present`（§4.4.7 第 1 条）：「没标状态」是**证据缺失**，不是「状态可靠」。

★ 本批不回填、不改写任何 dataset/归档 —— dataset 里 `gold_answer_status` 保持不填
  （填它 = 正式盲标开工）。因此 grade 集的「human_score 有值 + 有出处 + 无状态」
  会按 ①③ 新增 ERROR —— 那是**契约收紧的有意红灯**（宁可暴露旧 gold 链缺状态，
  也不为维持绿灯而假定历史数据满足后来才冻结的契约，§4.4.7 末段）。
"""

from __future__ import annotations

from evaluation.task_eval.cases import ANSWER_STATUSES, TaskCase
from evaluation.task_eval.gold_sanity import ERROR, SanityIssue

# 与 `_check_gold_source_ref`（gold_sanity.py:206）逐字相同的字段清单 —— 三处共用一份键空间。
_STATUS_KEYED_FIELDS = ("gold_answer", "expected_difficulty", "human_score")


def check_gold_answer_status(case: TaskCase, out: list[SanityIssue]) -> None:
    """`gold_answer_status` 的键集相等 / 值域 / 有值必有状态（①②③）。"""
    status = case.gold.gold_answer_status or {}
    refs = case.gold.gold_source_ref or {}

    # ② 值域：越界值先单独报 —— 它既不等于「没填」，也不参与「键集相等」的沉默通过。
    for key in sorted(status):
        if status[key] not in ANSWER_STATUSES:
            out.append(
                SanityIssue(
                    case.case_id,
                    case.task,
                    ERROR,
                    "gold_answer_status",
                    f"键 {key!r} 的状态 {status[key]!r} 不在 ANSWER_STATUSES 五值枚举"
                    "（§4.4.2）—— 越界值按错误键统计也不按 present 统计，必须先改回合法值域",
                )
            )

    # ① 键集相等（双向）：`gold_source_ref` 说「出处指向哪里」，`gold_answer_status`
    #    必须并排说出「那里的键处于什么状态」，一侧多键 = 两栏脱节。
    only_refs = sorted(set(refs) - set(status))
    only_status = sorted(set(status) - set(refs))
    if only_refs or only_status:
        parts = []
        if only_refs:
            parts.append(f"status 侧缺 {only_refs}（有出处却无状态）")
        if only_status:
            parts.append(f"出处侧缺 {only_status}（有状态却无出处）")
        out.append(
            SanityIssue(
                case.case_id,
                case.task,
                ERROR,
                "gold_answer_status",
                "键集与 gold_source_ref 不相等：" + "；".join(parts),
            )
        )

    # ③ gold 字段有值而状态缺 ⇒ ERROR（与「有值无出处」同构，不得默认 present）。
    for field_name in _STATUS_KEYED_FIELDS:
        if getattr(case.gold, field_name, None) is not None and status.get(field_name) is None:
            out.append(
                SanityIssue(
                    case.case_id,
                    case.task,
                    ERROR,
                    field_name,
                    "有值但 gold_answer_status 无该键 —— §4.4.7 第 1 条：缺状态不得推断为"
                    " present（填它属于 P−1 盲标开工，本批禁止回填）",
                )
            )


__all__ = ["ERROR", "check_gold_answer_status"]
