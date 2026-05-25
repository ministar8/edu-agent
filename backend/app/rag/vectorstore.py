import hashlib
import logging
import time

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.config import settings
from app.rag.embeddings import get_embeddings
from app.rag.metrics import metrics
from app.rag._metadata_spec import sanitize_for_chroma

logger = logging.getLogger(__name__)

# ── HNSW 索引参数（针对 bge-m3 1024 维向量优化） ─────
# bge-m3 输出 1024 维 dense vector，配置 HNSW 参数确保召回精度
_HNSW_M = 32                     # 每节点最大连接数（默认 16，高维数据用 32）
_HNSW_EF_CONSTRUCTION = 300      # 索引构建候选数（越大质量越高，构建稍慢）
_HNSW_EF_SEARCH = 100            # 检索候选数（≈ k × 15~20，k=5~8 时 100 合理）
_HNSW_SPACE = "cosine"           # bge-m3 官方推荐余弦距离

_HNSW_COLLECTION_METADATA = {
    "hnsw:M": _HNSW_M,
    "hnsw:construction_ef": _HNSW_EF_CONSTRUCTION,
    "hnsw:search_ef": _HNSW_EF_SEARCH,
    "hnsw:space": _HNSW_SPACE,
}

_LEGACY_HNSW_KEYS = {
    "hnsw:ef_construction": "hnsw:construction_ef",
    "hnsw:ef_search": "hnsw:search_ef",
}


def _content_hash(content: str) -> str:
    """生成内容的 SHA256 哈希，用于去重"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


class VectorStoreManager:
    """向量数据库管理器"""

    def __init__(self) -> None:
        self._embeddings = None
        self.client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        self._stores: dict[str, Chroma] = {}
        self._hnsw_degraded: dict[str, str] = {}
        self._hash_cache: dict[str, tuple[set[str], float]] = {}
        self._hnsw_checked: set[str] = set()

    @property
    def embeddings(self):
        """懒加载 Embedding 模型，首次访问时才初始化"""
        if self._embeddings is None:
            self._embeddings = get_embeddings()
        return self._embeddings

    def _ensure_hnsw_params(self, collection_name: str) -> None:
        """确保已有集合的 HNSW 索引参数为目标配置

        ChromaDB 的 `get_or_create_collection(metadata=...)` 在集合已存在时
        不会更新 metadata，需要单独调用 `modify()` 写入。
        """
        try:
            collection = self.client.get_collection(collection_name)
            current = collection.metadata or {}
            if collection.count() > 0:
                missing = [key for key in _HNSW_COLLECTION_METADATA if key not in current]
                legacy = [key for key in _LEGACY_HNSW_KEYS if key in current]
                if missing or legacy:
                    logger.warning(
                        "Collection '%s' needs rebuild for HNSW params (missing=%s legacy=%s)",
                        collection_name, missing, legacy,
                    )
                    return
            # 只有当缺少目标字段时才更新（避免不必要的 I/O）
            needs_update = any(
                key not in current or str(current.get(key, "")) != str(val)
                for key, val in _HNSW_COLLECTION_METADATA.items()
            )
            if needs_update:
                merged = {**current, **_HNSW_COLLECTION_METADATA}
                collection.modify(metadata=merged)
                logger.info(
                    "Updated HNSW params for collection '%s': %s",
                    collection_name, _HNSW_COLLECTION_METADATA,
                )
            self._hnsw_degraded.pop(collection_name, None)
        except Exception as e:
            self._hnsw_degraded[collection_name] = str(e)
            logger.debug("Could not update HNSW params for '%s': %s", collection_name, e)

    def get_store(self, collection_name: str = "data_structure") -> Chroma:
        """获取或创建向量存储（HNSW 索引参数在创建时写入，已有集合自动更新）"""
        if collection_name not in self._stores:
            # 新集合：创建时指定 HNSW 参数
            # 若集合已存在，get_or_create_collection 不会更新 metadata，
            # 因此无论新旧都通过 _ensure_hnsw_params 保证参数一致
            try:
                self._stores[collection_name] = Chroma(
                    client=self.client,
                    collection_name=collection_name,
                    embedding_function=self.embeddings,
                    collection_metadata=_HNSW_COLLECTION_METADATA,
                )
                if collection_name not in self._hnsw_checked:
                    self._ensure_hnsw_params(collection_name)
                    self._hnsw_checked.add(collection_name)
            except Exception as e:
                self._hnsw_degraded[collection_name] = str(e)
                # HNSW 参数解析失败（Chroma 版本不兼容或索引损坏），
                # 回退为不传 HNSW metadata，让 Chroma 使用默认参数
                logger.warning(
                    "get_store('%s') with HNSW metadata failed (%s), retrying without",
                    collection_name, e,
                )
                self._stores[collection_name] = Chroma(
                    client=self.client,
                    collection_name=collection_name,
                    embedding_function=self.embeddings,
                )
        return self._stores[collection_name]

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
            existing_hashes = self._get_existing_hashes(collection_name)
            unique_docs: list[Document] = []
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
                    skipped, len(documents), collection_name,
                )
            documents = unique_docs

        if not documents:
            logger.info("All documents are duplicates, nothing to add")
            return []

        # 清理 metadata 中 Chroma 不支持的类型（list, 内部审计字段等）
        for doc in documents:
            doc.metadata = sanitize_for_chroma(doc.metadata)

        try:
            store = self.get_store(collection_name)
            ids = store.add_documents(documents)
            metrics.emit(
                event="index_documents",
                stage="vectorstore",
                duration_ms=round((time.perf_counter() - start) * 1000, 3),
                tags={"collection": collection_name},
                values={
                    "input_docs": original_count,
                    "dedup_skipped": skipped,
                    "ready_docs": len(documents),
                    "indexed_docs": len(ids),
                    "index_success_rate": round(len(ids) / len(documents), 6) if documents else 0.0,
                },
            )
            # Invalidate hash cache after successful add (new hashes incoming)
            self._hash_cache.pop(collection_name, None)
            return ids
        except Exception as e:
            metrics.emit(
                event="index_documents",
                stage="vectorstore",
                status="error",
                duration_ms=round((time.perf_counter() - start) * 1000, 3),
                tags={"collection": collection_name},
                values={
                    "input_docs": original_count,
                    "dedup_skipped": skipped,
                    "ready_docs": len(documents),
                    "error_type": e.__class__.__name__,
                },
            )
            raise

    def delete_collection(self, collection_name: str) -> None:
        """删除集合"""
        try:
            self.client.delete_collection(collection_name)
            self._stores.pop(collection_name, None)
            self._hash_cache.pop(collection_name, None)
            self._hnsw_checked.discard(collection_name)
        except Exception as e:
            logger.warning("Failed to delete collection %s: %s", collection_name, e)

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
                key for key, val in _HNSW_COLLECTION_METADATA.items()
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
            return {"name": collection_name, "count": 0}


_vector_store_manager: VectorStoreManager | None = None


def get_vector_store_manager() -> VectorStoreManager:
    """懒加载向量数据库管理器（单例）"""
    global _vector_store_manager
    if _vector_store_manager is None:
        _vector_store_manager = VectorStoreManager()
    return _vector_store_manager

