from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

MIN_CHUNK_LENGTH = 20


def split_documents(
    documents: list[Document],
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
) -> list[Document]:
    """将文档切分为chunks，过滤过短片段"""
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
    )

    chunks = text_splitter.split_documents(documents)

    # 过滤过短 chunk，生成溯源 ID
    valid_chunks: list[Document] = []
    for chunk in chunks:
        if len(chunk.page_content.strip()) < MIN_CHUNK_LENGTH:
            continue
        source = chunk.metadata.get("source_file", "unknown")
        chunk.metadata["chunk_id"] = f"{source}_{len(valid_chunks)}"
        valid_chunks.append(chunk)

    return valid_chunks
