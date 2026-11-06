"""缺失值填充主流程：单文档三级填充 + 集合级并行/串行调度。"""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from langchain_core.documents import Document

from ._constants import _LOW_CONFIDENCE_PREFIX, _PLACEHOLDER_RE, _UNCLOSED_FENCE_RE
from ._heading import (
    _heading_cache,
    _impute_category,
    _impute_heading,
    _impute_heading_path,
    get_heading_cache_stats,
)
from ._resources import _resource_guard
from ._segmentation import _impute_section_headings

logger = logging.getLogger(__name__)


# ── 内容层缺失值 ────────────────────────────────────


def _detect_content_status(doc: Document) -> str:
    """检测内容状态

    Returns:
        "empty" | "placeholder" | "truncated" | "normal"
    """
    text = doc.page_content.strip() if doc.page_content else ""

    if not text or len(text) < 10:
        return "empty"

    # 占位符检测
    if _PLACEHOLDER_RE.search(text):
        return "placeholder"

    # 截断检测：未闭合代码围栏 + 未闭合括号
    fence_matches = _UNCLOSED_FENCE_RE.findall(text)
    if fence_matches and len(fence_matches) % 2 != 0:
        return "truncated"

    # 未闭合中文/英文括号（开括号多于闭括号 → 截断）
    open_paren = len(re.findall(r"[(（]", text))
    close_paren = len(re.findall(r"[)）]", text))
    if open_paren != close_paren and open_paren > close_paren:
        return "truncated"

    open_bracket = len(re.findall(r"[\[{【]", text))
    close_bracket = len(re.findall(r"[\]}】]", text))
    if open_bracket != close_bracket and open_bracket > close_bracket:
        return "truncated"

    return "normal"


# ── 主函数 ──────────────────────────────────────────


def _impute_content_layer(doc: Document, source: str) -> tuple[list[dict], bool]:
    """内容层：标记空/占位符/截断

    Returns:
        (填充日志, 是否为空文档（调用方应丢弃）)
    """
    status = _detect_content_status(doc)
    if status == "normal":
        doc.metadata["content_status"] = "normal"
        return [], False

    doc.metadata["content_status"] = status
    if status == "empty":
        return (
            [
                {
                    "field": "content_status",
                    "method": "mark_empty",
                    "source": source,
                    "value": "empty",
                }
            ],
            True,
        )

    log: list[dict] = []
    if status == "placeholder":
        doc.metadata["has_placeholder"] = True
        log.append(
            {"field": "has_placeholder", "method": "detect", "source": source, "value": True}
        )
    if status == "truncated":
        doc.metadata["truncated"] = True
        log.append({"field": "truncated", "method": "detect", "source": source, "value": True})
    return log, False


def _impute_heading_field(doc: Document, source: str) -> tuple[list[dict], str | None]:
    """元数据层：heading 缺失填充

    Returns:
        (填充日志, heading 填充值（未填充时为 None）)
    """
    result = _impute_heading(doc)
    if result is None:
        return [], None

    heading_filled, method, confidence = result
    doc.metadata["heading"] = heading_filled
    doc.metadata["heading_source"] = method
    doc.metadata["heading_confidence"] = confidence
    doc.metadata["has_heading"] = bool(
        heading_filled
        and heading_filled != "[未命名文档]"
        and not heading_filled.startswith(_LOW_CONFIDENCE_PREFIX)
    )
    log = [
        {
            "field": "heading",
            "method": method,
            "source": source,
            "value": heading_filled,
            "confidence": confidence,
        }
    ]
    return log, heading_filled


def _impute_other_metadata(doc: Document, source: str, heading_filled: str | None) -> list[dict]:
    """元数据/结构层剩余字段：heading_path → category → auto_sections

    Returns:
        各字段的填充日志（未填充的字段不产生条目）
    """
    log: list[dict] = []

    heading_path_filled = _impute_heading_path(doc, heading_filled)
    if heading_path_filled is not None:
        doc.metadata["heading_path"] = heading_path_filled
        log.append(
            {
                "field": "heading_path",
                "method": "from_heading",
                "source": source,
                "value": heading_path_filled,
            }
        )

    category_filled = _impute_category(doc)
    if category_filled is not None:
        doc.metadata["category"] = category_filled
        log.append(
            {
                "field": "category",
                "method": "path_infer",
                "source": source,
                "value": category_filled,
            }
        )

    sections = _impute_section_headings(doc)
    if sections:
        doc.metadata["auto_sections"] = sections
        doc.metadata["has_auto_sections"] = True
        log.append(
            {
                "field": "auto_sections",
                "method": "auto_segment",
                "source": source,
                "value": f"{len(sections)} sections",
            }
        )

    return log


