from __future__ import annotations

import logging
import os
import re
from pathlib import Path

from fastapi import UploadFile

from app.config import settings

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    def __init__(self, upload_dir: Path | None = None) -> None:
        self.upload_dir = upload_dir or Path(settings.KNOWLEDGE_DIR)

    @staticmethod
    def safe_filename(filename: str) -> str:
        basename = os.path.basename(filename)
        basename = basename.replace("\x00", "").replace("..", "")
        basename = re.sub(r"[^a-zA-Z0-9_.\-\u4e00-\u9fff]", "_", basename)
        return basename or "uploaded_file"

    @staticmethod
    async def save_upload_file(file: UploadFile, target_dir: Path) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        filepath = target_dir / KnowledgeBaseService.safe_filename(file.filename or "")
        content = await file.read()
        filepath.write_bytes(content)
        return filepath

    def list_collections(self) -> dict:
        from app.rag.vectorstore import get_vector_store_manager

        vector_store = get_vector_store_manager()
        collections = vector_store.list_collections()
        info = [vector_store.get_collection_info(collection) for collection in collections]
        return {"collections": info}

    async def batch_upload(self, files: list[UploadFile], category: str) -> dict:
        from app.services.knowledge_ingest import ingest_file_to_knowledge_base

        results = []
        for file in files:
            try:
                filepath = await self.save_upload_file(file, self.upload_dir)
                results.append(ingest_file_to_knowledge_base(filepath, category))
            except Exception as exc:
                results.append({"filename": file.filename, "error": str(exc), "success": False})
        return {"results": results}

    def delete_collection(self, collection_name: str) -> dict:
        from app.rag.vectorstore import get_vector_store_manager

        get_vector_store_manager().delete_collection(collection_name)
        try:
            from app.rag.knowledge_graph import get_kg_manager

            deleted = get_kg_manager().delete_by_category(collection_name)
            if deleted:
                logger.info("KG cleanup for collection '%s': %d nodes removed", collection_name, deleted)
        except Exception as exc:
            logger.warning("KG cleanup failed for collection '%s' (non-fatal): %s", collection_name, exc)
        return {"success": True, "deleted": collection_name}
