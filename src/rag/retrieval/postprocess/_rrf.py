"""自动拆分自 postprocess.py（行为等价）。"""

from __future__ import annotations

import hashlib
import math

from langchain_core.documents import Document

from rag.retrieval.postprocess._log import logger
from rag.retrieval.query_classifier import QueryCategory

# RRF 常数 k 基准值（RAG 场景每路 5-20 条结果，k=20 平衡排名区分度与多路融合）
_RRF_K_BASE = 20


def _dynamic_rrf_k(route_count: int) -> int:
    """按路由数动态调整 RRF k 值

    路由多时 k 需更大（降低排名区分度，让多路融合更平滑），
    路由少时 k 更小（增强区分度，让 top-1 信号更强）。
    经验值：k ≈ 10 × sqrt(route_count)
    """
    return max(10, min(60, int(_RRF_K_BASE * math.sqrt(route_count) / math.sqrt(4))))


def _rrf_scale(k: int) -> float:
    """把 RRF 分数归一到**标定参考 k**（`_RRF_K_BASE`），使分数尺度与路由数解耦。

    ★ 为什么必须有（2026-09-27 实测）：阈值是按 **k = `_RRF_K_BASE`(=20)** 标定的
    （见 `retriever._resolve_thresholds` 注释里 `2.5/40` 的算例），
    而 `_dynamic_rrf_k` 在 13 条路由时给出 **36** ⇒ 分数尺度随之缩小约 1.76×，
    **阈值却没跟着缩**。后果是**量纲错配**，不是「宁严勿滥」：

    | 查询类别 | 有效阈值 | 可达上限（两条最高权重路由都排第 1） |
    |---|---|---|
    | 短概念 | 0.0600 | 0.1027 |
    | 一般 | 0.0600 | 0.0811 |
    | 对比 | 0.0880 | 0.1081 |
    | **练习 / 批改** | **0.1200** | **0.1081** ← 阈值高于上限 |
    | 代码 | 0.1200 | 0.1351 |

    ⇒ 练习/批改类（占黄金集 **41%**）只要文档没被 **≥3 条**路由命中，就**必然**被滤掉。

    归一到参考 k 后：rank 1 处的分数与 `k == _RRF_K_BASE` 时**完全一致**；
    `k == _RRF_K_BASE` 时该因子为 **1**，行为不变。
    """
    return (k + 1) / (_RRF_K_BASE + 1)


def _rrf_scale_needed(cat: QueryCategory | None, k: int) -> bool:
    """该类别当前的有效阈值**是否高于其 RRF 可达上限**（见 `_rrf_scale`）。

    ★ **只在越界时启用** —— 那才是量纲错配真正造成危害的地方。
    对本来就有余量的类别放大分数，只会让更多低分噪声越过阈值：
    实测**全局**修正虽让 `kp@k` 6 条路由全升（最高 +0.0705），
    却把 `category_precision` 在 2 条路由压破 0.02 容差（−0.0272 / −0.0324）；
    **收窄**后代价降到 −0.0242 / −0.0296。用户于 2026-09-27 明确接受该权衡。

    ⚠️ **不能按类别名判定** —— 实测「用信号量写出生产者—消费者问题的伪代码」
    同时被标为 `is_exercise` **与** `is_code`，但它有 `code_meta` 与另一条同权重路由
    （top2 = 5.0），可达上限 0.1351 **高于**阈值 0.12，**并不越界**。按类别名判会误伤它。

    ⚠️ 这里的阈值公式与 `retriever._resolve_thresholds` **同源**
    （`0.06` / `1.5` / `1.2·0.75·1.1` 三个系数）。**两者是一对**：
    那边改公式，这里必须同步，否则判定会静默失效（该修的没修、或不该修的乱修）。

    完整分析见 `docs/RETRIEVAL_PLAN.md` §3⑦。
    """
    if cat is None:
        return False

    from rag.retrieval.recall import ALL_ROUTES, get_route_weight

    weights = sorted((get_route_weight(r, cat) for r in ALL_ROUTES), reverse=True)

    # 与 `retriever._resolve_thresholds` 同源的阈值（只用于**判定**，不改阈值）
    threshold = 0.06 * (weights[0] / 1.5)
    if cat.is_exercise or cat.is_answer:
        threshold *= 1.2
    elif cat.is_short:
        threshold *= 0.75
    elif cat.is_long or cat.is_comparison:
        threshold *= 1.1

    return threshold > (weights[0] + weights[1]) / (k + 1)


