import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

UPLOAD_DIR = Path(settings.KNOWLEDGE_DIR)


async def _save_upload_file(file: UploadFile, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    filepath = target_dir / file.filename
    content = await file.read()
    filepath.write_bytes(content)
    return filepath


@router.get("/collections")
async def list_collections():
    """列出所有知识库集合"""
    from app.rag.vectorstore import get_vector_store_manager

    vsm = get_vector_store_manager()
    collections = vsm.list_collections()
    info = [vsm.get_collection_info(c) for c in collections]
    return {"collections": info}


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    category: str = Form("data_structure"),
):
    """上传文档到知识库"""
    filepath = await _save_upload_file(file, UPLOAD_DIR)

    try:
        from app.services.knowledge_ingest import ingest_file_to_knowledge_base
        result = ingest_file_to_knowledge_base(filepath, category)

        return {
            "category": category,
            **result,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/batch-upload")
async def batch_upload(files: list[UploadFile] = File(...), category: str = Form("data_structure")):
    """批量上传文档"""
    from app.services.knowledge_ingest import ingest_file_to_knowledge_base

    results = []

    for file in files:
        try:
            filepath = await _save_upload_file(file, UPLOAD_DIR)
            results.append(ingest_file_to_knowledge_base(filepath, category))
        except Exception as e:
            results.append({"filename": file.filename, "error": str(e), "success": False})

    return {"results": results}


@router.post("/import-local")
async def import_local(category: str = "data_structure"):
    """扫描 knowledge/{category}/ 目录，自动导入所有文件到知识库"""
    dir_path = UPLOAD_DIR / category
    if not dir_path.is_dir():
        return {"success": False, "error": f"目录不存在: {dir_path}"}

    results = []
    total_chunks = 0

    from app.services.knowledge_ingest import SUPPORTED_EXTENSIONS, ingest_file_to_knowledge_base

    for filepath in dir_path.iterdir():
        if filepath.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        try:
            result = ingest_file_to_knowledge_base(filepath, category)
            total_chunks += result["chunk_count"]
            results.append(result)
            logger.info("Imported %s: %d chunks", filepath.name, result["chunk_count"])
        except Exception as e:
            results.append({"filename": filepath.name, "error": str(e), "success": False})
            logger.error("Failed to import %s: %s", filepath.name, e)

    return {
        "success": True,
        "category": category,
        "files_processed": len(results),
        "total_chunks": total_chunks,
        "results": results,
    }


@router.delete("/collections/{collection_name}")
async def delete_collection(collection_name: str):
    """删除知识库集合（同步清理向量库 + 知识图谱）"""
    from app.rag.vectorstore import get_vector_store_manager

    get_vector_store_manager().delete_collection(collection_name)
    # 同步清理知识图谱中该分类的节点
    try:
        from app.rag.knowledge_graph import get_kg_manager
        deleted = get_kg_manager().delete_by_category(collection_name)
        if deleted:
            logger.info("KG cleanup for collection '%s': %d nodes removed", collection_name, deleted)
    except Exception as e:
        logger.warning("KG cleanup failed for collection '%s' (non-fatal): %s", collection_name, e)
    return {"success": True, "deleted": collection_name}


@router.get("/search")
async def search_knowledge(query: str, collection: str = "data_structure", k: int = 5):
    """搜索知识库（统一检索管线，用于可视化展示检索过程）"""
    from app.rag.retriever import retrieve_documents, build_rag_context, _kg_context_supplement

    try:
        docs = retrieve_documents(query=query, collection_name=collection, k=k, use_rerank=True)
        kg_supplement = ""
        try:
            kg_supplement = _kg_context_supplement(query)
        except Exception:
            logger.debug("KG context supplement failed for query=%s", query[:30])
        result_text = build_rag_context(docs, query=query, kg_supplement=kg_supplement) if docs else ""

        # 获取源文档节点信息
        source_nodes = []
        for doc in docs[:k]:
            source_nodes.append({
                "content": doc.page_content[:200] if doc.page_content else "",
                "score": float(doc.metadata.get("rerank_score", 0.0)),
                "metadata": doc.metadata,
            })

        return {
            "original_query": query,
            "engine_type": "LangChain unified (semantic+BM25+KG+Reranker)",
            "collection": collection,
            "answer": result_text,
            "source_nodes": source_nodes,
        }
    except Exception as e:
        logger.error("Search error: %s", e, exc_info=True)
        return {
            "original_query": query,
            "engine_type": "LangChain unified",
            "collection": collection,
            "answer": "",
            "source_nodes": [],
        }


@router.get("/consistency")
async def consistency_check(category: str = ""):
    """检查 ChromaDB 与 Neo4j 之间的数据一致性"""
    try:
        from app.services.consistency_checker import check_consistency
        report = await asyncio.to_thread(check_consistency, category)
        return {"success": True, **report}
    except Exception as e:
        logger.error("Consistency check failed: %s", e)
        return {"success": False, "error": str(e)}


@router.post("/consistency/cleanup")
async def consistency_cleanup(category: str = ""):
    """清理孤儿节点（KG 中存在但 ChromaDB 中无对应文档的节点）"""
    try:
        from app.services.consistency_checker import cleanup_orphans
        result = await asyncio.to_thread(cleanup_orphans, category)
        return {"success": True, **result}
    except Exception as e:
        logger.error("Orphan cleanup failed: %s", e)
        return {"success": False, "error": str(e)}
