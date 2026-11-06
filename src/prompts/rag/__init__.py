"""RAG 层 Prompt 统一导出。

检索链路的模板集中在 `retrieval.py`：HYDE / 意图分类 / 查询拆解。
"""

from prompts.rag.retrieval import (
    CLASSIFY_PROMPT,
    DECOMPOSE_PROMPT,
    HYDE_PROMPT,
)

__all__ = [
    "CLASSIFY_PROMPT",
    "DECOMPOSE_PROMPT",
    "HYDE_PROMPT",
]
