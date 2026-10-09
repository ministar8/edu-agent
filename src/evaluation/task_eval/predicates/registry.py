"""判据注册表：每个指标只允许一处定义（EVIDENCE_CHAIN.md §1.6）。

★ registry **不提供** `composite_name()` 之类的「复合指标叫什么」查询：复合名由调用方
  按任务自己传（`report.py` 里就是 `common.composite(...)`），多一个查询函数就多一处
  可能漂移的间接层。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from evaluation.task_eval import claims as cl
from evaluation.task_eval.predicates.common import Verdict


@dataclass(frozen=True)
class Predicate:
    name: str
    task: str
    tier: int
    contract_ref: str
    contract_inputs: tuple[str, ...]
    required_when: Callable[[Any], bool]
    fn: Callable[[Any], Verdict]
    falsifier: str
    optional: bool = False
    # ★ tier 不许裸写（Task 7 Step 4b，与 ledger 行侧的 `LITERAL_TIER_REASONS` 同一道锁）：
    #   每个锚点都要能在 `claims.TIER_ANCHORS`（唯一一份白名单）里查到实名。
    #   `tier == 0` 同样要带 —— 白拿的 0 和手滑的 2 是同一种病。
    #   两个 optional 机械替身用债标记 `TIER-DEBT-task3`（登记待偿，不是「已证明为 tier 2」）。
    tier_reason: tuple[str, ...] = ()


_BY_NAME: dict[str, Predicate] = {}
_BY_TASK: dict[str, list[Predicate]] = {}


def register(pred: Predicate) -> None:
    if pred.name in _BY_NAME:
        raise ValueError(f"判据重复注册：{pred.name}（一个指标只允许一处定义）")
    if not pred.tier_reason:
        raise ValueError(
            f"判据 {pred.name}: tier={pred.tier} 必须带 tier_reason"
            f"（白名单 {sorted(cl.TIER_ANCHORS)}）"
        )
    unknown = sorted(a for a in pred.tier_reason if a not in cl.TIER_ANCHORS)
    if unknown:
        raise ValueError(f"判据 {pred.name}: tier_reason 锚点 {unknown} 不在白名单")
    _BY_NAME[pred.name] = pred
    _BY_TASK.setdefault(pred.task, []).append(pred)


def get(name: str) -> Predicate:
    return _BY_NAME[name]


def all_preds() -> list[Predicate]:
    """全部已注册判据（**按注册顺序**，只读快照）。供 V0 的 7f/7g 逐条遍历。"""
    return list(_BY_NAME.values())


def for_task(task: str) -> list[Predicate]:
    """qa / grade 走 metrics 路径 ⇒ 无判据是**设计**，不是缺字段。
    写成显式分支而不是 `.get(task, [])`：V0 的 AST 禁令对整个包零豁免（§8①）。"""
    return list(_BY_TASK[task]) if task in _BY_TASK else []
