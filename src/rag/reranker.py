"""Reranker 重排序模块

使用本地 TEI bge-reranker-v2-m3 对向量检索结果进行精排。
通过 RERANK_ENABLED 开关控制。

``USE_FAKE_RERANK=true`` 时改用确定性本地打分（见 `_fake_rerank`），
让无 TEI 的门禁 / 单测也能覆盖重排链路。
"""

from __future__ import annotations

import hashlib
import logging
import math
import re
import time
from typing import Any

import httpx
from langchain_core.documents import Document

from core.cache import BoundedCache
from core.settings import settings

logger = logging.getLogger(__name__)

# 文档截断长度：截断前段语义即可
_MAX_DOC_CHARS = 2000
_RERANK_CACHE_TTL = 300
_RERANK_CACHE_MAX = 128
_rerank_cache: BoundedCache[str, list[Document]] = BoundedCache(
    max_size=_RERANK_CACHE_MAX, ttl=_RERANK_CACHE_TTL, name="rerank"
)


def _copy_ranked(docs: list[Document]) -> list[Document]:
    """缓存命中时返回浅拷贝：新 list + 每篇 Document 复制一份 metadata。

    缓存中的 Document 会被下游写入 metadata（窗口展开、噪声降级等），直接返回原对象
    会让这些写入污染缓存。
    """
    return [Document(page_content=d.page_content, metadata=dict(d.metadata)) for d in docs]


def _document_cache_id(doc: Document) -> str:
    metadata = doc.metadata or {}
    return str(
        metadata.get("content_hash")
        or metadata.get("chunk_id")
        or f"{metadata.get('source') or metadata.get('source_file') or ''}:{metadata.get('chunk_index') or ''}:{doc.page_content[:120]}"
    )


def _rerank_cache_key(query: str, documents: list[Document], top_k: int) -> str:
    raw = "\n".join([query, str(top_k), *[_document_cache_id(doc) for doc in documents]])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ── 假重排（测试 / 门禁用，由 settings.USE_FAKE_RERANK 启用）──────


def _bigram_counts(text: str) -> dict[str, int]:
    """字符 bigram 计数，与 `HashingEmbeddings` 同一套分词口径。"""
    normalized = "".join(str(text).lower().split())
    if not normalized:
        return {}
    tokens = [normalized[i : i + 2] for i in range(len(normalized) - 1)]
    tokens.append(normalized)  # 整串参与，保证极短文本也有区分度
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return counts


def _bigram_cosine(a: dict[str, int], b: dict[str, int]) -> float:
    if not a or not b:
        return 0.0
    common = a.keys() & b.keys()
    if not common:
        return 0.0
    dot = sum(a[key] * b[key] for key in common)
    norm_a = math.sqrt(sum(value * value for value in a.values()))
    norm_b = math.sqrt(sum(value * value for value in b.values()))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _fake_rerank(query: str, texts: list[str], top_n: int) -> list[dict[str, Any]]:
    """确定性本地打分，替代 TEI ``/rerank``。返回与 TEI 同款的结构。

    **与 `HashingEmbeddings` 同一哲学**：只保留**词汇重叠**信号（字符 bigram 余弦），
    因此足以验证重排链路的**接线** —— 候选顺序是否真被改写、``top_n`` 是否被遵守、
    ``rerank_score`` 是否被写入、阈值是否照常过滤 —— 但**没有语义泛化能力**
    （同义不同词不会相似）。

    **确定性来自纯计算**：不碰网络、也不用内置 ``hash()``（后者受 PYTHONHASHSEED
    影响，跨进程结果不一致）。这正是原来「必须打真实 TEI 才能跑重排」做不到的事。

    ⚠️ **分数分布与 bge-reranker 不同**：真实模型分数经 sigmoid 集中在 0.5~0.99，
    而这里的余弦对「短查询 vs 长文档」天然偏低。所以本路由上绝对阈值
    （``RERANK_ABSOLUTE_MIN_SCORE``）的行为**不代表生产** —— 该路由的指标
    只能与**同环境**基线比，不能拿去和生产数字对照。
    """
    query_vec = _bigram_counts(query)
    scored = [
        (index, _bigram_cosine(query_vec, _bigram_counts(text))) for index, text in enumerate(texts)
    ]
    # 同分时按原顺序，保证排序完全确定
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [{"index": index, "score": score} for index, score in scored[:top_n]]


