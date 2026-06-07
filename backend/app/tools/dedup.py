"""文档去重模块

提供两级去重能力：
1. 精确去重 (Exact Dedup) — MD5 哈希，删除完全相同的记录
2. 模糊去重 (Fuzzy Dedup)  — MinHash + LSH，删除高度相似记录（相似度>90%）

集成位置：清洗管道 clean_documents() 中，分块前执行。
"""

from __future__ import annotations

import hashlib
import logging
import re

from langchain_core.documents import Document

logger = logging.getLogger(__name__)


def _doc_source(doc: Document) -> str:
    """提取文档的 source_path 或 source_file 标识"""
    return str(doc.metadata.get("source_path") or doc.metadata.get("source_file") or "unknown")


# ── 内存与性能控制 ──────────────────────────────────

# LSH 单批最大文档数（超出则分批处理，降低峰值内存）
_LSH_BATCH_SIZE = 10_000

# MinHash 签名估算内存：每个签名约 num_perm * 4 bytes + 开销
_MINHASH_MEM_BYTES = 128 * 4 + 200  # ~712 bytes/doc (num_perm=128)

# 内存安全阈值：可用内存低于此值时降级到暴力比对
_MEM_SAFETY_MB = 200


def _available_memory_mb() -> float:
    """获取系统可用内存（MB）"""
    try:
        import psutil
        return psutil.virtual_memory().available / (1024 * 1024)
    except ImportError:
        # 无 psutil 时假设内存充足
        return 1024.0


def _estimate_lsh_memory(n_docs: int, num_perm: int = 128) -> float:
    """估算 LSH 索引所需内存（MB）

    MinHash 签名: num_perm * 4 bytes/doc
    LSH 哈希表: 约 2x 签名内存
    开销系数: 1.5x
    """
    sig_mem = n_docs * num_perm * 4
    total = sig_mem * 2 * 1.5
    return total / (1024 * 1024)

# ── 精确去重 ────────────────────────────────────────

def _md5_hash(text: str) -> str:
    """计算文本的 MD5 哈希"""
    return hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()


def exact_dedup(documents: list[Document]) -> tuple[list[Document], list[dict]]:
    """精确去重：通过 MD5 哈希识别并删除完全相同的记录

    保留首次出现的文档，后续完全相同的文档被标记为重复并移除。

    Args:
        documents: 待去重文档列表

    Returns:
        (去重后文档列表, 重复记录列表)
        重复记录格式: [{"hash": str, "source": str, "duplicate_of": str}]
    """
    seen_hashes: dict[str, str] = {}  # hash -> first source
    unique_docs: list[Document] = []
    duplicates: list[dict] = []

    for doc in documents:
        text = doc.page_content.strip() if doc.page_content else ""
        if not text:
            continue

        content_hash = _md5_hash(text)
        source = str(doc.metadata.get("source_path") or doc.metadata.get("source_file") or "unknown")

        if content_hash in seen_hashes:
            duplicates.append({
                "hash": content_hash,
                "source": source,
                "duplicate_of": seen_hashes[content_hash],
                "type": "exact",
                "similarity": 1.0,
            })
            logger.debug("Exact dedup: '%s' is duplicate of '%s'", source, seen_hashes[content_hash])
        else:
            seen_hashes[content_hash] = source
            doc.metadata["content_hash_md5"] = content_hash
            unique_docs.append(doc)

    if duplicates:
        logger.info(
            "Exact dedup: removed %d/%d duplicates",
            len(duplicates), len(documents),
        )

    return unique_docs, duplicates


# ── 模糊去重 ────────────────────────────────────────

# 默认 MinHash 参数
_DEFAULT_NUM_PERM = 128       # 排列数（越高越精确，越慢）
_DEFAULT_THRESHOLD = 0.9      # 相似度阈值
_DEFAULT_NGRAM = 3            # n-gram 长度


