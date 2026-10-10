"""离线切分（split_documents）—— 由原单文件拆分为子包，对外 API 不变。"""

from rag.chunking.splitter._core import split_documents
from rag.chunking.splitter._params import (
    _CHUNK_HARD_LIMIT,
    MIN_CHUNK_LENGTH,
    _resolve_chunk_params,
)

__all__ = ["split_documents", "MIN_CHUNK_LENGTH", "_CHUNK_HARD_LIMIT", "_resolve_chunk_params"]