def _impute_single_doc(doc: Document) -> tuple[Document, list[dict]]:
    """处理单个文档的缺失值填充（可并行化）

    Returns:
        (填充后文档, 填充记录列表)
    """
    meta = doc.metadata or {}
    source = str(meta.get("source_path") or meta.get("source_file") or "unknown")
    doc_log: list[dict] = []

    # ── 内容层 ──
    content_log, is_empty = _impute_content_layer(doc, source)
    doc_log.extend(content_log)
    if is_empty:
        return doc, doc_log

    # ── 元数据层：heading ──
    heading_log, heading_filled = _impute_heading_field(doc, source)
    doc_log.extend(heading_log)

    # ── 元数据/结构层：heading_path / category / auto_sections ──
    doc_log.extend(_impute_other_metadata(doc, source, heading_filled))

    # ── 记录审计日志 ──
    if doc_log:
        doc.metadata["_impute_log"] = doc_log

    return doc, doc_log


def _impute_parallel(
    documents: list[Document], max_workers: int
) -> tuple[list[Document], list[dict]]:
    """并行处理文档集合（按原始顺序还原，丢弃空内容文档）"""
    filled_docs: list[Document] = []
    impute_log: list[dict] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_impute_single_doc, doc): i for i, doc in enumerate(documents)}

        results: list[tuple[int, Document, list[dict]]] = []
        for future in as_completed(futures):
            idx = futures[future]
            try:
                doc, doc_log = future.result()
                results.append((idx, doc, doc_log))
            except Exception as e:
                logger.error("Impute parallel error on doc %d: %s", idx, e)

        # 按原始顺序排列
        results.sort(key=lambda x: x[0])
        for idx, doc, doc_log in results:
            if doc.metadata.get("content_status") == "empty":
                impute_log.extend(doc_log)
                continue
            filled_docs.append(doc)
            impute_log.extend(doc_log)

    return filled_docs, impute_log


def _impute_serial(documents: list[Document]) -> tuple[list[Document], list[dict]]:
    """串行处理文档集合（丢弃空内容文档）"""
    filled_docs: list[Document] = []
    impute_log: list[dict] = []

    for doc in documents:
        doc, doc_log = _impute_single_doc(doc)

        if doc.metadata.get("content_status") == "empty":
            impute_log.extend(doc_log)
            continue

        filled_docs.append(doc)
        impute_log.extend(doc_log)

    return filled_docs, impute_log


def _log_impute_summary(impute_log: list[dict]) -> None:
    """汇总填充字段并输出统计日志"""
    if not impute_log:
        return
    filled_fields: dict[str, int] = {}
    for entry in impute_log:
        field = entry["field"]
        filled_fields[field] = filled_fields.get(field, 0) + 1
    logger.info(
        "Imputer: filled %d fields across %d docs — %s | cache=%s | guard=%s",
        len(impute_log),
        len(set(e["source"] for e in impute_log)),
        ", ".join(f"{k}:{v}" for k, v in sorted(filled_fields.items())),
        get_heading_cache_stats(),
        _resource_guard.summary(),
    )


def impute_documents(
    documents: list[Document],
    max_workers: int = 4,
    parallel: bool = True,
) -> tuple[list[Document], list[dict]]:
    """缺失值填充主函数

    对文档集合执行三级缺失值填充：
    1. 内容层：标记空内容/占位符/截断
    2. 元数据层：填充 heading / heading_path / category
    3. 结构层：为长文档自动分段标注

    支持并行处理和资源配额控制。

    Args:
        documents: 待填充文档列表（通常是清洗后的文档）
        max_workers: 并行工作线程数，默认 4
        parallel: 是否启用并行处理，默认 True

    Returns:
        (填充后文档列表, 填充记录列表)
        填充记录: [{"field": str, "method": str, "source": str, "value": str}]
    """
    # 重置资源监控器（每次入库开始时重置配额）
    _resource_guard.reset()
    # ★ 同时清空 heading 缓存：否则跨调用复用旧推断 —— 既让输出依赖「本函数被调用过几次」
    #   （非幂等），也不会察觉「同路径文件内容已变」（陈旧命中）。清空后本函数无跨调用状态。
    _heading_cache.clear()

    if parallel and len(documents) > 10:
        filled_docs, impute_log = _impute_parallel(documents, max_workers)
    else:
        filled_docs, impute_log = _impute_serial(documents)

    # ── 汇总日志 ──
    _log_impute_summary(impute_log)

    return filled_docs, impute_log
