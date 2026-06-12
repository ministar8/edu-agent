from fastapi import APIRouter, UploadFile, File, Form, Depends

from app.api.auth import get_current_user
from app.core.dependencies import get_knowledge_base_service
from app.services.knowledge_base_service import KnowledgeBaseService

router = APIRouter()

_save_upload_file = KnowledgeBaseService.save_upload_file



@router.get("/collections")
async def list_collections(service: KnowledgeBaseService = Depends(get_knowledge_base_service)):
    """列出所有知识库集合"""
    return service.list_collections()


@router.post("/batch-upload")
async def batch_upload(
    files: list[UploadFile] = File(...),
    category: str = Form("data_structure"),
    current_user=Depends(get_current_user),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
):
    """批量上传文档"""
    return await service.batch_upload(files, category)


@router.delete("/collections/{collection_name}")
async def delete_collection(
    collection_name: str,
    current_user=Depends(get_current_user),
    service: KnowledgeBaseService = Depends(get_knowledge_base_service),
):
    """删除知识库集合（同步清理向量库 + 知识图谱）"""
    return service.delete_collection(collection_name)
