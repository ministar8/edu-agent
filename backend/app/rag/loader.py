import logging
import os
import time

from langchain_community.document_loaders import PyPDFLoader, TextLoader, Docx2txtLoader
from langchain_core.documents import Document

from app.config import settings
from app.rag.metrics import metrics

logger = logging.getLogger(__name__)


# ── PDF 表格提取 ──────────────────────────────────────

def _extract_pdf_tables(filepath: str) -> list[Document]:
    """从 PDF 中提取表格，转换为 Markdown 格式

    优先使用 camelot（基于 PDF 线条检测，表格识别精度高），
    不可用时回退到 pdfplumber（基于文本坐标推断，精度稍低但无需 Ghostscript）。

    Returns:
        表格 Document 列表，每个表格为一个 Document，
        page_content 为 Markdown 表格，metadata 包含页码和表格索引
    """
    table_docs: list[Document] = []

    # 尝试 camelot
    try:
        import camelot  # type: ignore[import-not-found]

        tables = camelot.read_pdf(filepath, pages="all", flavor="stream")
        for i, table in enumerate(tables):
            md = table.df.to_markdown(index=False)
            if md and len(md.strip()) > 10:
                table_docs.append(Document(
                    page_content=md,
                    metadata={
                        "source": filepath,
                        "table_index": i,
                        "table_page": table.page,
                        "table_extraction": "camelot",
                    },
                ))
        if table_docs:
            logger.info("camelot extracted %d tables from %s", len(table_docs), filepath)
            return table_docs
    except ImportError:
        logger.debug("camelot not available, trying pdfplumber")
    except Exception as e:
        logger.debug("camelot failed for %s: %s, trying pdfplumber", filepath, e)

    # 回退到 pdfplumber
    try:
        import pdfplumber  # type: ignore[import-not-found]

        with pdfplumber.open(filepath) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                for table_idx, table in enumerate(page.extract_tables()):
                    if not table or len(table) < 2:
                        continue
                    # 转换为 Markdown 表格
                    header = table[0]
                    rows = table[1:]
                    # 清理单元格：去除 None 和多余空白
                    header = [str(c or "").strip() for c in header]
                    rows = [[str(c or "").strip() for c in row] for row in rows]
                    if not any(header):
                        # 无表头：用第一行做表头
                        header = rows[0] if rows else []
                        rows = rows[1:] if rows else []
                    if not header or not rows:
                        continue
                    md_lines = ["| " + " | ".join(header) + " |"]
                    md_lines.append("| " + " | ".join(["---"] * len(header)) + " |")
                    for row in rows:
                        md_lines.append("| " + " | ".join(row) + " |")
                    md = "\n".join(md_lines)
                    if len(md.strip()) > 10:
                        table_docs.append(Document(
                            page_content=md,
                            metadata={
                                "source": filepath,
                                "table_index": table_idx,
                                "table_page": page_num,
                                "table_extraction": "pdfplumber",
                            },
                        ))
        if table_docs:
            logger.info("pdfplumber extracted %d tables from %s", len(table_docs), filepath)
    except ImportError:
        logger.debug("pdfplumber not available, table extraction skipped for %s", filepath)
    except Exception as e:
        logger.debug("pdfplumber failed for %s: %s", filepath, e)

    return table_docs

# ── 自动编码检测 ──────────────────────────────────────

# 编码检测优先级：cchardet(C加速) > chardet(纯Python) > 硬编码UTF-8
_chardet_available: bool | None = None

# 常见中文编码候选列表（检测置信度低时按此顺序尝试）
_CN_ENCODING_CANDIDATES = [
    "utf-8",
    "gbk",
    "gb2312",
    "gb18030",
    "big5",
    "utf-16",
]

# 检测时读取的文件头字节数（足够检测编码，避免读整个文件）
_DETECT_SAMPLE_SIZE = 64 * 1024  # 64KB


