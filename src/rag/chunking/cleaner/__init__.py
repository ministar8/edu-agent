"""文本清洗（clean_documents）—— 由原单文件拆分为子包，对外 API 不变。"""

from rag.chunking.cleaner._stages import clean_documents

__all__ = ["clean_documents"]
