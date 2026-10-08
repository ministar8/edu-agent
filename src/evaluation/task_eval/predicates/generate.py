"""Generate 任务的判据（EFFECT_PLAN.md §3.1 冻结五项 + 两个机械替身）。

两类判据名不能混（§4.1：证据不是等价定义就不沿用原名）：
- 冻结五项 `gen_structure / gen_answerability / gen_coverage / gen_correctness /
  gen_difficulty`：其中 `gen_correctness` / `gen_answerability` 要**外部 gold**
  （盲标规程 P-1），gold 未标注 ⇒ 如实返回 `missing_premise` —— 那是诚实状态，
  不是缺陷，**不得**用机械替身顶名。
- 机械替身 `gen_answer_key_validity` / `gen_analysis_agreement`：**必要非充分**，
  永不进门槛行顶替冻结名（registry 侧以 `optional=True` 标注）。
"""

from __future__ import annotations

import re
from typing import Any

from evaluation.task_eval import metrics
from evaluation.task_eval.predicates.common import Verdict
from evaluation.task_eval.predicates.registry import Predicate, register

# 真实键名来自 metrics.structure_completeness 的返回（stem/options_or_task/answer/explanation）
_GEN_KEYS = ("stem", "options_or_task", "answer", "explanation")


def _structure(rec: dict) -> Verdict:
    """§3.1 completeness_pass：四件套**逐一非空**，不是「整条能解析」。"""
    parsed = metrics.structure_completeness(str(rec.get("reply") or ""))
    return "fail" if [k for k in _GEN_KEYS if not parsed.get(k)] else "pass"


def _answerability(rec: dict) -> Verdict:
    """§3.1 冻结项「答案可判定」，判定主体是**人工**（盲标 P-1 未做）。

    无 gold（连出处都没有）⇒ `missing_premise`；gold 在册也仍需人工标注结论，
    而标注通道尚未建立（P-1 未做）⇒ 同样 `missing_premise`。名字保留、状态诚实。
    """
    gold = rec.get("gold") or {}
    if not gold.get("gold_answer") or not (gold.get("gold_source_ref") or {}).get("gold_answer"):
        return "missing_premise"
    return "missing_premise"  # P-1 人工标注结论不存在：无可读判定，不冒充可测


def _coverage(rec: dict) -> Verdict:
    """§3.1 冻结项「知识点覆盖」：包一层 `metrics.kp_coverage`（唯一公式）。

    `expected_kp` 为空 ⇒ `not_applicable`（族级零覆盖披露，§1.6）。
    ★ checkpoint 5 裁定 A：record 缺 `top_items` 键（老归档检索探针未落盘，
      phase1_baseline_v2 15/15 实测）⇒ 「证据不存在」= `missing_premise`，
      **不得**把空 retrieved 集喂进 `kp_coverage` 读成 fail（规则①禁止
      「没证据 = 不合格」）。键存在但列表为空 ⇒ 仍是 `fail`
      （「查了且没覆盖」≠「没证据」）。
    """
    expected = (rec.get("gold") or {}).get("expected_kp") or []
    if not expected:
        return "not_applicable"
    if "top_items" not in rec or rec.get("top_items") is None:
        return "missing_premise"
    retrieved = [
        kp
        for item in (rec.get("top_items") or [])
        for kp in ((item.get("kp") if isinstance(item, dict) else None) or [])
    ]
    v = metrics.kp_coverage(expected, retrieved)
    return "missing_premise" if v is None else ("pass" if v else "fail")


def _difficulty(rec: dict) -> Verdict:
    """§3.1 冻结项「难度匹配」：`metrics.difficulty_match(expected, actual)`。

    两条前置（§1.6）：`gold.expected_difficulty` 缺失或 `difficulty_of()` 抽不出来
    ⇒ `missing_premise` —— 解析器的失败不能记成产品的失败。
    """
    gold = rec.get("gold") or {}
    if not gold.get("expected_difficulty"):
        return "missing_premise"
    actual = metrics.difficulty_of(str(rec.get("reply") or ""))
    if actual is None:
        return "missing_premise"
    v = metrics.difficulty_match(gold["expected_difficulty"], actual)
    return "missing_premise" if v is None else ("pass" if v else "fail")


