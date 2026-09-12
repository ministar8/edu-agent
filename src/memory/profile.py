"""学生画像读写：Store 上的语义记忆封装。"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.store.base import BaseStore

from memory.namespaces import PROFILE_DOC_KEY, student_profile_ns
from memory.schemas import SCHEMA_VERSION, StudentProfile

logger = logging.getLogger(__name__)


def _coerce_profile(raw: Any) -> StudentProfile:
    """把 Store 里的 dict 收成 StudentProfile；版本不识别时回退默认字段。"""
    if not raw:
        return StudentProfile()
    if isinstance(raw, StudentProfile):
        return raw
    data = dict(raw)
    version = data.get("schema_version")
    if version is not None and int(version) != SCHEMA_VERSION:
        logger.warning(
            "StudentProfile schema_version=%s 与当前 %s 不一致，按兼容模式读取",
            version,
            SCHEMA_VERSION,
        )
        data["schema_version"] = SCHEMA_VERSION
    try:
        return StudentProfile.model_validate(data)
    except Exception:
        logger.warning("StudentProfile 文档损坏，忽略并使用空画像", exc_info=True)
        return StudentProfile()


async def aget_profile(store: BaseStore, user_id: int | str) -> StudentProfile:
    """读取画像；不存在时返回空画像（不抛错）。"""
    item = await store.aget(student_profile_ns(user_id), PROFILE_DOC_KEY)
    if item is None:
        return StudentProfile()
    return _coerce_profile(item.value)


async def aupsert_profile(
    store: BaseStore,
    user_id: int | str,
    **fields: Any,
) -> StudentProfile:
    """合并更新画像并写回 Store；自动盖 schema_version 与 updated_at。

    fields 仅接受 StudentProfile 已有字段（非法键由 Pydantic 拒绝）。
    """
    current = await aget_profile(store, user_id)
    updated = current.with_updates(**fields)
    await store.aput(student_profile_ns(user_id), PROFILE_DOC_KEY, updated.model_dump())
    return updated
