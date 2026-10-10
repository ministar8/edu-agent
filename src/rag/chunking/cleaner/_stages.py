"""自动拆分自 cleaner.py（行为等价）。"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from langchain_core.documents import Document

from rag.chunking.cleaner._exam import (
    _clean_markdown_text,
    _is_exam_markdown_source,
    _normalize_exam_question_headings,
    _remove_exam_web_noise,
)
from rag.chunking.cleaner._log import logger
from rag.chunking.cleaner._pdf import _clean_pdf_text, _dedupe_pdf_edges, _pdf_source_key
from rag.chunking.cleaner._text import _clean_plain_text, _get_source_ext, _get_source_path
from rag.common.metrics import metrics
from rag.common.synonyms import normalize_synonyms

if TYPE_CHECKING:
    from tools.anomaly import AnomalyRecord


def _dispatch_clean(
    doc: Document,
    ext: str,
    source_path: str,
    repeated_edges: set[str],
) -> None:
    """按扩展名分派单文档清洗：.md / .pdf / 其它（三分支顺序与条件是行为的一部分）"""
    if ext == ".md":
        doc.page_content = _clean_markdown_text(doc.page_content)
        if _is_exam_markdown_source(source_path):
            doc.page_content, removed_noise = _remove_exam_web_noise(doc.page_content)
            doc.page_content = _normalize_exam_question_headings(doc.page_content)
            if removed_noise:
                doc.metadata["exam_web_noise_removed_chars"] = removed_noise
    elif ext == ".pdf":
        doc.page_content = _clean_pdf_text(doc.page_content, repeated_edges)
    else:
        doc.page_content = _clean_plain_text(doc.page_content)


def _clean_by_extension(documents: list[Document]) -> tuple[list[Document], int]:
    """阶段0：按扩展名分派清洗，丢弃过短文档并标记 cleaned_ratio

    Returns:
        (清洗后保留的文档列表, 被丢弃的文档数)
    """
    cleaned: list[Document] = []
    dropped_docs = 0
    pdf_edge_map = _dedupe_pdf_edges([doc for doc in documents if _get_source_ext(doc) == ".pdf"])
    for doc in documents:
        original_len = len(doc.page_content)
        ext = _get_source_ext(doc)
        source_path = _get_source_path(doc)
        repeated_edges = pdf_edge_map.get(_pdf_source_key(doc), set()) if ext == ".pdf" else set()
        _dispatch_clean(doc, ext, source_path, repeated_edges)

        if len(doc.page_content.strip()) < 10:
            dropped_docs += 1
            continue

        if len(doc.page_content) < original_len * 0.5:
            doc.metadata["cleaned_ratio"] = f"{1 - len(doc.page_content) / original_len:.0%}"

        cleaned.append(doc)
    return cleaned, dropped_docs


def _run_normalization(cleaned: list[Document]) -> tuple[list[Document], list[dict]]:
    """阶段1：数据转换与标准化（清洗后、填充前执行）"""
    from tools.normalizer import normalize_documents

    cleaned, norm_log = normalize_documents(cleaned)
    if norm_log:
        logger.info("标准化: %d 篇文档已转换", len(norm_log))
    return cleaned, norm_log


def _run_synonym_normalize(cleaned: list[Document]) -> list[Document]:
    """阶段2：同义词归一（标准化后、填充前执行）"""
    # ★ 跨侧契约的文档侧：一旦改写原文，query 侧做字面匹配的消费者（BM25 的 `$contains`、
    #   cross-encoder reranker）就必须同样归一，否则错配。开关默认开（保持既有行为），
    #   关掉即「文档保持原文」，用于与 query 侧归一做对照；实测代价见 settings 同名开关的注释。
    from core.settings import settings

    synonym_total = 0
    if settings.INGEST_SYNONYM_NORMALIZE:
        for doc in cleaned:
            doc.page_content, replaced_count = normalize_synonyms(doc.page_content)
            synonym_total += replaced_count
    if synonym_total:
        logger.info("同义词归一: %d 处替换", synonym_total)
    return cleaned


def _run_imputation(cleaned: list[Document]) -> tuple[list[Document], list[dict]]:
    """阶段3：缺失值填充（标准化后、去重前执行）"""
    from tools.imputer import impute_documents

    cleaned, impute_log = impute_documents(cleaned)
    if impute_log:
        logger.info("缺失值填充: %d 条记录", len(impute_log))
    return cleaned, impute_log


def _detect_content_anomalies_stage(
    cleaned: list[Document],
) -> tuple[list[Document], list[AnomalyRecord], int]:
    """阶段4：异常检测·内容层（去重前，处理乱码型异常）"""
    from tools.anomaly import detect_content_anomalies

    cleaned, content_anomaly_records = detect_content_anomalies(cleaned)
    # 过滤全乱码文档（不入库）
    cleaned = [doc for doc in cleaned if doc.metadata.get("content_status") != "full_garbage"]
    content_anomaly_count = sum(1 for r in content_anomaly_records if r.actions_taken)
    if content_anomaly_count:
        logger.info("异常检测[阶段1/内容层]: %d 篇文档存在异常", content_anomaly_count)
    return cleaned, content_anomaly_records, content_anomaly_count


def _run_dedup(
    cleaned: list[Document],
    *,
    dedup: bool,
    fuzzy_dedup: bool,
    fuzzy_threshold: float,
) -> tuple[list[Document], list[dict]]:
    """阶段5：去重（内容异常处理后执行，基于清洗后的内容）"""
    if not (dedup or fuzzy_dedup):
        return cleaned, []

    from tools.dedup import dedup_documents

    cleaned, dup_records = dedup_documents(
        cleaned,
        exact=dedup,
        fuzzy=fuzzy_dedup,
        fuzzy_threshold=fuzzy_threshold,
    )
    if dup_records:
        logger.info("去重结果: 移除 %d 条重复记录", len(dup_records))
    return cleaned, dup_records


def _detect_statistical_anomalies_stage(
    cleaned: list[Document],
    content_anomaly_records: list[AnomalyRecord],
) -> tuple[list[Document], int]:
    """阶段6：异常检测·统计层（去重后，统计指标更准确）"""
    from tools.anomaly import detect_statistical_anomalies

    cleaned, anomaly_records = detect_statistical_anomalies(
        cleaned, prev_records=content_anomaly_records
    )
    stat_anomaly_count = sum(1 for r in anomaly_records if r.actions_taken)
    if stat_anomaly_count:
        logger.info("异常检测[阶段2/统计层]: %d 篇文档存在异常", stat_anomaly_count)
    return cleaned, stat_anomaly_count


def clean_documents(
    documents: list[Document],
    *,
    dedup: bool = True,
    fuzzy_dedup: bool = True,
    fuzzy_threshold: float = 0.9,
) -> list[Document]:
    """清洗文档集合

    Args:
        documents: 待清洗文档列表
        dedup: 是否启用精确去重（MD5）
        fuzzy_dedup: 是否启用模糊去重（MinHash + LSH）
        fuzzy_threshold: 模糊去重相似度阈值，默认 0.9

    Returns:
        清洗后文档列表
    """
    start = time.perf_counter()
    original_total_chars = sum(len(doc.page_content or "") for doc in documents)
    cleaned, dropped_docs = _clean_by_extension(documents)

    cleaned, norm_log = _run_normalization(cleaned)

    cleaned = _run_synonym_normalize(cleaned)

    cleaned, impute_log = _run_imputation(cleaned)

    cleaned, content_anomaly_records, content_anomaly_count = _detect_content_anomalies_stage(
        cleaned
    )

    cleaned, dup_records = _run_dedup(
        cleaned, dedup=dedup, fuzzy_dedup=fuzzy_dedup, fuzzy_threshold=fuzzy_threshold
    )

    cleaned, stat_anomaly_count = _detect_statistical_anomalies_stage(
        cleaned, content_anomaly_records
    )

    cleaned_total_chars = sum(len(doc.page_content or "") for doc in cleaned)
    retention_ratio = cleaned_total_chars / original_total_chars if original_total_chars else 0.0
    metrics.emit(
        event="clean_documents",
        stage="cleaner",
        duration_ms=round((time.perf_counter() - start) * 1000, 3),
        values={
            "input_docs": len(documents),
            "output_docs": len(cleaned),
            "dropped_docs": dropped_docs,
            "normalized_docs": len(norm_log),
            "imputed_docs": len(impute_log),
            "content_anomaly_docs": content_anomaly_count,
            "stat_anomaly_docs": stat_anomaly_count,
            "dedup_removed": len(dup_records),
            "retention_ratio": round(retention_ratio, 6),
            "original_total_chars": original_total_chars,
            "cleaned_total_chars": cleaned_total_chars,
        },
    )
    return cleaned
