"""学习路径入库：``knowledge/learning_paths/`` → ``learning_paths`` 集合。

这是 ``rag.ingest`` 通用链路的唯一剩余语料（四科讲义目录退役后）：
``load → clean → split → enhance → tag``。
"""

from __future__ import annotations

from langchain_core.documents import Document

from rag.chunking.cleaner import clean_documents
from rag.chunking.enhancer import enhance_documents
from rag.chunking.loader import SUPPORTED_EXTENSIONS, load_single_file
from rag.chunking.splitter import split_documents
from rag.common.vectorstore import get_vector_store_manager
from rag.ingest_layers import _shared
from rag.knowledge_tagger import tag_chunks_with_knowledge_points

COLLECTION = "learning_paths"
LP_DIR = _shared.KNOWLEDGE_DIR / "learning_paths"


def build() -> tuple[list[Document], list[dict], dict]:
    """构建 learning_paths chunk（纯函数：不落库、不写 links）。"""
    chunks: list[Document] = []
    if not LP_DIR.is_dir():
        return chunks, [], {"chunks": 0, "skipped": True}
    files = sorted(
        p for p in LP_DIR.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    for filepath in files:
        documents = load_single_file(str(filepath))
        documents = clean_documents(documents, dedup=True, fuzzy_dedup=False, fuzzy_threshold=0.9)
        cs = split_documents(documents)
        cs = enhance_documents(cs)
        for chunk in cs:
            chunk.metadata["category"] = COLLECTION
            chunk.metadata["kb_depth"] = "learning_path"
        cs = tag_chunks_with_knowledge_points(cs, fallback_category=COLLECTION)
        chunks.extend(cs)
    return chunks, [], {"chunks": len(chunks)}


def ingest() -> dict:
    mgr = get_vector_store_manager()
    chunks, _, stats = build()
    if stats.get("skipped"):
        return stats
    ids = mgr.add_documents(chunks, collection_name=COLLECTION)
    mgr.wait_until_ready(COLLECTION)
    print(f"  [{COLLECTION}] chunks={len(chunks)} new={len(ids)}")
    return stats