# 多小问分节痕迹（（1）（2）… 式编号小问）：checkpoint 3 裁定的「混合卷」识别信号之一。
# 形状与 `_STRUCTURE_OPTIONS` 的（n）分支同源，但语义是**排除门**，不是结构要素。
_MULTI_PART_MARK = re.compile(r"(?:^|\n)\s*[（(]\s*[1-9]\s*[）)]")


def _is_pure_mcq(reply: str) -> bool:
    """可靠识别：恰有一个 A–D 选项块、恰有一条答案行、且没有多小问分节痕迹。

    依据是 Task 3 标定的实测：15 条真实产物里 14 条是「综合应用+选择+填空」混合卷，
    答案键/解析结论/难度行在多小问之间互相污染（`answer_keys_of` 10/15 误读、
    十六进制 41C8 / 单位 4KB / Baud / SYN-ACK 全被当选项字母）。
    ★ 代价要如实接受：加上这道门之后，机械判据的适用域从 15 条收缩到「真纯选择题」那几条
      （标定表里只有 gen-002/004/008/011/013/014 等带完整 A-D 选项块的才算，
       且仍需人工抽查确认不是混合卷）——收缩是**诚实**，不是退化。
    """
    text = str(reply or "")
    if not text:
        return False
    # metrics 的抽取正则仍是唯一真源：这里只复用它做**形状**判定，不另写第二套抽取。
    if metrics._OPTION_LINE.findall(text) != ["A", "B", "C", "D"]:
        return False  # 恰一个完整 A–D 选项块（缺项/重复/乱序都不可靠）
    if len(metrics._ANSWER_LINE.findall(text)) != 1:
        return False  # 恰一条答案行
    return not _MULTI_PART_MARK.search(text)


def _correctness(rec: dict) -> Verdict:
    """§3.1 冻结原文是「gold 判定正确」⇒ 需要外部 gold，且必须带出处（盲标规程）。"""
    gold = rec.get("gold") or {}
    if not gold.get("gold_answer") or not (gold.get("gold_source_ref") or {}).get("gold_answer"):
        return "missing_premise"
    reply = str(rec.get("reply") or "")
    if not _is_pure_mcq(reply):
        return "missing_premise"  # checkpoint 3：混合卷答案键不可靠，测不到 ≠ 不合格
    keys = metrics.answer_keys_of(reply)
    return (
        "pass" if len(keys) == 1 and keys[0] == str(gold["gold_answer"]).strip().upper() else "fail"
    )


def _answer_key_validity(rec: dict) -> Verdict:
    """原 `gen_answerability` 的**必要非充分**机械替身。它不证明这题可被作答判定。

    契约是三条，缺一条就不算覆盖（spec §6 那行的「two correct options」是第 2 条）：
      ① 答案键可解析  ② 键数**恰好为 1**  ③ 该键 ∈ 选项集
    """
    reply = str(rec.get("reply") or "")
    if not _is_pure_mcq(reply):
        return "missing_premise"  # checkpoint 3：无可靠选项集 = 没资格谈唯一性，测不到 ≠ 失败
    opts = metrics.option_letters(reply)
    if not opts:
        return "missing_premise"  # 连选项集都读不出来 = 没资格谈唯一性（纯选择题门下不触发）
    keys = metrics.answer_keys_of(reply)
    if len(keys) != 1:
        return "fail"  # 0 个键（没给答案）与多键（A、B 都算对）在这里都是失败
    return "pass" if keys[0] in opts else "fail"


def _analysis_agreement(rec: dict) -> Verdict:
    """原 `gen_correctness` 的**必要非充分**机械替身（#33 产品规则的评测化）。

    ★ 它不证明答案对不对 —— #36 手验 5 道里 2 道客观错、1 道满分漏检就是这件事的证据。
    """
    reply = str(rec.get("reply") or "")
    if not _is_pure_mcq(reply):
        return "missing_premise"  # checkpoint 3：混合卷的解析结论被多小问污染，测不到 ≠ 失败
    keys, cited = metrics.answer_keys_of(reply), metrics.analysis_key_of(reply)
    if cited is None or len(keys) != 1:
        return "missing_premise"  # 点不出可比的「键 ↔ 解析结论」= 测不到，不是不合格
    return "pass" if keys[0] == cited else "fail"


