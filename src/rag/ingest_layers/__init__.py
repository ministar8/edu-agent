"""各入库层的**生产构建逻辑**（脚本与检索门禁的共同真源）。

每层暴露：
- ``build(...)`` → 纯函数，返回 chunk（不落库、不写 links）—— 检索门禁据此走**生产入库路径**；
- ``ingest(...)`` → ``build()`` + 落库 + 写 links（``scripts/ingest_*.py`` 调）。

``build_all()`` 按生产顺序（basic → advanced → exams 年 → exam_practice → code → 路径）
汇总所有集合的 chunk，返回 ``{collection: [Document, ...]}``。
"""

from __future__ import annotations

from langchain_core.documents import Document

from rag.ingest_layers import _shared, advanced, basic, code, exam_practice, exams, learning_paths

__all__ = [
    "_shared",
    "advanced",
    "basic",
    "code",
    "exam_practice",
    "exams",
    "learning_paths",
    "build_all",
]


def build_all(kp_ids: set[str] | None = None) -> dict[str, list[Document]]:
    """按生产入库逻辑构建**所有集合**的 chunk（纯函数：不落库、不写 links）。

    顺序与生产脚本一致：basic → advanced → exams 年 → exam_practice → code → learning_paths。
    """
    if kp_ids is None:
        kp_ids = _shared.load_kp_ids()
    by_col: dict[str, list[Document]] = {}

    def _merge(collection: str, chunks: list[Document]) -> None:
        if chunks:
            by_col.setdefault(collection, []).extend(chunks)

    basic_cols, _, _ = basic.build(kp_ids)
    for collection, chunks in basic_cols.items():
        _merge(collection, chunks)

    adv_cols, _, _ = advanced.build(kp_ids)
    for collection, chunks in adv_cols.items():
        _merge(collection, chunks)

    exam_chunks, _, _ = exams.build_all(kp_ids)
    _merge("exams", exam_chunks)
    practice_chunks, _, _ = exam_practice.build(kp_ids)
    _merge("exams", practice_chunks)

    for subject, collection in code.SUBJECT_TO_COLLECTION.items():
        chunks, _, _ = code.build(subject, kp_ids)
        _merge(collection, chunks)

    lp_chunks, _, _ = learning_paths.build()
    _merge(learning_paths.COLLECTION, lp_chunks)
    return by_col
