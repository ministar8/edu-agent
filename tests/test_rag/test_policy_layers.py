"""三层策略的边界不变量（安全/披露 vs 算力预算 vs 部署开关）。

为什么需要：`TaskPolicy` 曾带 `depth / k / use_rerank` 三个**算力**字段，
`resolve_task_policy` 也接收同名参数 —— 策略对象看上去也管预算，三层概念因此互相混。
实测那三个字段全仓**没有任何读取方**（2026-11-04 删除），边界只是被冗余字段弄糊了。

本文件把边界锁成**类型事实**。反向验证：把任一算力字段加回 `TaskPolicy`、
或给 `resolve_task_policy` 加回 `depth` 参数，前三条断言立刻变红。
"""

from __future__ import annotations

import dataclasses
import inspect

from rag.retrieval.query_classifier import RetrievalDepth
from rag.retrieval.task_policy import resolve_task_policy
from schema.task_policy import TaskPolicy

COMPUTE_FIELDS = {"depth", "k", "use_rerank"}
SAFETY_FIELDS = {
    "answer_policy",
    "explanation_policy",
    "related_exam_policy",
    "allow_question_id_leak",
    "exam_resources",
    "legacy_policy",
}


def test_task_policy_has_no_compute_budget_fields() -> None:
    assert COMPUTE_FIELDS.isdisjoint(TaskPolicy.model_fields), (
        "TaskPolicy 不得携带算力预算字段；算力真源是 RetrievalDepth"
    )


def test_retrieval_depth_has_no_policy_fields() -> None:
    names = {f.name for f in dataclasses.fields(RetrievalDepth)}
    assert SAFETY_FIELDS.isdisjoint(names)


def test_resolve_task_policy_cannot_override_budget() -> None:
    params = set(inspect.signature(resolve_task_policy).parameters)
    assert COMPUTE_FIELDS.isdisjoint(params)


def test_safety_fields_depend_only_on_task_mode() -> None:
    """同一 task_mode 下，查询文本只影响 preferred_layers，不得改变安全字段。"""
    a = resolve_task_policy("给我一道 BST 练习题", task_mode="practice")
    b = resolve_task_policy("完全不同的题面：用 C 写快速排序", task_mode="practice")
    for field in SAFETY_FIELDS:
        assert getattr(a, field) == getattr(b, field), field