def _base_route_name(route_name: str) -> str:
    return route_name.rsplit(":", 1)[-1].strip()


def _dedup_key(doc: Document) -> str:
    """去重键 = `集合 + content_hash`（跨集合去重，防同名文档被误合并）。"""
    collection = doc.metadata.get("_collection", "")
    content_hash = doc.metadata.get("content_hash")
    if not content_hash:
        content_hash = hashlib.sha256(doc.page_content[:200].encode()).hexdigest()[:16]
    else:
        content_hash = str(content_hash)
    return f"{collection}::{content_hash}"


# ── RRF 合并 ──────────────────────────────────────────


def _accumulate_route_merge(
    route_results: list[tuple[str, list[tuple[Document, float]]]],
    k: int,
    scale: float,
    cat: QueryCategory | None,
) -> dict[str, tuple[Document, float, set[str], dict[str, float]]]:
    """按路由把文档累加进 `merged`（键 = 集合 + 内容哈希，防跨集合同名误合并）。"""
    from rag.retrieval.recall import get_route_weight

    merged: dict[str, tuple[Document, float, set[str], dict[str, float]]] = {}
    for route_name, results in route_results:
        w = get_route_weight(_base_route_name(route_name), cat)
        for rank, (doc, original_score) in enumerate(results, 1):
            key = _dedup_key(doc)
            rrf_contribution = w / (k + rank) * scale

            existing = merged.get(key)
            if existing is None:
                copied = Document(page_content=doc.page_content, metadata=dict(doc.metadata))
                merged[key] = (copied, rrf_contribution, {route_name}, {route_name: original_score})
            else:
                doc_obj, prev_score, routes, route_scores = existing
                merged[key] = (
                    doc_obj,
                    prev_score + rrf_contribution,
                    routes | {route_name},
                    {**route_scores, route_name: original_score},
                )
    return merged


def _finalize_route_merge(
    merged: dict[str, tuple[Document, float, set[str], dict[str, float]]],
) -> list[tuple[Document, float]]:
    """写回 `recall_*` 元数据，并按确定序排序。

    排序必须**完全确定**：RRF 分数并列时若沿用插入顺序，而插入顺序又来自
    ThreadPoolExecutor.as_completed 的完成次序，同一 query 每次运行都会得到
    不同的证据排列（实测 category_hit@1 在 0.900~0.925 间抖动）。
    这既让检索结果不可复现，也让质量门禁的噪声高于它能识别的退化幅度。
    用 _dedup_key 作次级键：merged 就是以它为键，故唯一且确定。
    """
    ranked: list[tuple[Document, float]] = []
    for doc, rrf_score, routes, route_scores in merged.values():
        doc.metadata["recall_score"] = round(rrf_score, 6)
        doc.metadata["recall_routes"] = ", ".join(sorted(routes))
        doc.metadata["recall_route_count"] = len(routes)
        for rn, rs in route_scores.items():
            doc.metadata[f"recall_{rn}_score"] = round(float(rs), 6)
        ranked.append((doc, rrf_score))
    ranked.sort(key=lambda item: (-item[1], _dedup_key(item[0])))
    return ranked


def merge_route_results(
    route_results: list[tuple[str, list[tuple[Document, float]]]],
    cat: QueryCategory | None = None,
) -> list[tuple[Document, float]]:
    """RRF (Reciprocal Rank Fusion) 合并多路检索结果

    加权 RRF：不同路由按查询类型赋予不同权重。
    公式：score(d) = Σ w(route, cat) / (k + rank_i(d)) × scale
    其中 `scale` 只在**阈值高于可达上限**的类别上取 `_rrf_scale(k)`，否则为 1.0
    —— 判定与理由见 `_rrf_scale_needed` 的文档串。
    优点：
    - 对异常高分不敏感（排名 1 和 2 的差距是 1/(k+1)-1/(k+2)）
    - 跨路由重复文档自然获得更高分数
    - 精准路由（metadata 过滤）权重高于宽泛路由（semantic）
    """
    # 动态 k：路由多时 k 更大，让多路融合更平滑
    k = _dynamic_rrf_k(len(route_results))
    scale = _rrf_scale(k) if _rrf_scale_needed(cat, k) else 1.0
    merged = _accumulate_route_merge(route_results, k, scale, cat)
    ranked = _finalize_route_merge(merged)

    logger.debug(
        "RRF k=%d routes=%d raw=%d merged=%d top=%.4f multi=%d",
        k,
        len(route_results),
        sum(len(results) for _, results in route_results),
        len(ranked),
        ranked[0][1] if ranked else 0,
        sum(1 for _, _, routes, _ in merged.values() if len(routes) >= 2),
    )
    return ranked