def _detect_encoding(filepath: str) -> str:
    """自动检测文件编码

    策略：
    1. 优先用 cchardet/chardet 检测，置信度 ≥ 0.7 时采用
    2. 置信度 < 0.7 时，按中文编码候选列表逐一尝试解码
    3. 全部失败则回退到 utf-8（允许 errors='replace'）

    Returns:
        检测到的编码名称（如 'gbk', 'utf-8'）
    """
    global _chardet_available

    # 1. chardet 检测
    if _chardet_available is not False:
        try:
            import cchardet as chardet  # type: ignore[import-not-found]
            _chardet_available = True
        except ImportError:
            try:
                import chardet  # type: ignore[import-not-found]
                _chardet_available = True
            except ImportError:
                _chardet_available = False

    if _chardet_available:
        try:
            with open(filepath, "rb") as f:
                raw = f.read(_DETECT_SAMPLE_SIZE)
            result = chardet.detect(raw)
            encoding = result.get("encoding", "")
            confidence = result.get("confidence", 0.0)

            if encoding and confidence >= 0.7:
                logger.debug(
                    "Encoding detected: %s (confidence=%.2f) for %s",
                    encoding, confidence, filepath,
                )
                return encoding.lower()

            # 置信度低 → 走候选列表
            logger.debug(
                "Low confidence encoding: %s (%.2f) for %s, trying candidates",
                encoding, confidence, filepath,
            )
        except Exception as e:
            logger.debug("chardet failed for %s: %s", filepath, e)

    # 2. 候选编码逐一尝试
    for enc in _CN_ENCODING_CANDIDATES:
        try:
            with open(filepath, "r", encoding=enc) as f:
                f.read(_DETECT_SAMPLE_SIZE)
            logger.debug("Encoding candidate '%s' works for %s", enc, filepath)
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
        except Exception:
            continue

    # 3. 兜底 utf-8
    logger.warning("Could not detect encoding for %s, falling back to utf-8", filepath)
    return "utf-8"


def _load_text_with_encoding(filepath: str) -> list[Document]:
    """加载文本文件，自动检测编码

    流程：
    1. 先尝试 utf-8（最常见，速度最快）
    2. utf-8 失败 → 自动检测编码 → 用检测到的编码加载
    3. 检测到的编码也失败 → utf-8 + errors='replace'（保留内容，替换乱码字符）
    """
    # 快速路径：先试 utf-8
    try:
        loader = TextLoader(filepath, encoding="utf-8")
        docs = loader.load()
        return docs
    except (UnicodeDecodeError, UnicodeError):
        pass

    # 慢速路径：自动检测编码
    detected_enc = _detect_encoding(filepath)
    try:
        loader = TextLoader(filepath, encoding=detected_enc)
        docs = loader.load()
        # 标记检测到的编码
        for doc in docs:
            doc.metadata["detected_encoding"] = detected_enc
        logger.info("Loaded %s with detected encoding: %s", filepath, detected_enc)
        return docs
    except (UnicodeDecodeError, UnicodeError):
        pass

    # 兜底：utf-8 + replace
    logger.warning(
        "Encoding %s failed for %s, loading with utf-8 (errors=replace)",
        detected_enc, filepath,
    )
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        doc = Document(
            page_content=content,
            metadata={"source": filepath, "detected_encoding": "utf-8-replaced"},
        )
        return [doc]
    except Exception as e:
        logger.error("Failed to load %s even with errors=replace: %s", filepath, e)
        return []

SUPPORTED_EXTENSIONS = {
    ".pdf": PyPDFLoader,
    ".txt": TextLoader,
    ".md": TextLoader,
    ".docx": Docx2txtLoader,
}


