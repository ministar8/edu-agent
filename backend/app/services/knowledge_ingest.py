from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}


def ingest_file_to_knowledge_base(file_path: str | Path, category: str) -> dict:
    from app.rag.cleaner import clean_documents
    from app.rag.enhancer import enhance_documents
    from app.rag.graph_builder import build_graph_from_documents
    from app.rag.knowledge_tagger import tag_chunks_with_knowledge_points
    from app.rag.loader import load_single_file
    from app.rag.splitter import split_documents
    from app.rag.vectorstore import get_vector_store_manager

    path = Path(file_path)

    documents = load_single_file(str(path))
    documents = clean_documents(documents)
    chunks = split_documents(documents)
    chunks = enhance_documents(chunks)

    for chunk in chunks:
        chunk.metadata["category"] = category

    # 知识点标签：从 heading_path 提取并写入 Registry + chunk metadata
    chunks = tag_chunks_with_knowledge_points(chunks, fallback_category=category)

    get_vector_store_manager().add_documents(chunks, collection_name=category)
    graph_result = build_graph_from_documents(chunks, category=category)

    return {
        "filename": path.name,
        "chunk_count": len(chunks),
        "graph_nodes": graph_result["nodes_added"],
        "graph_edges": graph_result["edges_added"],
        "success": True,
    }
