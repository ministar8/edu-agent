"""自动拆分自 splitter.py（行为等价）。"""

from __future__ import annotations

MIN_CHUNK_LENGTH = 80


# ── Adaptive chunk_size 映射 ──
# 根据 content_type 选择 chunk_size，0 表示不拆分（整块保留）
_ADAPTIVE_CHUNK_SIZE: dict[str, int] = {
    "section": 800,
    "text": 800,
    "list": 0,  # 不拆
    "code_mixed": 400,
    "exercise": 600,
    "answer": 600,
    "merged_qa": 0,  # 不拆（题+答原子单元）
    "table": 0,  # 不拆（表格原子保留）
    "formula": 0,  # 不拆（公式块原子保留）
}

_ADAPTIVE_CHUNK_OVERLAP: dict[str, int] = {
    "section": 150,
    "text": 150,
    "list": 0,
    "code_mixed": 100,
    "exercise": 100,
    "answer": 100,
    "merged_qa": 0,
    "table": 0,
    "formula": 0,
}


# 硬上限：任何 chunk 不超过此长度（超长单元按句子拆分）
_CHUNK_HARD_LIMIT = 1600

# QA 软上限：只用于多题合并时的题目边界分组，不拆单题
_QA_CHUNK_SOFT_LIMIT = 3000

# 过短阈值：低于此长度的 chunk 尝试与邻居合并
_CHUNK_MIN_EFFECTIVE = 80

# 散文单元上限：超过它才按句子拆分
_PROSE_UNIT_MAX_CHARS = 1200

_PARENT_WINDOW_CHAR_BUDGET = 4200


def _resolve_chunk_params(content_type: str) -> tuple[int, int]:
    """根据内容类型返回 (chunk_size, chunk_overlap)"""
    size = _ADAPTIVE_CHUNK_SIZE.get(content_type, 800)
    overlap = _ADAPTIVE_CHUNK_OVERLAP.get(content_type, 150)
    return size, overlap