def load_documents(directory: str | None = None) -> list[Document]:
    """加载目录下所有支持的文档（递归扫描子目录）"""
    doc_dir = directory or settings.KNOWLEDGE_DIR
    documents = []

    if not os.path.exists(doc_dir):
        os.makedirs(doc_dir, exist_ok=True)
        return documents

    for root, _dirs, files in os.walk(doc_dir):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            filepath = os.path.join(root, filename)
            loader_cls = SUPPORTED_EXTENSIONS[ext]

            try:
                start = time.perf_counter()
                if loader_cls is TextLoader:
                    docs = _load_text_with_encoding(filepath)
                else:
                    loader = loader_cls(filepath)
                    docs = loader.load()
                for doc in docs:
                    doc.metadata["source_file"] = filename
                    doc.metadata["source_path"] = os.path.relpath(filepath, doc_dir)
                    doc.metadata["source_ext"] = ext
                    doc.metadata["source_type"] = ext.lstrip(".") or "unknown"
                documents.extend(docs)

                # PDF 表格提取：额外提取表格为 Markdown 格式 Document
                if ext == ".pdf":
                    table_docs = _extract_pdf_tables(filepath)
                    for doc in table_docs:
                        doc.metadata["source_file"] = filename
                        doc.metadata["source_path"] = os.path.relpath(filepath, doc_dir)
                        doc.metadata["source_ext"] = ext
                        doc.metadata["source_type"] = "pdf_table"
                        doc.metadata["section.chunk_role"] = "table"
                    documents.extend(table_docs)
                detected_encoding = ""
                if docs:
                    detected_encoding = str(docs[0].metadata.get("detected_encoding") or "")
                metrics.emit(
                    event="load_file",
                    stage="loader",
                    duration_ms=round((time.perf_counter() - start) * 1000, 3),
                    tags={"file": filepath, "source_ext": ext},
                    values={
                        "doc_count": len(docs),
                        "parse_success": bool(docs),
                        "detected_encoding": detected_encoding,
                        "encoding_fallback": detected_encoding == "utf-8-replaced",
                    },
                )
            except Exception as e:
                metrics.emit(
                    event="load_file",
                    stage="loader",
                    status="error",
                    tags={"file": filepath, "source_ext": ext},
                    values={"parse_success": False, "error_type": e.__class__.__name__},
                )
                logger.warning("Failed to load %s: %s", filepath, e)

    return documents


def load_single_file(filepath: str) -> list[Document]:
    """加载单个文件"""
    ext = os.path.splitext(filepath)[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {ext}")

    loader_cls = SUPPORTED_EXTENSIONS[ext]
    start = time.perf_counter()
    try:
        if loader_cls is TextLoader:
            docs = _load_text_with_encoding(filepath)
        else:
            loader = loader_cls(filepath)
            docs = loader.load()
        for doc in docs:
            doc.metadata["source_file"] = os.path.basename(filepath)
            doc.metadata["source_path"] = os.path.basename(filepath)
            doc.metadata["source_ext"] = ext
            doc.metadata["source_type"] = ext.lstrip(".") or "unknown"

        # PDF 表格提取
        table_docs: list[Document] = []
        if ext == ".pdf":
            table_docs = _extract_pdf_tables(filepath)
            for doc in table_docs:
                doc.metadata["source_file"] = os.path.basename(filepath)
                doc.metadata["source_path"] = os.path.basename(filepath)
                doc.metadata["source_ext"] = ext
                doc.metadata["source_type"] = "pdf_table"
                doc.metadata["section.chunk_role"] = "table"

        all_docs = docs + table_docs
        detected_encoding = ""
        if docs:
            detected_encoding = str(docs[0].metadata.get("detected_encoding") or "")
        metrics.emit(
            event="load_file",
            stage="loader",
            duration_ms=round((time.perf_counter() - start) * 1000, 3),
            tags={"file": filepath, "source_ext": ext},
            values={
                "doc_count": len(all_docs),
                "table_count": len(table_docs),
                "parse_success": bool(docs),
                "detected_encoding": detected_encoding,
                "encoding_fallback": detected_encoding == "utf-8-replaced",
            },
        )
        return all_docs
    except Exception as e:
        metrics.emit(
            event="load_file",
            stage="loader",
            status="error",
            duration_ms=round((time.perf_counter() - start) * 1000, 3),
            tags={"file": filepath, "source_ext": ext},
            values={"parse_success": False, "error_type": e.__class__.__name__},
        )
        raise
