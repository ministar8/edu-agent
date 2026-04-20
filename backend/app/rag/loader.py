import logging
import os

from langchain_community.document_loaders import PyPDFLoader, TextLoader, Docx2txtLoader
from langchain_core.documents import Document

from app.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".pdf": PyPDFLoader,
    ".txt": TextLoader,
    ".md": TextLoader,
    ".docx": Docx2txtLoader,
}


def load_documents(directory: str | None = None) -> list[Document]:
    """加载目录下所有支持的文档"""
    doc_dir = directory or settings.KNOWLEDGE_DIR
    documents = []

    if not os.path.exists(doc_dir):
        os.makedirs(doc_dir, exist_ok=True)
        return documents

    for filename in os.listdir(doc_dir):
        ext = os.path.splitext(filename)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            continue

        filepath = os.path.join(doc_dir, filename)
        loader_cls = SUPPORTED_EXTENSIONS[ext]

        try:
            if loader_cls is TextLoader:
                loader = loader_cls(filepath, encoding="utf-8")
            else:
                loader = loader_cls(filepath)
            docs = loader.load()
            for doc in docs:
                doc.metadata["source_file"] = filename
            documents.extend(docs)
        except Exception as e:
            logger.warning("Failed to load %s: %s", filepath, e)

    return documents


def load_single_file(filepath: str) -> list[Document]:
    """加载单个文件"""
    ext = os.path.splitext(filepath)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}")

    loader_cls = SUPPORTED_EXTENSIONS[ext]
    # TextLoader 需显式指定 UTF-8 编码，否则中文文件会报错
    if loader_cls is TextLoader:
        loader = loader_cls(filepath, encoding="utf-8")
    else:
        loader = loader_cls(filepath)
    docs = loader.load()
    for doc in docs:
        doc.metadata["source_file"] = os.path.basename(filepath)
    return docs
