import logging

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document

from app.config import settings
from app.rag.embeddings import get_embeddings

logger = logging.getLogger(__name__)


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

    def get_store(self, collection_name: str = "knowledge") -> Chroma:
        """获取或创建向量存储"""
        if collection_name not in self._stores:
            self._stores[collection_name] = Chroma(
                client=self.client,
                collection_name=collection_name,
                embedding_function=self.embeddings,
            )
        return self._stores[collection_name]

    def add_documents(
        self,
        documents: list[Document],
        collection_name: str = "knowledge",
    ) -> list[str]:
        """添加文档到向量存储"""
        store = self.get_store(collection_name)
        ids = store.add_documents(documents)
        return ids

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


vector_store_manager = VectorStoreManager()
