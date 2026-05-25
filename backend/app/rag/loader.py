"""文档加载器 — LangChain 原生 Loader + PyMuPDF4LLM

支持的文件类型：
  .pdf  → PyMuPDF4LLM（PDF→Markdown，保留表格/公式结构）
  .txt  → TextLoader（autodetect_encoding=True 自动编码检测）
  .md   → TextLoader（同上，Markdown 作为纯文本加载）
  .docx → Docx2txtLoader（原生 DOCX 解析）

PyMuPDF4LLM 相比 PyPDFLoader 的优势：
  - 表格保留为 Markdown 格式（PyPDFLoader 丢失表格）
  - 公式/代码块结构保持
  - 输出 Markdown 文本，与下游 splitter/cleaner 兼容
  - 轻量高效，无需 GPU
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from langchain_core.documents import Document
from langchain_community.document_loaders import Docx2txtLoader, TextLoader
import pymupdf4llm

# ── 编码检测（langchain_community TextLoader.autodetect_encoding 与
#    charset_normalizer>=3.4 不兼容，自研三级策略替代） ──
_CN_ENCODINGS = ["utf-8", "utf-8-sig", "gb18030", "gbk", "gb2312", "big5"]


def _detect_and_read(filepath: str) -> str:
    """四级编码检测：UTF-8 严格 → 中文编码候选列表 → cchardet → utf-8 replace

    注意：cchardet 对中文 UTF-8 文件可能误判为 Windows-1252，
    导致 Mojibake（乱码），因此 UTF-8 严格解码优先于 cchardet。
    """
    raw = open(filepath, "rb").read()
    # 1. UTF-8 严格解码（knowledge base 文件均为 UTF-8）
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    # 2. 中文编码候选列表（utf-8-sig, GB 系列, Big5）
    for enc in _CN_ENCODINGS[1:]:  # skip utf-8, already tried
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    # 3. cchardet / chardet（作为兜底，不优先）
    try:
        import cchardet as chardet_mod
        result = chardet_mod.detect(raw)
        enc = result.get("encoding")
        if enc:
            return raw.decode(enc, errors="replace")
    except ImportError:
        try:
            import chardet as chardet_mod
            result = chardet_mod.detect(raw)
            enc = result.get("encoding")
            if enc:
                return raw.decode(enc, errors="replace")
        except ImportError:
            pass
    # 4. utf-8 replace 兜底
    return raw.decode("utf-8", errors="replace")

logger = logging.getLogger(__name__)
# ── 支持的文件扩展名 ──────────────────────────────────
SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}

# ── Loader 映射 ───────────────────────────────────────
_PDF_LOADER = "pymupdf4llm"
_LOADER_MAP: dict[str, type | str] = {
    ".pdf": _PDF_LOADER,
    ".txt": TextLoader,
    ".md": TextLoader,
    ".docx": Docx2txtLoader,
}


# ════════════════════════════════════════════════════════
#  单文件加载
# ════════════════════════════════════════════════════════

def load_single_file(filepath: str | Path) -> list[Document]:
    """使用 LangChain 原生 Loader 加载单个文件

    Args:
        filepath: 文件路径

    Returns:
        Document 列表（PDF 按页拆分，其他格式通常为单个 Document）
    """
    filepath = str(filepath)
    ext = os.path.splitext(filepath)[1].lower()

    if ext not in _LOADER_MAP:
        raise ValueError(f"不支持的文件类型: {ext}（支持: {SUPPORTED_EXTENSIONS}）")

    loader_cls = _LOADER_MAP[ext]

    if loader_cls is _PDF_LOADER:
        # ── PyMuPDF4LLM: PDF → Markdown ──
        docs = _load_pdf_with_pymupdf(filepath)
    elif loader_cls is TextLoader:
        # TextLoader.autodetect_encoding 与 charset_normalizer>=3.4 不兼容
        # 使用自研三级编码检测
        text = _detect_and_read(filepath)
        docs = [Document(page_content=text, metadata={"source": filepath})]
    else:
        loader = loader_cls(filepath)
        docs = loader.load()

    # 注入标准元数据
    for doc in docs:
        doc.metadata["source"] = filepath
        doc.metadata["source_file"] = os.path.basename(filepath)
        doc.metadata["source_path"] = filepath
        doc.metadata["file_type"] = ext.lstrip(".")

    logger.debug("Loaded %s: %d documents", filepath, len(docs))
    return docs


# ════════════════════════════════════════════════════════
#  PyMuPDF4LLM: PDF → Markdown Document
# ════════════════════════════════════════════════════════

def _load_pdf_with_pymupdf(filepath: str) -> list[Document]:
    """使用 PyMuPDF4LLM 将 PDF 转为 Markdown Document 列表

    PyMuPDF4LLM 输出 Markdown 文本，表格保留为 Markdown 表格格式，
    公式/代码块结构保持，与下游 cleaner/splitter 完全兼容。

    按页拆分，每页一个 Document，保留页码元数据。
    """
    try:
        md_pages: list[str] = pymupdf4llm.to_markdown(filepath, page_chunks=True)
    except Exception as e:
        logger.warning("PyMuPDF4LLM failed for '%s': %s, fallback to PyPDFLoader", filepath, e)
        # 回退到 PyPDFLoader
        from langchain_community.document_loaders import PyPDFLoader
        return PyPDFLoader(filepath).load()

    docs: list[Document] = []
    for page_idx, page_text in enumerate(md_pages):
        if isinstance(page_text, dict):
            # pymupdf4llm 某些版本返回 dict
            text = page_text.get("text", "")
            metadata = {
                "source": filepath,
                "page": page_text.get("page", page_idx + 1),
            }
        else:
            text = str(page_text)
            metadata = {
                "source": filepath,
                "source_file": os.path.basename(filepath),
                "source_path": filepath,
                "page": page_idx + 1,
            }

        if text.strip():
            docs.append(Document(page_content=text, metadata=metadata))

    if not docs:
        # 空结果回退
        logger.warning("PyMuPDF4LLM returned empty for '%s', fallback to PyPDFLoader", filepath)
        from langchain_community.document_loaders import PyPDFLoader
        return PyPDFLoader(filepath).load()

    return docs

