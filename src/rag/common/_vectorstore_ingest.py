"""VectorStoreManager 的入库/写路径（从 vectorstore.py 拆出，行为等价）。"""

from __future__ import annotations

import logging
import time

from langchain_core.documents import Document

from rag.common._metadata_spec import sanitize_for_chroma
from rag.common._vectorstore_base import _content_hash, _VectorStoreBase
from rag.common.metrics import metrics

logger = logging.getLogger(__name__)


class _IngestMixin(_VectorStoreBase):
    """入库：内容去重、写入、删除、写指标。"""

    def _get_existing_hashes(self, collection_name: str) -> set[str]:
        """获取集合中已有内容的哈希集合，用于去重（带 5min TTL 缓存）"""
        now = time.monotonic()
        cache_entry = self._hash_cache.get(collection_name)
        if cache_entry:
            hashes, ts = cache_entry
            if now - ts < 300:  # 5 min TTL
                return hashes
        try:
            collection = self.client.get_collection(collection_name)
            if collection.count() == 0:
                hashes: set[str] = set()
            else:
                result = collection.get(include=["metadatas"])
                hashes = set()
                for meta in result.get("metadatas", []) or []:
                    h = meta.get("content_hash") if meta else None
                    if h:
                        hashes.add(h)
        except Exception:
            hashes = set()
        self._hash_cache[collection_name] = (hashes, now)
        return hashes

    def _dedup_by_content_hash(
        self, documents: list[Document], collection_name: str
    ) -> tuple[list[Document], int]:
        """按内容哈希跳过集合中已存在的文档；返回 (去重后文档, 跳过条数)。"""
        existing_hashes = self._get_existing_hashes(collection_name)
        unique_docs: list[Document] = []
        skipped = 0
        for doc in documents:
            content_hash = _content_hash(doc.page_content)
            if content_hash in existing_hashes:
                skipped += 1
                continue
            doc.metadata["content_hash"] = content_hash
            unique_docs.append(doc)

        if skipped > 0:
            logger.info(
                "Dedup: skipped %d/%d documents in collection '%s'",
                skipped,
                len(documents),
                collection_name,
            )
        return unique_docs, skipped

    def _write_documents(self, documents: list[Document], collection_name: str) -> list[str]:
        """写入 Chroma；PersistentClient 非线程安全，写必须独占锁防止 HNSW 损坏。"""
        store = self.get_store(collection_name)
        if self.client_mode == "persistent":
            with self._rw_lock.write_lock():
                return store.add_documents(documents)
        return store.add_documents(documents)

    def _index_and_emit(
        self,
        documents: list[Document],
        collection_name: str,
        *,
        started: float,
        input_docs: int,
        dedup_skipped: int,
    ) -> list[str]:
        """写入集合并写指标；失败时写 error 指标后**原样抛出**（不吞异常）。"""
        try:
            ids = self._write_documents(documents, collection_name)
        except Exception as e:
            metrics.emit(
                event="index_documents",
                stage="vectorstore",
                status="error",
                duration_ms=round((time.perf_counter() - started) * 1000, 3),
                tags={"collection": collection_name},
                values={
                    "input_docs": input_docs,
                    "dedup_skipped": dedup_skipped,
                    "ready_docs": len(documents),
                    "error_type": e.__class__.__name__,
                },
            )
            raise
        metrics.emit(
            event="index_documents",
            stage="vectorstore",
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            tags={"collection": collection_name},
            values={
                "input_docs": input_docs,
                "dedup_skipped": dedup_skipped,
                "ready_docs": len(documents),
                "indexed_docs": len(ids),
                "index_success_rate": round(len(ids) / len(documents), 6) if documents else 0.0,
            },
        )
        return ids

    def add_documents(
        self,
        documents: list[Document],
        collection_name: str = "data_structure",
        dedup: bool = True,
    ) -> list[str]:
        """添加文档到向量存储，支持内容去重

        Args:
            documents: 待入库的文档列表
            collection_name: 集合名称
            dedup: 是否启用去重（基于内容哈希），默认开启
        """
        start = time.perf_counter()
        original_count = len(documents)
        if not documents:
            metrics.emit(
                event="index_documents",
                stage="vectorstore",
                duration_ms=0.0,
                tags={"collection": collection_name},
                values={"input_docs": 0, "indexed_docs": 0, "dedup_skipped": 0},
            )
            return []

        # 去重：计算内容哈希，跳过已存在的文档
        skipped = 0
        if dedup:
            documents, skipped = self._dedup_by_content_hash(documents, collection_name)

        if not documents:
            logger.info("All documents are duplicates, nothing to add")
            return []

        # 清理 metadata 中 Chroma 不支持的类型（list, 内部审计字段等）
        for doc in documents:
            doc.metadata = sanitize_for_chroma(doc.metadata)

        ids = self._index_and_emit(
            documents,
            collection_name,
            started=start,
            input_docs=original_count,
            dedup_skipped=skipped,
        )
        # 写入成功后失效哈希缓存（新增的哈希需重新读取）
        self._hash_cache.pop(collection_name, None)
        return ids

    def delete_collection(self, collection_name: str) -> None:
        """删除集合"""
        try:
            self.client.delete_collection(collection_name)
            self._stores.pop(collection_name, None)
            self._hash_cache.pop(collection_name, None)
            self._hnsw_checked.discard(collection_name)
        except Exception as e:
            logger.warning("Failed to delete collection %s: %s", collection_name, e)
