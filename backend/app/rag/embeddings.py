from __future__ import annotations

import logging
from typing import List

from langchain_core.embeddings import Embeddings
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)

# DashScope 单次请求上限
BATCH_SIZE = 25
# 单条文本最大字符数（text-embedding-v3 上限 8192 tokens，约 16000 中文字符）
MAX_TEXT_LENGTH = 8000


class DashScopeEmbeddings(BaseModel, Embeddings):
    """阿里 DashScope Embedding（OpenAI 兼容接口，自动分批）"""

    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "text-embedding-v3"

    model_config = {"arbitrary_types_allowed": True}

    def _embed_batch(self, texts: List[str]) -> List[List[float]]:
        """单批次调用 DashScope Embedding API"""
        import httpx

        # 截断超长文本，防止 400 错误
        truncated = [t[:MAX_TEXT_LENGTH] if len(t) > MAX_TEXT_LENGTH else t for t in texts]

        resp = httpx.post(
            f"{self.base_url}/embeddings",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={"model": self.model, "input": [str(t) for t in truncated]},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        sorted_data = sorted(data["data"], key=lambda x: x["index"])
        return [item["embedding"] for item in sorted_data]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """分批 Embedding，每批 BATCH_SIZE 条"""
        if not texts:
            return []

        all_embeddings: List[List[float]] = []
        for i in range(0, len(texts), BATCH_SIZE):
            batch = texts[i : i + BATCH_SIZE]
            logger.debug("Embedding batch %d/%d (%d texts)", i // BATCH_SIZE + 1, -(-len(texts) // BATCH_SIZE), len(batch))
            all_embeddings.extend(self._embed_batch(batch))

        return all_embeddings

    def embed_query(self, text: str) -> List[float]:
        result = self.embed_documents([str(text)])
        return result[0]


def get_embeddings() -> Embeddings:
    """返回 Embedding 模型（通过 OpenAI 兼容接口）"""
    return DashScopeEmbeddings(
        api_key=settings.EMBEDDING_API_KEY,
        base_url=settings.EMBEDDING_API_BASE,
        model=settings.EMBEDDING_MODEL,
    )
