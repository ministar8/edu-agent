"""向量数据库管理器（门面）。

`VectorStoreManager` 由基类（共享状态 + HNSW/get_store/失败记录）与两个 mixin（查询 / 入库）
组合而成，公开 API 与拆分前一致。子模块见 `_vectorstore_base` / `_vectorstore_query` / `_vectorstore_ingest`。
"""

from __future__ import annotations

import logging
import time

from rag.common._vectorstore_base import (
    _HNSW_COLLECTION_METADATA,
    _LEGACY_HNSW_KEYS,
    _READINESS_PROBE_QUERY,
)
from rag.common._vectorstore_ingest import _IngestMixin
from rag.common._vectorstore_query import _QueryMixin

logger = logging.getLogger(__name__)

# ── `wait_until_ready` 说明（检测器，非修复器）─────────────────────────────
# 现象：`add_documents` 返回后查询该集合会抛
#     Error executing plan: Internal error: Error creating hnsw segment reader:
#     Nothing found on disk
# **间歇性**：同一份代码连续运行，每次命中的集合不同（实测在 `computer_organization` /
# `operating_system` 之间随机），命中后该集合**整轮不可查询**（检索结果全错，但不报错）。
#
# 实测过的三种恢复手段（针对已损坏的集合）：
#     丢弃 `_stores` 缓存句柄后重试        无效
#     重开 `chromadb.PersistentClient`     无效
#     `delete_collection` 后重新入库       **有效**
# 也就是说：集合的向量确实写进去了（`count()` 正确、HNSW 元数据 `status=ok`），
# 但 HNSW 段文件从未落盘；进程内没有任何办法把它"等"出来。**只有重建索引能修。**
# 重试只覆盖"真的只是慢"那一小部分情况。


class VectorStoreManager(_QueryMixin, _IngestMixin):
    """向量数据库管理器"""

    def list_collections(self) -> list[str]:
        """列出所有集合"""
        return [col.name for col in self.client.list_collections()]

    def get_collection_info(self, collection_name: str) -> dict:
        """获取集合信息（含 HNSW 索引参数）"""
        try:
            collection = self.client.get_collection(collection_name)
            meta = collection.metadata or {}
            count = collection.count()
            legacy_keys = [key for key in _LEGACY_HNSW_KEYS if key in meta]
            missing_keys = [key for key in _HNSW_COLLECTION_METADATA if key not in meta]
            mismatched_keys = [
                key
                for key, val in _HNSW_COLLECTION_METADATA.items()
                if key in meta and str(meta.get(key)) != str(val)
            ]
            if collection_name in self._hnsw_degraded:
                status = "degraded"
            elif count > 0 and (missing_keys or legacy_keys or mismatched_keys):
                status = "needs_rebuild"
            elif missing_keys or legacy_keys or mismatched_keys:
                status = "needs_init"
            else:
                status = "ok"
            return {
                "name": collection_name,
                "count": count,
                "client_mode": self.client_mode,
                "hnsw_M": meta.get("hnsw:M", "N/A"),
                "hnsw_search_ef": meta.get("hnsw:search_ef", "N/A"),
                "hnsw_construction_ef": meta.get("hnsw:construction_ef", "N/A"),
                "hnsw_space": meta.get("hnsw:space", "N/A"),
                "hnsw_status": status,
                "hnsw_missing_keys": missing_keys,
                "hnsw_legacy_keys": legacy_keys,
                "hnsw_mismatched_keys": mismatched_keys,
                "hnsw_error": self._hnsw_degraded.get(collection_name, ""),
            }
        except Exception:
            return {"name": collection_name, "count": 0, "client_mode": self.client_mode}

    def wait_until_ready(
        self,
        collection_name: str,
        *,
        retries: int = 8,
        delay: float = 0.5,
    ) -> int:
        """等待集合的 HNSW 索引可查询，返回成功前经历的失败次数。

        **这是"检测器"，不是"修复器"** —— 只能把"静默返回错误检索结果"变成"入库期显式失败"。
        完整现象（间歇性 `Nothing found on disk`）与实测恢复手段见本文件顶部
        `wait_until_ready` 说明注释。

        Args:
            collection_name: 集合名。
            retries: 最大尝试次数（含首次）。
            delay: 两次尝试之间的等待秒数。

        Returns:
            成功前经历的失败次数（0 表示首次即通过）。

        Raises:
            RuntimeError: 重试耗尽后仍不可查询。信息里含底层原因与补救命令。
        """
        last_error = ""
        for attempt in range(retries):
            try:
                self.similarity_search_with_score(collection_name, _READINESS_PROBE_QUERY, k=1)
            except Exception as e:  # noqa: BLE001 — 需要兜住 Chroma 各类底层异常
                last_error = f"{type(e).__name__}: {e}"
                # 丢弃缓存句柄：对"慢"的情况有帮助；对"段文件未落盘"无效（实测）
                self._stores.pop(collection_name, None)
                if attempt < retries - 1:
                    time.sleep(delay)
                continue

            if attempt:
                logger.info(
                    "Collection '%s' became queryable after %d retries", collection_name, attempt
                )
            return attempt

        raise RuntimeError(
            f"集合 '{collection_name}' 在 {retries} 次重试后索引仍不可查询：{last_error}。"
            f"该集合的 HNSW 段文件未落盘，进程内无法恢复；"
            f"请重建：ingest_category({collection_name!r}, rebuild=True)"
        )


_vector_store_manager: VectorStoreManager | None = None


def get_vector_store_manager() -> VectorStoreManager:
    """懒加载向量数据库管理器（单例）"""
    global _vector_store_manager
    if _vector_store_manager is None:
        _vector_store_manager = VectorStoreManager()
    return _vector_store_manager
