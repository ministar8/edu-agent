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


def _content_hash(content: str) -> str:
    """生成内容的 SHA256 哈希，用于去重"""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


class VectorStoreManager:
    """向量数据库管理器"""

    def __init__(self) -> None:
        self._embeddings = None
        self.client = chromadb.PersistentClient(path=settings.CHROMA_PERSIST_DIR)
        self._stores: dict[str, Chroma] = {}

    @property
    def embeddings(self):
        """懒加载 Embedding 模型，首次访问时才初始化"""
        if self._embeddings is None:
            self._embeddings = get_embeddings()
        return self._embeddings

    def get_store(self, collection_name: str = "data_structure") -> Chroma:
        """获取或创建向量存储"""
        if collection_name not in self._stores:
            self._stores[collection_name] = Chroma(
                client=self.client,
                collection_name=collection_name,
                embedding_function=self.embeddings,
            )
        return self._stores[collection_name]

    def _get_existing_hashes(self, collection_name: str) -> set[str]:
        """获取集合中已有内容的哈希集合，用于去重"""
        try:
            collection = self.client.get_collection(collection_name)
            if collection.count() == 0:
                return set()
            # 获取所有文档的元数据中的 content_hash
            result = collection.get(include=["metadatas"])
            hashes = set()
            for meta in result.get("metadatas", []) or []:
                h = meta.get("content_hash") if meta else None
                if h:
                    hashes.add(h)
            return hashes
        except Exception:
            return set()

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
        except Exception as e:
            logger.warning("Failed to delete collection %s: %s", collection_name, e)

    def list_collections(self) -> list[str]:
        """列出所有集合"""
        return [col.name for col in self.client.list_collections()]

    def get_collection_info(self, collection_name: str) -> dict:
        """获取集合信息"""
        try:
            collection = self.client.get_collection(collection_name)
            return {
                "name": collection_name,
                "count": collection.count(),
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


def __getattr__(name):
    """兼容旧代码 from app.rag.vectorstore import vector_store_manager"""
    if name == "vector_store_manager":
        return get_vector_store_manager()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
