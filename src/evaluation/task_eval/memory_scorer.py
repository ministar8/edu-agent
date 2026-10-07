"""Memory 三维主指标的**机械判定**（judge 不参与）。

设计动机
--------
Phase 1.5 之前，Memory 的三个维度由 judge 一次 LLM 调用顺带判定
（`judge.py` 旧实现：`record.memory_retrieved = output.memory_retrieved`）。
实测暴露两类问题：

1. **主观误判**：`recalled` 是**客观事实**（记忆卡里到底有没有），却由 LLM 凭回复猜；
2. **三态不一致**：`mem-004` 的 `memory_correct` 被判成 `None`，
   而 `memory_correct_use` 要求三者全非 None ⇒ 主指标**凭空变 N/A**。

现在改为：`load_memory` 注入的记忆卡被 harness 按固定 ID 机械捕获
（`CaseResult.memory_cards`），`recalled` 直接读它 —— **事实就是事实，不问 LLM**。

判定口径（与 `cases.py` 的 gold 契约一一对应）
--------------------------------------------
::

    recalled_actual = 任一 card 含 expected_memory.values 中任一值
    recalled_pass   = recalled_actual == expected_memory.should_be_recalled
    used            = 回复含 expected_memory.values 中任一值
    correct         = used and 回复不含 forbidden_values 中任一值

★ 关于 `recalled_pass`：**不能**只报 `recalled_actual`。
  `should_be_recalled=False` 是**负样本**（期望这条记忆**不**被召回）。
  此时 `actual=False` 是**通过**，若直接写进 `memory_retrieved` 会被读成失败。
  故进主指标的是 `pass`（与期望对齐的结果），`actual` 只作诊断保留。

★ 关于 `correct` 的表达力边界（**已知且已声明**）：
  字符串包含判定只能抓「明确列出的错误值」。若回复既含正确值又含
  `forbidden_values`（如「建议先看图论，但重点在数据结构」），会被判 `correct=False`
  —— 这是**下界**（可能低估），不会高估。`forbidden_values` 应只放
  **明确有害**的词（如把弱项说反），不要把正常论述词放进去。

★ 不在此处调用任何 LLM。本模块**零 token 成本**，可离线单测。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evaluation.task_eval.cases import (
    ExpectedAnswerProperty,
    ExpectedMemory,
    Gold,
    SetupConditions,
)

__all__ = [
    "MemoryJudgement",
    "ValidityResult",
    "check_case_validity",
    "judge_memory_mechanically",
    "judgement_to_dict",
    "validity_to_dict",
]


@dataclass(frozen=True)
class MemoryJudgement:
    """Memory 三项判定结果 + 诊断所需原始事实。

    进报告主指标的是 `recalled_pass` / `used` / `correct`；
    `recalled_actual` 与 `hit_values` / `forbidden_hits` 仅供排查，
    **不参与**任何比率计算。
    """

    # —— 进主指标 ——
    recalled_pass: bool | None = None
    used: bool | None = None
    correct: bool | None = None

    # —— 诊断（不进指标）——
    recalled_actual: bool | None = None
    should_be_recalled: bool | None = None
    hit_values: tuple[str, ...] = ()  # 记忆卡里命中的期望值
    reply_hit_values: tuple[str, ...] = ()  # 回复里命中的期望值
    forbidden_hits: tuple[str, ...] = ()  # 回复里命中的禁止值

    @property
    def correct_use(self) -> bool | None:
        """主指标：记忆是否被**正确使用**（任一判定量为 None ⇒ None）。

        ★ 为什么要按样本极性分定义（2026-10-07 修 #4）。旧口径是
        `recalled_pass ∧ used ∧ correct`，而当时 `used` 只看**回复里有没有出现期望值**，
        于是负样本出现两个方向都错的结论：

        * 回复**碰巧**提到该值（其实来自 RAG 证据或题面本身）⇒ `used=True` ⇒ 判「正确使用记忆」
          —— **假阳性**（实测 `mem-006`：记忆卡为空、什么都没召回，却记为通过）；
        * 规规矩矩没凭空用记忆（`used=False`）⇒ AND 失败 ⇒ 判**不通过**
          —— **假阴性**（实测 `mem-004`/`mem-005` 全被判 False）。

        即「**负样本只有碰巧提到才算通过**」，与 §2.B.4 想测的东西正好相反。
        现在把「用了记忆」这件事钉回它的事实前提（`recalled_actual`），两极性分别定义：

        * **正样本**：实际召回 ∧ `used` ∧ `correct`；
        * **负样本**：未实际召回 ∧ **未误用**（回复不含任何 `forbidden_values`）。

        ★ 公式**不在此处实现** —— 委托 `metrics.memory_correct_use`（2026-10-07 修 #21：
          此前三处各写一份，`runner.CaseRecord` 那份没跟着 #4 改 ⇒ 极性版从未落进归档，
          报告一直印旧口径 2/6）。单一公式在 `metrics`，护栏 ⑱ 断言三处一致。
        """
        from evaluation.task_eval import metrics

        return metrics.memory_correct_use(
            should_be_recalled=self.should_be_recalled,
            recalled_actual=self.recalled_actual,
            used=self.used,
            correct=self.correct,
            recalled_pass=self.recalled_pass,
            forbidden_hits=self.forbidden_hits,
        )


def _hits(text: str, needles: list[str]) -> tuple[str, ...]:
    """text 中命中的 needle（保持 needle 原序，去重）。"""
    if not text:
        return ()
    out: list[str] = []
    for n in needles:
        if n and n in text and n not in out:
            out.append(n)
    return tuple(out)


def judge_memory_mechanically(
    *,
    memory_cards: list[str],
    reply: str,
    gold: Gold,
) -> MemoryJudgement:
    """按 gold 契约**机械**判定 Memory 三维。gold 不合法 ⇒ 三项全 None（记 N/A）。

    Parameters
    ----------
    memory_cards:
        harness 从 `load_memory` 注入的 SystemMessage 机械捕获的**记忆卡正文**列表
        （`CaseResult.memory_cards`）。空列表 = 全程没有注入过记忆卡
        ⇒ `recalled_actual=False`（**不是**「未测量」—— 没注入就是没召回）。
    reply:
        被测会话的**最终回复**（`CaseResult.reply`）。多段会话时应传
        **读取段**（最后一段）的回复 —— 召回发生在后段。
    gold:
        该 case 的 gold；需含合法的 `expected_memory` 与 `expected_answer_property`。

    Returns
    -------
    MemoryJudgement
        gold 不可机械判定时返回**全 None** 的实例（由 `gold_sanity` 报 PENDING），
        **绝不**回退到 judge 猜测。
    """
    em: ExpectedMemory | None = gold.expected_memory
    eap: ExpectedAnswerProperty | None = gold.expected_answer_property
    if not gold.memory_mechanizable():
        # gold 未标注/非法：三项都不可判 ⇒ 全 None（N/A，不进分母）
        return MemoryJudgement()

    assert em is not None and eap is not None  # memory_mechanizable() 已保证
    assert em.should_be_recalled is not None
    assert eap.forbidden_values is not None

    card_text = "\n".join(memory_cards or [])
    hit_values = _hits(card_text, em.values)
    recalled_actual = bool(hit_values)

    # ★ 与「期望」对齐 —— 负样本（should=False）时 actual=False 才是通过
    recalled_pass = recalled_actual == bool(em.should_be_recalled)

    reply_hit_values = _hits(reply or "", em.values)
    # ★ `used` 的语义是「**用了记忆**」，不是「回复里出现了这个词」。
    #   只看回复文本会把两种完全不同的事件判成一件事：
    #     · 负样本（什么都没召回）回复里出现期望值 —— 那来自 **RAG 证据或题面本身**，
    #       不是记忆 ⇒ 旧实现在此给出 `used=True`（**假阳性**，实测 `mem-006` 即如此）。
    #   ⇒ 必须有记忆卡的事实前提 `recalled_actual`，才允许谈「用没用」。
    used = recalled_actual and bool(reply_hit_values)

    forbidden_hits = _hits(reply or "", eap.forbidden_values)
    # forbidden 为空 ⇒ correct ≡ used（显式退化，已在 gold 契约中注明）
    correct = used and not forbidden_hits

    return MemoryJudgement(
        recalled_pass=recalled_pass,
        used=used,
        correct=correct,
        recalled_actual=recalled_actual,
        should_be_recalled=bool(em.should_be_recalled),
        hit_values=hit_values,
        reply_hit_values=reply_hit_values,
        forbidden_hits=forbidden_hits,
    )


def judgement_to_dict(j: MemoryJudgement) -> dict[str, Any]:
    """转成落盘 dict（供 record 归档；诊断字段一并保留以便复算）。"""
    return {
        "memory_recalled_actual": j.recalled_actual,
        "memory_recalled_pass": j.recalled_pass,
        "memory_used": j.used,
        "memory_correct": j.correct,
        "memory_should_be_recalled": j.should_be_recalled,
        "memory_hit_values": list(j.hit_values),
        "memory_reply_hit_values": list(j.reply_hit_values),
        "memory_forbidden_hits": list(j.forbidden_hits),
        "memory_correct_use": j.correct_use,
    }


# ── case validity（A 段前置条件验收，2026-10-06 Step 5）──────────────


@dataclass(frozen=True)
class ValidityResult:
    """case 前置条件的验收结果。

    `valid=True` ⇒ 本 case 的 Memory 主指标**可进分母**；
    `valid=False` ⇒ **前置条件没成立**（如 mem-006 要求两次高分、实际跑出 100/52），
      该 case 记 `case_invalid`，其 Memory 三项记 N/A（**不进分母**）——
      与「产品召回失败」严格区分。
    `valid=None` ⇒ case **未声明**前置条件（无需校验），按可进分母处理。
    """

    valid: bool | None = None
    reason: str = ""
    observed: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.observed is None:
            object.__setattr__(self, "observed", {})


def check_case_validity(
    *,
    setup: SetupConditions | None,
    grade_scores: list[dict[str, Any]] | None,
    session_scope: int = 0,
) -> ValidityResult:
    """按 `setup_conditions` 校验 A 段（写入前提）是否成立。

    Parameters
    ----------
    setup:
        case 声明的前置条件；None/空 ⇒ 返回 `valid=None`（不校验，不阻塞）。
    grade_scores:
        harness 捕获的批改得分 `[{"session": 0, "score": 52.0}, ...]`。
    session_scope:
        只校验**该会话下标**的批改（默认 0 = A 段）。跨会话语义下
        前置条件归 A 段，B 段不应有批改 ⇒ 用 0 精确圈定。

    Returns
    -------
    ValidityResult
        `valid=False` 时 `reason` 说明**哪一条**没满足（可读，便于报告归因）。
    """
    if setup is None or not setup.is_valid():
        return ValidityResult(valid=None, reason="未声明前置条件（不校验）")

    calls = [g for g in (grade_scores or []) if int(g.get("session", 0)) == session_scope]
    scores = [g.get("score") for g in calls]
    observed: dict[str, Any] = {"grade_calls": len(calls), "scores": scores}

    # —— 条件 1：批改次数下限 ——
    if setup.min_grade_calls is not None and len(calls) < setup.min_grade_calls:
        return ValidityResult(
            valid=False,
            reason=f"A 段批改次数 {len(calls)} < 期望下限 {setup.min_grade_calls}",
            observed=observed,
        )

    # —— 条件 1b：批改次数上限（负样本对照用，2026-10-07）——
    #   `min: 0` 单写是永真的（`len < 0` 不可能），所以「A 段不该有任何批改」这个
    #   意图只有配上限才**真的被验收**。mem-005 若在上限处失败 ⇒ 说明 A 段真发生了
    #   批改、Store 里确实有画像 ⇒ 此时 B 段「没召回」是**产品失败**而非无话可说，
    #   把它留在分母里会得出反方向的结论 ⇒ 必须记 case_invalid 排除。
    if setup.max_grade_calls is not None and len(calls) > setup.max_grade_calls:
        return ValidityResult(
            valid=False,
            reason=f"A 段批改次数 {len(calls)} > 期望上限 {setup.max_grade_calls}"
            "（负样本对照的「无写入」前提不成立）",
            observed=observed,
        )

    # —— 条件 2：每次得分须落入给定区间 ——
    if setup.grade_score_bands:
        bands = setup.grade_score_bands
        for i, (lo, hi) in enumerate(bands):
            if i >= len(scores):
                return ValidityResult(
                    valid=False,
                    reason=f"缺少第 {i + 1} 次批改（期望落在 [{lo},{hi}]）",
                    observed=observed,
                )
            s = scores[i]
            if s is None:
                if not setup.allow_missing_score:
                    return ValidityResult(
                        valid=False,
                        reason=f"第 {i + 1} 次批改得分未能解析（未获授权容忍缺分）",
                        observed=observed,
                    )
                continue
            if not (lo <= float(s) <= hi):
                return ValidityResult(
                    valid=False,
                    reason=f"第 {i + 1} 次批改得分 {s} 不在期望区间 [{lo},{hi}]",
                    observed=observed,
                )

    return ValidityResult(valid=True, reason="前置条件满足", observed=observed)


def validity_to_dict(v: ValidityResult) -> dict[str, Any]:
    return {"validity_valid": v.valid, "validity_reason": v.reason, "validity_observed": v.observed}