# ── 加权 RRF 合并（查询分解用） ──────────────────────────────


def _accumulate_weighted_merge(
    grouped_results: list[tuple[str, list[tuple[Document, float]]]],
    weights: dict[str, float],
    k: int,
    scale: float,
    cat: QueryCategory | None,
) -> dict[str, tuple[Document, float, set[str]]]:
    """按来源把文档累加进 `merged`，含 route 级加权（从 recall_routes 元数据提取）。"""
    from rag.retrieval.recall import get_route_weight

    merged: dict[str, tuple[Document, float, set[str]]] = {}
    for label, results in grouped_results:
        w_source = weights.get(label, 1.0)
        for rank, (doc, _original_score) in enumerate(results, 1):
            # 路由级加权：从 recall_routes metadata 提取路由名
            route_str = doc.metadata.get("recall_routes", "")
            route_names = [r.strip() for r in route_str.split(",") if r.strip()]
            if route_names and cat is not None:
                w_route = max(get_route_weight(_base_route_name(r), cat) for r in route_names)
            else:
                w_route = 1.0
            # 去重 key 用 content_hash + collection，避免同 section 不同 chunk 前100字相同被误合并
            key = _dedup_key(doc)
            rrf_contribution = w_source * w_route / (k + rank) * scale

            existing = merged.get(key)
            if existing is None:
                copied = Document(page_content=doc.page_content, metadata=dict(doc.metadata))
                copied.metadata["_decompose_weight"] = w_source
                merged[key] = (copied, rrf_contribution, {label})
            else:
                doc_obj, prev_score, labels = existing
                merged[key] = (doc_obj, prev_score + rrf_contribution, labels | {label})
    return merged


def _finalize_weighted_merge(
    merged: dict[str, tuple[Document, float, set[str]]],
) -> list[tuple[Document, float]]:
    """写回 `recall_score` / `_decompose_labels`，并按确定性次序排序。"""
    ranked: list[tuple[Document, float]] = []
    for doc, rrf_score, labels in merged.values():
        doc.metadata["recall_score"] = round(rrf_score, 6)
        doc.metadata["_decompose_labels"] = ", ".join(sorted(labels))
        ranked.append((doc, rrf_score))
    # 同 merge_route_results：并列分数必须用确定性的次级键，否则结果不可复现
    ranked.sort(key=lambda item: (-item[1], _dedup_key(item[0])))
    return ranked


def weighted_rrf_merge(
    grouped_results: list[tuple[str, list[tuple[Document, float]]]],
    weights: dict[str, float],
    k: int = 0,
    cat: QueryCategory | None = None,
) -> list[tuple[Document, float]]:
    """加权 RRF 合并：不同来源（原始查询/子查询）可赋予不同权重

    标准 RRF: score(d) = Σ 1/(k + rank_i(d)) × scale
    加权 RRF: score(d) = Σ w_source × w_route / (k + rank_i(d)) × scale
    （`scale` 的取值见 `_rrf_scale_needed`）

    w_source: 原始查询 1.5，子查询 1.0，确保原始语境信号更强。
    w_route: 从 recall_routes metadata 提取路由名，按 get_route_weight 加权，
             使分解路径与非分解路径的 RRF 分数分布归一化到同一尺度。
    去重 key 使用 content_hash + collection（与 merge_route_results 一致，避免同前缀误合并）。
    """
    # 动态 k：k=0 时按路由数自动计算
    if k <= 0:
        total_routes = sum(len(results) for _, results in grouped_results)
        k = _dynamic_rrf_k(max(1, total_routes // max(1, len(grouped_results))))
    scale = _rrf_scale(k) if _rrf_scale_needed(cat, k) else 1.0
    merged = _accumulate_weighted_merge(grouped_results, weights, k, scale, cat)
    ranked = _finalize_weighted_merge(merged)

    logger.debug(
        "Weighted RRF k=%d raw=%d merged=%d top=%.4f",
        k,
        sum(len(results) for _, results in grouped_results),
        len(ranked),
        ranked[0][1] if ranked else 0,
    )
    return ranked
