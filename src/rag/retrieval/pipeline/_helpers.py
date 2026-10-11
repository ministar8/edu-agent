"""检索阶段的纯辅助函数（从 pipeline.py 拆出，行为等价）。

★ 这里的函数**不被猴子补丁**，故可脱离 `_stages` 存放；被阶段函数调用的几个
  （`_apply_rerank_threshold` 等）会 `import` 回 `_stages` 命名空间 —— 因为调用方
  在 `_stages` 里以「模块全局」方式解析它们，`setattr(_stages, name, wrapper)` 仍然有效。
"""

from __future__ import annotations

import logging

from langchain_core.documents import Document

from core.settings import settings
from rag.common.rag_utils import content_key
from rag.retrieval.hyde import generate_hyde_query
from rag.retrieval.postprocess import sentence_window_expand
from rag.retrieval.query_classifier import RetrievalDepth
from rag.retrieval.routes import _log_final_retrieval_summary, _safe_to_thread

logger = logging.getLogger(__name__)


def _apply_rerank_threshold(
    reranked: list[Document],
    *,
    min_keep: int = 2,
) -> list[Document]:
    """对 Rerank 结果应用双重阈值过滤（相对 + 绝对），兜底保留 top-N。

    策略：
    1. 相对阈值：保留 rerank_score >= top_score * RERANK_MIN_SCORE
    2. 绝对阈值：丢弃 rerank_score < RERANK_ABSOLUTE_MIN_SCORE
    3. 兜底：过滤后不足 min_keep 个时，强制保留 rerank 排序最靠前的 min_keep 个
    """
    if not reranked:
        return reranked

    top_score = reranked[0].metadata.get("rerank_score", 0) or 0

    # 相对阈值
    rel_min = top_score * settings.RERANK_MIN_SCORE if top_score > 0 else 0
    # 绝对阈值
    abs_min = settings.RERANK_ABSOLUTE_MIN_SCORE

    # 取两者中更高的作为最终阈值
    final_min = max(rel_min, abs_min)

    high_confidence = [d for d in reranked if (d.metadata.get("rerank_score", 0) or 0) >= final_min]

    if len(high_confidence) >= min_keep:
        return high_confidence

    # 兜底：保留 top-min_keep
    fallback = reranked[:min_keep]
    logger.info(
        "Rerank threshold fallback: only %d/%d >= %.3f (rel=%.3f, abs=%.3f), keeping top-%d",
        len(high_confidence),
        len(reranked),
        final_min,
        rel_min,
        abs_min,
        min_keep,
    )
    return fallback


# ── 重排关闭的一次性告警（C4：关闭动作必须可观测）──────────────
# `.env` 的 RERANK_ENABLED=false 是**稳态配置**而非异常，故每进程只告警一次，
# 避免在每条 query 上刷屏（批量脚本/门禁会连打多条）。
# ⚠️ 与 reranker.py 里闸 3 的告警区分：那个是「防御网被触发」，属异常，每次都要打。
_rerank_disabled_warned = False


def _warn_rerank_disabled_once(use_rerank: bool, filtered: list[Document]) -> None:
    """重排被部署开关关闭时告警一次（仅当确有候选且调用方要求重排）。"""
    global _rerank_disabled_warned
    if _rerank_disabled_warned or not (use_rerank and filtered):
        return
    _rerank_disabled_warned = True
    logger.warning(
        "重排已按部署开关关闭（settings.RERANK_ENABLED=false）：调用方要求重排"
        "（use_rerank=True）但本次不执行，候选按原始顺序截断返回。"
        "如需开启请在 .env 设 RERANK_ENABLED=true 并确保 TEI reranker 可用。"
    )