def _required_always(_rec: Any) -> bool:
    return True


def _required_when_query_mentions_difficulty(rec: Any) -> bool:
    """query 未指定难度 ⇒ 本项不 required（`optional=True` 一并披露族级零覆盖）。"""
    return bool(re.search(r"难度|难易", str((rec or {}).get("query") or "")))


register(
    Predicate(
        name="gen_structure",
        task="generate",
        tier=1,
        contract_ref="EFFECT_PLAN.md §3.1 结构完整",
        contract_inputs=(
            "reply#stem",
            "reply#options_or_task",
            "reply#answer",
            "reply#explanation",
        ),
        required_when=_required_always,
        fn=_structure,
        falsifier="omit_reply_part",
    )
)
register(
    Predicate(
        name="gen_answerability",
        task="generate",
        tier=1,
        contract_ref="EFFECT_PLAN.md §3.1 答案可判定",
        contract_inputs=("gold.gold_answer", "gold.gold_source_ref.gold_answer"),
        required_when=_required_always,
        fn=_answerability,
        falsifier="omit_reply_part",
    )
)
register(
    Predicate(
        name="gen_coverage",
        task="generate",
        tier=1,
        contract_ref="EFFECT_PLAN.md §3.1 知识点覆盖",
        # ★ 归档真实字段名是 `top_items[].kp`（runner.py 落盘即此名，无 knowledge_points 键）
        contract_inputs=("top_items[].kp", "gold.expected_kp"),
        required_when=_required_always,
        fn=_coverage,
        falsifier="drop_path:top_items[].kp",
    )
)
register(
    Predicate(
        name="gen_correctness",
        task="generate",
        tier=1,
        contract_ref="EFFECT_PLAN.md §3.1 内容正确",
        # ★ checkpoint 5 裁定（supersede checkpoint 3 的「contract_inputs 不变」字面）：
        #   纯选择守卫让选项块成为**真实输入**（omit options ⇒ 经 `_is_pure_mcq`
        #   pass→missing_premise），contract_inputs 必须声明现实依赖，包括经守卫引入的间接依赖。
        contract_inputs=(
            "reply#answer",
            "gold.gold_answer",
            "gold.gold_source_ref.gold_answer",
            "reply#options_or_task",
        ),
        required_when=_required_always,
        fn=_correctness,
        falsifier="dual_answer",
    )
)
register(
    Predicate(
        name="gen_difficulty",
        task="generate",
        tier=1,
        contract_ref="EFFECT_PLAN.md §3.1 难度匹配",
        contract_inputs=("gold.expected_difficulty", "reply#difficulty"),
        required_when=_required_when_query_mentions_difficulty,
        fn=_difficulty,
        falsifier="drop_path:gold.expected_difficulty",
        optional=True,  # query 未指定难度 ⇒ 不毒化（§1.6 族级零覆盖披露）
    )
)
register(
    Predicate(
        name="gen_answer_key_validity",
        task="generate",
        tier=2,
        contract_ref="EFFECT_PLAN.md §3.1 答案可判定（机械替身，必要非充分）",
        contract_inputs=("reply#answer", "reply#options_or_task"),
        required_when=_required_always,
        fn=_answer_key_validity,
        falsifier="dual_answer",
        optional=True,  # 机械替身：永不顶替 gen_answerability 进门槛行
    )
)
register(
    Predicate(
        name="gen_analysis_agreement",
        task="generate",
        tier=2,
        contract_ref="EFFECT_PLAN.md §3.1 内容正确（机械替身，必要非充分）",
        # ★ checkpoint 5 裁定（同 gen_correctness）：守卫引入的间接依赖必须补实为真实契约输入
        contract_inputs=("reply#answer", "reply#explanation", "reply#options_or_task"),
        required_when=_required_always,
        fn=_analysis_agreement,
        falsifier="flip_conclusion",
        optional=True,  # 机械替身：永不顶替 gen_correctness 进门槛行
    )
)