def _shingle_ngrams(text: str, n: int = _DEFAULT_NGRAM) -> set[str]:
    """将文本切分为 n-gram 集合

    中文按字符切分，英文按单词切分。
    """
    # 预处理：去除多余空白
    text = re.sub(r"\s+", " ", text.strip())
    if len(text) < n:
        return {text} if text else set()

    # 混合策略：中文按字符 n-gram，英文按词 n-gram
    ngrams: set[str] = set()

    # 字符级 n-gram（覆盖中文和混合文本）
    for i in range(len(text) - n + 1):
        ngrams.add(text[i:i + n])

    return ngrams


def _compute_minhash(ngrams: set[str], num_perm: int = _DEFAULT_NUM_PERM) -> object:
    """计算 MinHash 签名

    优先使用 datasketch 库，降级为内置实现。
    """
    try:
        from datasketch import MinHash
        mh = MinHash(num_perm=num_perm)
        for gram in ngrams:
            mh.update(gram.encode("utf-8"))
        return mh
    except ImportError:
        return _SimpleMinHash(ngrams, num_perm)


class _SimpleMinHash:
    """内置 MinHash 简易实现（datasketch 不可用时的降级方案）

    使用多个哈希函数模拟 MinHash 签名。
    """

    def __init__(self, ngrams: set[str], num_perm: int = 128):
        self._signatures: list[int] = []
        for i in range(num_perm):
            min_hash = float("inf")
            for gram in ngrams:
                # 每个排列用不同的种子
                h = hash(f"{i}:{gram}") & 0xFFFFFFFF
                if h < min_hash:
                    min_hash = h
            self._signatures.append(min_hash)

    def jaccard(self, other: "_SimpleMinHash") -> float:
        """估算 Jaccard 相似度"""
        if len(self._signatures) != len(other._signatures):
            return 0.0
        matches = sum(1 for a, b in zip(self._signatures, other._signatures) if a == b)
        return matches / len(self._signatures)


def fuzzy_dedup(
    documents: list[Document],
    similarity_threshold: float = _DEFAULT_THRESHOLD,
    num_perm: int = _DEFAULT_NUM_PERM,
    ngram_size: int = _DEFAULT_NGRAM,
) -> tuple[list[Document], list[dict]]:
    """模糊去重：使用 MinHash + LSH 识别高度相似记录

    性能优化策略：
    1. 内存估算：根据文档数量估算 LSH 内存，超出可用内存时降级
    2. 分批处理：文档数 > _LSH_BATCH_SIZE 时分批构建 LSH，降低峰值内存
    3. 自适应 num_perm：文档数 >50k 时自动降低排列数（128→64），减少内存和计算量
    4. 降级路径：datasketch 不可用 → 暴力比对；内存不足 → 分批暴力比对

    Args:
        documents: 待去重文档列表
        similarity_threshold: 相似度阈值，默认 0.9 (90%)
        num_perm: MinHash 排列数，默认 128
        ngram_size: n-gram 长度，默认 3

    Returns:
        (去重后文档列表, 重复记录列表)
    """
    n_docs = len(documents)
    if n_docs <= 1:
        return documents, []

    # ── 自适应参数调整 ──
    effective_perm = num_perm
    if n_docs > 50_000:
        effective_perm = max(64, num_perm // 2)
        logger.info(
            "Fuzzy dedup: large dataset (%d docs), reducing num_perm %d→%d",
            n_docs, num_perm, effective_perm,
        )

    # ── 内存检查 ──
    est_mem = _estimate_lsh_memory(n_docs, effective_perm)
    avail_mem = _available_memory_mb()
    use_lsh = est_mem < avail_mem - _MEM_SAFETY_MB

    if not use_lsh:
        logger.warning(
            "Fuzzy dedup: LSH memory estimate %.0fMB exceeds available %.0fMB, "
            "degrading to batch brute-force",
            est_mem, avail_mem,
        )

    # 1. 计算所有文档的 MinHash 签名
    minhashes: list[object] = []
    for doc in documents:
        text = doc.page_content.strip() if doc.page_content else ""
        ngrams = _shingle_ngrams(text, n=ngram_size)
        if ngrams:
            minhashes.append(_compute_minhash(ngrams, effective_perm))
        else:
            minhashes.append(None)

    duplicate_indices: set[int] = set()
    duplicates: list[dict] = []

    # 2a. LSH 路径（datasketch 可用 + 内存充足）
    if use_lsh:
        try:
            from datasketch import MinHashLSH

            if n_docs <= _LSH_BATCH_SIZE:
                # 单批处理
                _lsh_batch(
                    documents, minhashes, duplicate_indices, duplicates,
                    similarity_threshold, effective_perm,
                )
            else:
                # 分批处理：每批构建独立 LSH，跨批比对
                _lsh_batched(
                    documents, minhashes, duplicate_indices, duplicates,
                    similarity_threshold, effective_perm,
                )

        except ImportError:
            use_lsh = False

    # 2b. 暴力比对路径（降级）
    if not use_lsh:
        _brute_force_batched(
            documents, minhashes, duplicate_indices, duplicates,
            similarity_threshold,
        )

    # 3. 构建去重后文档列表
    unique_docs = [doc for i, doc in enumerate(documents) if i not in duplicate_indices]

    if duplicates:
        logger.info(
            "Fuzzy dedup: removed %d near-duplicates (threshold=%.0f%%, perm=%d, lsh=%s)",
            len(duplicates), similarity_threshold * 100, effective_perm, use_lsh,
        )

    return unique_docs, duplicates


def _lsh_batch(
    documents: list[Document],
    minhashes: list[object],
    duplicate_indices: set[int],
    duplicates: list[dict],
    threshold: float,
    num_perm: int,
) -> None:
    """单批 LSH 去重（文档数 ≤ _LSH_BATCH_SIZE）"""
    from datasketch import MinHashLSH

    lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)

    for i, mh in enumerate(minhashes):
        if mh is not None:
            lsh.insert(f"doc_{i}", mh)

    for i, mh in enumerate(minhashes):
        if mh is None or i in duplicate_indices:
            continue

        similar_ids = lsh.query(mh)
        similar_ids = [sid for sid in similar_ids if sid != f"doc_{i}"]

        for sid in similar_ids:
            j = int(sid.split("_")[1])
            if j in duplicate_indices or j <= i:
                continue

            sim = minhashes[i].jaccard(minhashes[j]) if minhashes[j] is not None else 0.0

            if sim >= threshold:
                duplicate_indices.add(j)
                source_j = _doc_source(documents[j])
                source_i = _doc_source(documents[i])
                duplicates.append({
                    "source": source_j,
                    "duplicate_of": source_i,
                    "similarity": round(sim, 4),
                    "type": "fuzzy",
                })


