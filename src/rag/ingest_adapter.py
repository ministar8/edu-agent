"""离线入库 → 在线检索层的薄适配层。

把 `ingest` 对 `rag.retrieval.*` 的直接依赖收敛到本模块，
使离线入库子系统与检索策略层解耦。`retrieval/` 内部接口若变更，
仅需在此处调整，不改 `ingest.py`。

本模块是离线入库与在线检索之间唯一的契约入口：
- `aretrieve_evidence_raw()`：裸检索（供离线验收脚本用）
- `clear_semantic_cache()`：全量重建时清空语义缓存，避免旧知识残留
- `run_warmup_smoke()`：入库后跑检索冒烟，判定索引是否可查询
"""

from __future__ import annotations

from rag.retrieval.retriever import aretrieve_evidence_raw, warmup_query_cache
from rag.retrieval.semantic_cache import get_semantic_cache

__all__ = ["aretrieve_evidence_raw", "clear_semantic_cache", "run_warmup_smoke"]


def clear_semantic_cache() -> None:
    """全量重建时清空语义缓存，避免旧知识残留导致跨版本缓存命中。"""
    get_semantic_cache().clear()


def run_warmup_smoke(quiet: bool = True) -> dict:
    """入库后跑检索冒烟，返回 {total, succeeded, failed, elapsed_ms}。"""
    return warmup_query_cache(quiet=quiet)
