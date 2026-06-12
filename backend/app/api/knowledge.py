import logging
import os
import re
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Form, Depends

from app.config import settings
from app.api.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

UPLOAD_DIR = Path(settings.KNOWLEDGE_DIR)



def _safe_filename(filename: str) -> str:
    """Sanitize filename to prevent path traversal."""
    # Remove path components
    basename = os.path.basename(filename)
    # Remove null bytes and dangerous characters
    basename = basename.replace("\x00", "").replace("..", "")
    # Only allow safe characters
    basename = re.sub(r'[^a-zA-Z0-9_.\-\u4e00-\u9fff]', '_', basename)
    return basename or "uploaded_file"


async def _save_upload_file(file: UploadFile, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    # 上传文件名来自客户端，保存前必须清洗，避免路径穿越和非法字符。
    filepath = target_dir / _safe_filename(file.filename or "")
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


@router.post("/batch-upload")
async def batch_upload(files: list[UploadFile] = File(...), category: str = Form("data_structure"), current_user=Depends(get_current_user)):
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


@router.delete("/collections/{collection_name}")
async def delete_collection(collection_name: str, current_user=Depends(get_current_user)):
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


