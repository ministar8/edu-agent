"""R1-A 机械敏感性取证：在 **record 层**弄坏，看判据是否恰好变红。

★ 只动 record，不动 `src/` 产品代码。本模块证明的是「判据吃到了契约点名的输入」，
  **不是**「产品行为正确」—— 语义那一跳由 R1-B（人工对 §3.1 原文签署）负责。
★ 被破坏的是哪个契约输入，由 **mutation 声明表**给出（`declared_mutations()`），
  不从两条 record 的 diff 反猜。原设计用 diff 猜：`stem/options/answer/explanation` 都在
  `reply` 文本内部，diff 只能看到顶层 `reply` 变了 ⇒ `covered == contract_inputs` 必然失败。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from evaluation.task_eval import metrics
from evaluation.task_eval.predicates.common import drop_path
from evaluation.task_eval.predicates.registry import Predicate


@dataclass(frozen=True)
class FalsifyResult:
    """单次取证的行：哪个判据、被声明的哪个输入、基线、是否翻红、是否牵连、是否炸。"""

    predicate: str
    input: str  # ★ 来自 mutation 声明，不是 diff 猜的
    baseline: str  # 基线 verdict —— 「基线本就该 pass」这条前提靠它自检
    flipped: bool  # 基线为 pass 且弄坏后不为 pass
    collateral: bool  # 其余判据的 verdict 被牵连改变
    raised: bool  # 判据抛异常 —— 判据本身不健壮


# 同一个契约输入常常需要**多种**破坏才能真正覆盖它的语义：`reply#answer` 既可能整段缺席，
# 也可能出现「A、B 都算对」。所以每个输入返回 op 列表，而不是「一输入一 mutation」。
#
# ★★ op 按**判据语义**收窄（checkpoint 5 裁定，修矛盾 1）：额外 op 只给真正读那份信息的判据
#   —— `dual_answer`/`flip_conclusion` 保留全部 label，`_structure`（按 label 存在性判 pass）
#   对它们天然不翻转；把这两种 op 塞给 `gen_structure` 是设计错误，会让 5b 的
#   `all(r.flipped)` 永远红。规则（键 = 判据名，值 = {reply 片段名: 该片段允许的 op}）：
#     - 读 label 存在性的判据（`gen_structure`）⇒ 只有 `omit_reply_part`；
#     - 读答案键的判据（`gen_answer_key_validity` / `gen_analysis_agreement` / `gen_correctness`）
#       ⇒ `omit_reply_part` + `dual_answer`（answer）；
#     - 读解析结论的（`gen_analysis_agreement`）⇒ 额外 `flip_conclusion`（explanation）。
#   覆盖检查（5a/5e）比的是**输入名**，op 收窄不影响覆盖完整性。
_REPLY_OPS_BY_SEMANTICS: dict[str, dict[str, tuple[str, ...]]] = {
    "gen_structure": {
        "stem": ("omit_reply_part",),
        "options_or_task": ("omit_reply_part",),
        "answer": ("omit_reply_part",),
        "explanation": ("omit_reply_part",),
    },
    "gen_correctness": {"answer": ("omit_reply_part", "dual_answer")},
    "gen_answer_key_validity": {"answer": ("omit_reply_part", "dual_answer")},
    "gen_analysis_agreement": {
        "answer": ("omit_reply_part", "dual_answer"),
        "explanation": ("omit_reply_part", "flip_conclusion"),
    },
}
# 未在语义表里点名的 reply 片段（如 `reply#difficulty`、gen_answer_key_validity 的选项块）
# 默认只做整段缺席（omit）—— 没有已证实的额外语义就不配额外 op。
_DEFAULT_REPLY_OPS: tuple[str, ...] = ("omit_reply_part",)


def declared_mutations(pred: Predicate) -> list[dict[str, str]]:
    """把 `contract_inputs` 展开成声明表（破坏动作与被破坏的输入**同源声明**，不靠 diff 猜）。

    每个契约输入至少一条；缺任一 ⇒ `coverage()` 列成缺口 —— 「形式覆盖但语义没覆盖」的拦网。
    ★ 条数会**多于** `len(contract_inputs)`，而 `coverage()` 比的是输入名集合，不受影响。
    """
    out: list[dict[str, str]] = []
    per_input = _REPLY_OPS_BY_SEMANTICS.get(pred.name, {})
    for name in pred.contract_inputs:
        if name.startswith("reply#"):
            ops = per_input.get(name.split("#", 1)[1], _DEFAULT_REPLY_OPS)
        else:
            ops = ("drop_path",)
        out.extend({"predicate": pred.name, "input": name, "op": op} for op in ops)
    return out


def apply(*, mutation: dict[str, str], record: dict[str, Any]) -> dict[str, Any]:
    """按声明破坏 record。**不遍历、不猜。**分段知识只留在 `metrics`（结构真源），此处只调用。"""
    broken = copy.deepcopy(record)
    name, op = mutation["input"], mutation["op"]
    tail = name.split("#", 1)[1] if name.startswith("reply#") else name
    if op == "omit_reply_part":
        broken["reply"] = metrics.strip_reply_part(str(record.get("reply") or ""), tail)
    elif op == "dual_answer":
        broken["reply"] = metrics.rewrite_reply_part(
            str(record.get("reply") or ""), "answer", "标准答案：A、B"
        )
    elif op == "flip_conclusion":
        broken["reply"] = metrics.rewrite_reply_part(
            str(record.get("reply") or ""),
            "explanation",
            "解析：8 行分 2 路，故组号需 2 位，因此选 A。",
        )
    elif op == "drop_path":
        drop_path(broken, name)
    else:
        raise ValueError(f"未知 mutation op：{op}")
    return broken


def evaluate(
    pred: Predicate,
    base_rec: dict[str, Any],
    broken_rec: dict[str, Any],
    *,
    mutation_input: str,
    siblings: dict[str, tuple[Predicate, dict[str, Any]]] | None = None,
) -> FalsifyResult:
    """跑基线与弄坏后的 verdict；兄弟判据在弄坏后的 verdict 变化记为 collateral。"""
    base_v = _safe(pred, base_rec)
    broken_v = _safe(pred, broken_rec)
    collateral = False
    for _name, (other, rec) in (siblings or {}).items():
        # ★ 实测收窄（原定义不可满足）：`reply#answer` 同时是 gen_answer_key_validity /
        #   gen_analysis_agreement / gen_correctness 的契约输入，弄坏它必然牵连兄弟判据 ——
        #   原样实现会让 5c 永远红。collateral 只统计**不消费该地址**的判据被改动的情形。
        if other.name == pred.name or mutation_input in other.contract_inputs:
            continue
        if _safe(other, rec) != _safe(other, broken_rec):
            collateral = True
    return FalsifyResult(
        predicate=pred.name,
        input=mutation_input,
        baseline=base_v,
        flipped=(base_v == "pass" and broken_v != "pass"),
        collateral=collateral,
        raised=("raised" in (base_v, broken_v)),
    )


def _safe(pred: Predicate, rec: dict[str, Any]) -> str:
    """判据抛异常 ⇒ 记 `raised`（判据健壮性本身就是被测量，不炸掉整个取证）。"""
    try:
        return str(pred.fn(rec))
    except Exception:
        return "raised"


def coverage(preds: list[Predicate], covered: dict[str, set[str]]) -> dict[str, tuple[str, ...]]:
    """返回 {判据名: 未被任何 mutation 覆盖的 contract_input}。非空 ⇒ R1-A 不过。"""
    return {
        p.name: tuple(i for i in p.contract_inputs if i not in covered.get(p.name, set()))
        for p in preds
        if any(i not in covered.get(p.name, set()) for i in p.contract_inputs)
    }
