"""门禁数据模型（MetricSpec / QueryOutcome / RetrievalMetrics / RerankObservation）与 compute_metrics。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple


@dataclass
class MetricSpec:
    """指标的退化方向与容差。"""

    direction: str  # "higher" | "lower"
    tolerance: float


_METRIC_SPECS: dict[str, MetricSpec] = {
    "category_hit_at_1": MetricSpec("higher", 0.02),
    "category_hit_at_k": MetricSpec("higher", 0.02),
    "category_mrr": MetricSpec("higher", 0.02),
    "category_precision": MetricSpec("higher", 0.02),
    "empty_result_rate": MetricSpec("lower", 0.0),
    "mean_evidence_count": MetricSpec("higher", 0.5),
    # ── 章级知识点口径（比学科细一档；学科级已饱和，测不出改动） ──
    "kp_hit_at_k": MetricSpec("higher", 0.02),
    "kp_mrr": MetricSpec("higher", 0.02),
    # 被标注的查询条数。容差 0、方向 higher ⇒ **标注被误删会立刻失败**。
    "kp_annotated": MetricSpec("higher", 0.0),
}


@dataclass
class QueryOutcome:
    """单条查询的检索结果（只保留计算指标所需的最小信息）。"""

    query: str
    # 多值：出题类查询的合法证据来源有两处（对应学科讲义 / 历年真题），
    # 见 `load_golden_queries`。单值会把它判成「学科未命中」。
    expected_categories: tuple[str, ...]
    hit_categories: list[str] = field(default_factory=list)
    # 章级知识点（见 `chapter_of_source`）：期望值来自黄金集标注，命中值是逐条证据的章。
    expected_knowledge_points: list[str] = field(default_factory=list)
    hit_knowledge_points: list[str] = field(default_factory=list)

    @property
    def first_correct_rank(self) -> int | None:
        """首个命中**任一**目标类目的排名（1-based）；没有则 None。"""
        expected = set(self.expected_categories)
        for index, cat in enumerate(self.hit_categories, 1):
            if cat in expected:
                return index
        return None

    @property
    def first_correct_kp_rank(self) -> int | None:
        """首个命中目标知识点的排名（1-based）。

        无标注（``expected_knowledge_points`` 为空）时返回 None —— 这类查询不进
        ``kp_hit@k`` / ``kp_mrr`` 的分母，否则「未标注」会被误判成「未命中」。
        """
        if not self.expected_knowledge_points:
            return None
        expected = set(self.expected_knowledge_points)
        for index, label in enumerate(self.hit_knowledge_points, 1):
            if label in expected:
                return index
        return None


@dataclass
class RetrievalMetrics:
    """黄金集上的聚合指标。

    ``kp_*`` 三项按**章级知识点**度量（载体见 ``chapter_of_source``），是比「学科」
    细一档的中间层 —— 学科级已饱和（``category_hit_at_k = 1.0``），测不出检索改动。
    """

    n_queries: int
    category_hit_at_1: float
    category_hit_at_k: float
    category_mrr: float
    category_precision: float
    empty_result_rate: float
    mean_evidence_count: float
    kp_hit_at_k: float = 0.0
    kp_mrr: float = 0.0
    kp_annotated: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "n_queries": self.n_queries,
            "category_hit_at_1": round(self.category_hit_at_1, 4),
            "category_hit_at_k": round(self.category_hit_at_k, 4),
            "category_mrr": round(self.category_mrr, 4),
            "category_precision": round(self.category_precision, 4),
            "empty_result_rate": round(self.empty_result_rate, 4),
            "mean_evidence_count": round(self.mean_evidence_count, 4),
            "kp_hit_at_k": round(self.kp_hit_at_k, 4),
            "kp_mrr": round(self.kp_mrr, 4),
            "kp_annotated": round(self.kp_annotated, 4),
        }


def compute_metrics(outcomes: list[QueryOutcome]) -> RetrievalMetrics:
    """把逐条检索结果聚合成指标。**纯函数**，不依赖任何运行时环境。"""
    if not outcomes:
        return RetrievalMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    n = len(outcomes)
    hit_at_1 = 0
    hit_at_k = 0
    rr_sum = 0.0
    empty = 0
    correct_total = 0
    returned_total = 0
    # 知识点口径：只有被标注过的查询才进分母（未标注 ≠ 未命中）。
    kp_annotated = 0
    kp_hit_at_k = 0
    kp_rr_sum = 0.0

    for outcome in outcomes:
        rank = outcome.first_correct_rank
        if rank is not None:
            hit_at_k += 1
            rr_sum += 1.0 / rank
            if rank == 1:
                hit_at_1 += 1
        if not outcome.hit_categories:
            empty += 1
        expected = set(outcome.expected_categories)
        correct_total += sum(1 for cat in outcome.hit_categories if cat in expected)
        returned_total += len(outcome.hit_categories)

        if outcome.expected_knowledge_points:
            kp_annotated += 1
            kp_rank = outcome.first_correct_kp_rank
            if kp_rank is not None:
                kp_hit_at_k += 1
                kp_rr_sum += 1.0 / kp_rank

    return RetrievalMetrics(
        n_queries=n,
        category_hit_at_1=hit_at_1 / n,
        category_hit_at_k=hit_at_k / n,
        category_mrr=rr_sum / n,
        category_precision=correct_total / returned_total if returned_total else 0.0,
        empty_result_rate=empty / n,
        mean_evidence_count=returned_total / n,
        kp_hit_at_k=kp_hit_at_k / kp_annotated if kp_annotated else 0.0,
        kp_mrr=kp_rr_sum / kp_annotated if kp_annotated else 0.0,
        kp_annotated=float(kp_annotated),
    )


class RerankObservation(NamedTuple):
    """单条 query 的 rerank 观察，供 ``_assert_route_preconditions`` 反静默回退。

    - ``has_evidence``：该 query 是否返回了非空证据（空结果不参与断言）
    - ``has_rerank_score``：证据里出现 ``rerank_score > 0`` —— 重排确实跑过
    - ``rerank_used``：链路自报的「本次是否用过重排」（B2 起由 `rerank_status=="success"` 派生）
    - ``rerank_status``：★ B2 tier-0 四态原文 `off`/`success`/`degraded`/`failed`；
      缺字段（老链路）⇒ ``""``（未知，按「未知」处理，**不回填**）

    后两者是**两个独立信号**：交叉验证才能抓出"自报值失真"
    （曾出现：部署开关关掉重排后仍返回 ``rerank_used=True``）。
    """

    has_evidence: bool
    has_rerank_score: bool
    rerank_used: bool
    rerank_status: str = ""