def _empty_result_fallback(
    deduped: list[tuple[Document, float]], query: str, effective_threshold: float
) -> list[Document]:
    """阈值过滤后为空时的保底：返回最高分 top-1。

    ── 空结果保底（2026-09-24）────────────────────────────────────────
    症状：real embedding 路由下 3/156 条 query 返回空，而**去重后本有 120+ 条候选**
    —— 全部被阈值卡掉。fake 路由从不出现，因为假 embedding 的相似度分布更平，
    同一个文档更容易在多条路由里都排前 → 累加 RRF 分数更高 → 过得了阈值。

    为什么阈值会高过可达上限（实测反推，非推断）：
      `_resolve_thresholds` 的校准公式基于 k=20（见其注释里 `2.5/40` 的算例），
      但 `_dynamic_rrf_k` 在 13 条路由时给出 **k=36**，分数尺度随之缩小约 1.8×。
      于是 answer/exercise 类阈值 = 0.06×1.667×1.2 = **0.12**、long/comparison = **0.11**，
      而 RRF 可达上限（两条最高权重路由相加）= 2.5/37 + 1.5/37 = **0.1081**。
      **阈值 > 上限 → 只要 top 文档没命中 ≥3 条路由，必然返回空。**
    本该兜底的 HyDE 又恰好对 `answer`/`exercise`/`code` 三类显式禁用
    （`should_trigger_hyde`），而这 3 条正是 answer×2 + code×1 → 兜底也失效。

    为什么只做保底、不调阈值：`docs/RETRIEVAL_ROADMAP.md` 的「不做清单」明确列着
    「检索阈值微调 | #13 / #25」——三次实证真实口径零收益或有害。故此处**不动阈值**，
    只补一个独立缺陷：**「有候选却返回空」本身是错误的降级**。
    为什么只取 top-1 而不是 top-k：取最小必要内容，**不假装这些文档"合格"**；
    且保留「低召回」信号（docs_count<2）给下游的 HyDE 兜底。
    """
    # 用 max() 而非 deduped[0]：后者依赖 `dedup_same_section` 末尾那个 sort，
    # 一旦那个 sort 被改动，[0] 会**静默**选到非最高分的文档。
    best_doc, best_score = max(deduped, key=lambda pair: pair[1])
    logger.warning(
        "阈值过滤后为空，已保底返回 top-1：query=%s threshold=%.4f 最高分=%.4f "
        "候选=%d（阈值高于 RRF 可达上限，见 pipeline._stage_dedup_and_threshold 注释）",
        query[:40],
        effective_threshold,
        best_score,
        len(deduped),
    )
    return [best_doc]


async def _generate_hyde_query(query: str) -> str:
    """生成 HyDE 假设答案；LLM 超时/失败返回空串（不抛）。"""
    return await _safe_to_thread(
        "async_hyde_generate",
        generate_hyde_query,
        query,
        timeout=min(float(getattr(settings, "LLM_TIMEOUT", 60) or 60), 10.0),
        default="",
    )


def _top_rerank_score(docs: list[Document]) -> float:
    """docs 中最高的 rerank_score（无则 0.0）。"""
    scores = [
        float(doc.metadata.get("rerank_score") or 0.0)
        for doc in docs
        if doc.metadata.get("rerank_score") is not None
    ]
    return max(scores) if scores else 0.0


def _merge_hyde_docs(
    filtered: list[Document], hyde_docs: list[Document], hyde_query: str, k: int, query: str
) -> tuple[list[Document], int]:
    """给 HyDE 文档打标、按内容键去重后并入；返回 ``(新的 filtered, 净增条数)``。

    ⚠️ 净增必须是**净增**，不是候选数：最终条数被 `max(k, 原长度)` 封顶 ——
    若记候选数，「候选 20 条但结果仍是 5 条」会被记成 +20，语义失真。
    """
    for doc in hyde_docs:
        doc.metadata["_hyde_fallback"] = True
        doc.metadata["_hyde_query"] = hyde_query[:120]

    existing_keys = {content_key(doc) for doc in filtered}
    merged_hyde_docs = []
    for doc in hyde_docs:
        key = content_key(doc)
        if key not in existing_keys:
            merged_hyde_docs.append(doc)
            existing_keys.add(key)
    if not merged_hyde_docs:
        return filtered, 0

    _before = len(filtered)
    _candidates = len(merged_hyde_docs)
    filtered = (filtered + merged_hyde_docs)[: max(k, len(filtered))]
    added_count = len(filtered) - _before
    # HyDE 是**低频兜底**路径（触发条件：召回 < 2 条）—— 触发必须留痕。
    logger.info(
        "HyDE 兜底触发：query=%s 候选 +%d 条，净增 %d 条（%d → %d 条）",
        query[:40],
        _candidates,
        added_count,
        _before,
        len(filtered),
    )
    _log_final_retrieval_summary("async-post-hyde", query, filtered)
    return filtered, added_count


def _adaptive_window_size(depth: RetrievalDepth | None) -> int:
    if depth and depth.depth == "shallow":
        return 0
    return 1 if (depth and depth.depth == "standard") else 2


def _expand_windows_session(
    filtered: list[Document], collection_name: str, depth: RetrievalDepth | None
) -> list[Document]:
    """句子窗口展开：指定单一集合则整体展开；跨集合则按 `_collection` 分组逐集合展开。

    窗口要在各自集合内取相邻 chunk，跨集合混在一起会取到别的集合的邻居。
    """
    if collection_name:
        return sentence_window_expand(
            filtered, collection_name, window_size=_adaptive_window_size(depth)
        )
    grouped_docs: dict[str, list[Document]] = {}
    for doc in filtered:
        doc_collection = str(doc.metadata.get("_collection") or "")
        if doc_collection:
            grouped_docs.setdefault(doc_collection, []).append(doc)
    if not grouped_docs:
        return filtered
    expanded_docs: list[Document] = []
    for doc_collection, docs_in_collection in grouped_docs.items():
        expanded_docs.extend(
            sentence_window_expand(
                docs_in_collection, doc_collection, window_size=_adaptive_window_size(depth)
            )
        )
    return expanded_docs