def _lsh_batched(
    documents: list[Document],
    minhashes: list[object],
    duplicate_indices: set[int],
    duplicates: list[dict],
    threshold: float,
    num_perm: int,
) -> None:
    """分批 LSH 去重（文档数 > _LSH_BATCH_SIZE）

    策略：
    1. 将文档按 _LSH_BATCH_SIZE 分批
    2. 每批构建独立 LSH 索引
    3. 批内去重 + 跨批比对（用前批的 MinHash 查询后批的 LSH）
    4. 每批处理完后释放 LSH 对象，降低峰值内存
    """
    from datasketch import MinHashLSH

    n_docs = len(documents)
    batch_size = _LSH_BATCH_SIZE

    for batch_start in range(0, n_docs, batch_size):
        batch_end = min(batch_start + batch_size, n_docs)
        batch_indices = range(batch_start, batch_end)

        # 构建当前批的 LSH
        lsh = MinHashLSH(threshold=threshold, num_perm=num_perm)
        for i in batch_indices:
            if minhashes[i] is not None and i not in duplicate_indices:
                lsh.insert(f"doc_{i}", minhashes[i])

        # 批内去重
        for i in batch_indices:
            if minhashes[i] is None or i in duplicate_indices:
                continue

            similar_ids = lsh.query(minhashes[i])
            similar_ids = [sid for sid in similar_ids if sid != f"doc_{i}"]

            for sid in similar_ids:
                j = int(sid.split("_")[1])
                if j in duplicate_indices or j <= i:
                    continue

                sim = minhashes[i].jaccard(minhashes[j]) if minhashes[j] is not None else 0.0
                if sim >= threshold:
                    duplicate_indices.add(j)
                    source_j = _doc_source(documents[j])
                    source_i = _doc_source(documents[i])
                    duplicates.append({
                        "source": source_j,
                        "duplicate_of": source_i,
                        "similarity": round(sim, 4),
                        "type": "fuzzy",
                    })

        # 跨批比对：用之前批的 MinHash 查询当前批的 LSH
        if batch_start > 0:
            prev_indices = range(0, batch_start)
            for i in prev_indices:
                if minhashes[i] is None or i in duplicate_indices:
                    continue

                similar_ids = lsh.query(minhashes[i])
                for sid in similar_ids:
                    j = int(sid.split("_")[1])
                    if j in duplicate_indices or j < batch_start:
                        continue

                    sim = minhashes[i].jaccard(minhashes[j]) if minhashes[j] is not None else 0.0
                    if sim >= threshold:
                        duplicate_indices.add(j)
                        source_j = _doc_source(documents[j])
                        source_i = _doc_source(documents[i])
                        duplicates.append({
                            "source": source_j,
                            "duplicate_of": source_i,
                            "similarity": round(sim, 4),
                            "type": "fuzzy",
                        })

        # 释放 LSH 对象
        del lsh
        logger.debug(
            "Fuzzy dedup: batch %d-%d processed, %d duplicates found so far",
            batch_start, batch_end - 1, len(duplicates),
        )