def rerank(
    query: str,
    documents: list[Document],
    top_k: int = 5,
    lightweight: bool = False,
) -> list[Document]:
    """对检索结果进行重排序

    Args:
        query: 用户查询
        documents: 候选文档列表
        top_k: 返回前 top_k 个结果

    Returns:
        按 relevance_score 降序排列的文档列表（metadata 含 rerank_score）
    """
    if not documents:
        return []

    if not settings.RERANK_ENABLED:
        return documents[:top_k]

    start = time.perf_counter()

    # ── 预筛选：按可用分数保留 top N 候选 ──
    # lightweight（L2）：候选池 10，省延迟；deep（L3）：候选池 30，高精度
    _RERANK_MAX_CANDIDATES = 10 if lightweight else 30
    original_count = len(documents)
    if len(documents) > _RERANK_MAX_CANDIDATES:

        def _sort_score(d: Document) -> float:
            rs = d.metadata.get("recall_score")
            if rs is not None and float(rs) > 0:
                return float(rs)
            rrs = d.metadata.get("rerank_score")
            if rrs is not None and float(rrs) > 0:
                return float(rrs)
            return 0.0

        documents = sorted(documents, key=_sort_score, reverse=True)[:_RERANK_MAX_CANDIDATES]
        logger.debug("Rerank pre-filter: %d → %d", original_count, len(documents))

    cache_key = _rerank_cache_key(query, documents, top_k)
    cached_docs = _rerank_cache.get(cache_key)
    if cached_docs is not None:
        logger.debug("Rerank cache hit q=%s docs=%d top_k=%d", query[:30], len(documents), top_k)
        return _copy_ranked(cached_docs)

    # ── 去噪：去掉 heading_path 前缀（如 "[进程管理] > [PV操作]\n"） ──
    # heading_path 已存在于 metadata (section.path) 和 LLM 上下文 (format_text_evidence)，
    # 保留在 page_content 中会干扰 reranker 对正文相关性的判断。
    _HEADING_PATH_RE = re.compile(r"^(?:\[[^\]]*\]\s*(?:>\s*)*)+\n")
    texts = [_HEADING_PATH_RE.sub("", doc.page_content)[:_MAX_DOC_CHARS] for doc in documents]

    # ── 打分：默认打本地 TEI /rerank；USE_FAKE_RERANK 时走确定性本地实现 ──
    top_n = min(top_k, len(documents))
    if settings.USE_FAKE_RERANK:
        results = _fake_rerank(query, texts, top_n=top_n)
    else:
        api_url = f"{settings.RERANK_LOCAL_URL}/rerank"
        payload = {"query": query, "texts": texts, "top_n": top_n}
        try:
            with httpx.Client(timeout=settings.RERANK_TIMEOUT) as client:
                resp = client.post(api_url, json=payload)
                resp.raise_for_status()
            results = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("Rerank HTTP error: %s %s", e.response.status_code, e.response.text[:200])
            return documents[:top_k]
        except Exception as e:
            logger.error("Rerank call failed: %s", e, exc_info=True)
            return documents[:top_k]

    if not results:
        logger.warning("Rerank returned empty results, using original order")
        return documents[:top_k]

    # TEI 返回格式: [{"index": 0, "score": 0.98, "text": "..."}, ...]
    result: list[Document] = []
    for item in results:
        idx = item.get("index", -1)
        score = item.get("score", 0.0)
        if 0 <= idx < len(documents):
            doc = documents[idx]
            doc.metadata["rerank_score"] = round(float(score), 4)
            doc.metadata["rerank_method"] = "bge-reranker-v2-m3"
            result.append(doc)

    # 补充未排序的文档
    ranked_indices = {item.get("index", -1) for item in results}
    if len(result) < top_k:
        for i, doc in enumerate(documents):
            if i not in ranked_indices and len(result) < top_k:
                doc.metadata["rerank_score"] = 0.0
                doc.metadata["rerank_method"] = "bge-reranker-v2-m3-fallback"
                result.append(doc)

    # 补足后仍可能超过 top_k（TEI 不遵守 top_n 时）—— 截断以保证契约成立
    result = result[:top_k]

    elapsed_ms = (time.perf_counter() - start) * 1000
    top_score = result[0].metadata.get("rerank_score", 0) if result else 0
    logger.debug(
        "Rerank q=%s in=%d out=%d top=%.4f %.1fms lw=%s",
        query[:30],
        len(documents),
        len(result),
        top_score,
        elapsed_ms,
        lightweight,
    )

    # 存**副本**再返回：`result` 会原样交给调用方，而下游会往 metadata 里写东西
    # （窗口展开、噪声降级等）。若把同一对象放进缓存，**第一个调用方的写入会污染
    # 后续所有命中缓存的调用** —— 那样 `_copy_ranked` 只防住了一半（读时拷贝），
    # 而污染是从写时进去的。
    _rerank_cache.set(cache_key, _copy_ranked(result))

    return result
