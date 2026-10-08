"""判据注册表：每个指标只允许一处定义（EVIDENCE_CHAIN.md §1.6）。

★ registry **不提供** `composite_name()` 之类的「复合指标叫什么」查询：复合名由调用方
  按任务自己传（`report.py` 里就是 `common.composite(...)`），多一个查询函数就多一处
  可能漂移的间接层。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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


_BY_NAME: dict[str, Predicate] = {}
_BY_TASK: dict[str, list[Predicate]] = {}


def register(pred: Predicate) -> None:
    if pred.name in _BY_NAME:
        raise ValueError(f"判据重复注册：{pred.name}（一个指标只允许一处定义）")
    _BY_NAME[pred.name] = pred
    _BY_TASK.setdefault(pred.task, []).append(pred)


def get(name: str) -> Predicate:
    return _BY_NAME[name]


def for_task(task: str) -> list[Predicate]:
    return _BY_TASK.get(task, [])