def _brute_force_batched(
    documents: list[Document],
    minhashes: list[object],
    duplicate_indices: set[int],
    duplicates: list[dict],
    threshold: float,
) -> None:
    """暴力比对去重（降级路径，分批减少内存压力）

    策略：将文档按批次两两比对，跳过已标记为重复的文档。
    """
    n_docs = len(documents)
    batch_size = _LSH_BATCH_SIZE

    for batch_start in range(0, n_docs, batch_size):
        batch_end = min(batch_start + batch_size, n_docs)

        for i in range(batch_start, batch_end):
            if minhashes[i] is None or i in duplicate_indices:
                continue

            # 比对范围：当前批内 + 与之前所有文档
            compare_start = max(i + 1, batch_start)
            for j in range(compare_start, n_docs):
                if minhashes[j] is None or j in duplicate_indices:
                    continue

                sim = minhashes[i].jaccard(minhashes[j])
                if sim >= threshold:
                    duplicate_indices.add(j)
                    source_j = _doc_source(documents[j])
                    source_i = _doc_source(documents[i])
                    duplicates.append({
                        "source": source_j,
                        "duplicate_of": source_i,
                        "similarity": round(sim, 4),
                        "type": "fuzzy",
                    })


# ── 组合去重 ────────────────────────────────────────

def dedup_documents(
    documents: list[Document],
    exact: bool = True,
    fuzzy: bool = True,
    fuzzy_threshold: float = _DEFAULT_THRESHOLD,
    num_perm: int = _DEFAULT_NUM_PERM,
) -> tuple[list[Document], list[dict]]:
    """组合去重：先精确去重，再模糊去重

    Args:
        documents: 待去重文档列表
        exact: 是否启用精确去重
        fuzzy: 是否启用模糊去重
        fuzzy_threshold: 模糊去重相似度阈值
        num_perm: MinHash 排列数

    Returns:
        (去重后文档列表, 所有重复记录列表)
    """
    all_duplicates: list[dict] = []

    # 第一级：精确去重
    if exact:
        documents, exact_dups = exact_dedup(documents)
        all_duplicates.extend(exact_dups)

    # 第二级：模糊去重
    if fuzzy:
        documents, fuzzy_dups = fuzzy_dedup(
            documents,
            similarity_threshold=fuzzy_threshold,
            num_perm=num_perm,
        )
        all_duplicates.extend(fuzzy_dups)

    if all_duplicates:
        logger.info(
            "Dedup total: removed %d duplicates (%d exact + %d fuzzy) from %d docs",
            len(all_duplicates),
            sum(1 for d in all_duplicates if d["type"] == "exact"),
            sum(1 for d in all_duplicates if d["type"] == "fuzzy"),
            len(documents) + len(all_duplicates),
        )

    return documents, all_duplicates
