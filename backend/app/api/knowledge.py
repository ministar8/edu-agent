import os
import logging

from fastapi import APIRouter, UploadFile, File, Form

from app.config import settings
from app.rag.loader import load_single_file
from app.rag.splitter import split_documents
from app.rag.vectorstore import vector_store_manager

logger = logging.getLogger(__name__)

router = APIRouter()

UPLOAD_DIR = settings.KNOWLEDGE_DIR


@router.get("/collections")
async def list_collections():
    """列出所有知识库集合"""
    collections = vector_store_manager.list_collections()
    info = [vector_store_manager.get_collection_info(c) for c in collections]
    return {"collections": info}


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    category: str = Form("general"),
):
    """上传文档到知识库"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    filepath = os.path.join(UPLOAD_DIR, file.filename)
    with open(filepath, "wb") as f:
        content = await file.read()
        f.write(content)

    try:
        documents = load_single_file(filepath)
        chunks = split_documents(documents)

        for chunk in chunks:
            chunk.metadata["category"] = category

        vector_store_manager.add_documents(chunks, collection_name=category)

        return {
            "success": True,
            "filename": file.filename,
            "chunk_count": len(chunks),
            "category": category,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.post("/batch-upload")
async def batch_upload(files: list[UploadFile] = File(...), category: str = Form("general")):
    """批量上传文档"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    results = []

    for file in files:
        filepath = os.path.join(UPLOAD_DIR, file.filename)
        with open(filepath, "wb") as f:
            content = await file.read()
            f.write(content)

        try:
            documents = load_single_file(filepath)
            chunks = split_documents(documents)
            for chunk in chunks:
                chunk.metadata["category"] = category
            vector_store_manager.add_documents(chunks, collection_name=category)
            results.append({"filename": file.filename, "chunk_count": len(chunks), "success": True})
        except Exception as e:
            results.append({"filename": file.filename, "error": str(e), "success": False})

    return {"results": results}


@router.post("/import-local")
async def import_local(category: str = "general"):
    """扫描 knowledge/{category}/ 目录，自动导入所有文件到知识库"""
    dir_path = os.path.join(UPLOAD_DIR, category)
    if not os.path.isdir(dir_path):
        return {"success": False, "error": f"目录不存在: {dir_path}"}

    supported_ext = {".pdf", ".txt", ".md", ".docx"}
    results = []
    total_chunks = 0

    for filename in os.listdir(dir_path):
        ext = os.path.splitext(filename)[1].lower()
        if ext not in supported_ext:
            continue

        filepath = os.path.join(dir_path, filename)
        try:
            documents = load_single_file(filepath)
            chunks = split_documents(documents)
            for chunk in chunks:
                chunk.metadata["category"] = category
            vector_store_manager.add_documents(chunks, collection_name=category)
            total_chunks += len(chunks)
            results.append({"filename": filename, "chunk_count": len(chunks), "success": True})
            logger.info("Imported %s: %d chunks", filename, len(chunks))
        except Exception as e:
            results.append({"filename": filename, "error": str(e), "success": False})
            logger.error("Failed to import %s: %s", filename, e)

    return {
        "success": True,
        "category": category,
        "files_processed": len(results),
        "total_chunks": total_chunks,
        "results": results,
    }


@router.delete("/collections/{collection_name}")
async def delete_collection(collection_name: str):
    """删除知识库集合"""
    vector_store_manager.delete_collection(collection_name)
    return {"success": True, "deleted": collection_name}


@router.get("/search")
async def search_knowledge(query: str, collection: str = "general", k: int = 5):
    """搜索知识库（用于可视化展示检索过程）"""
    from app.rag.retriever import retrieve_with_scores, rewrite_query

    try:
        original_query = query
        rewritten_query = rewrite_query(query)
        results = retrieve_with_scores(rewritten_query, collection_name=collection, k=k)
        return {
            "original_query": original_query,
            "rewritten_query": rewritten_query,
            "results": results,
        }
    except Exception as e:
        logger.error("Search error: %s", e)
        return {
            "original_query": query,
            "rewritten_query": query,
            "results": [],
        }
