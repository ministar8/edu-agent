"""评估体系配置"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class EvaluationConfig:
    """单次评估运行的配置"""

    # ── 评估范围 ──
    layer: Literal["all", "ragas", "diagnosis"] = "all"
    category: str | None = None  # 限定学科，None 表示全部

    # ── 数据集 ──
    dataset_path: str = ""
    dataset_limit: int | None = None  # 限制测试条数（开发调试用）

    # ── Layer 1: RAGAS ──
    ragas_metrics: list[str] = field(
        default_factory=lambda: ["faithfulness", "context_precision", "context_recall", "answer_relevancy"]
    )
    # judge LLM — 默认跟随 settings.EVAL_JUDGE_MODEL（再回退到 settings.LLM_MODEL）
    judge_model: str = ""         # 空=跟随 settings 链
    judge_api_base: str = ""      # 空=跟随 settings 链
    judge_api_key: str = ""       # 空=跟随 settings 链
    # answer LLM — 默认跟随 settings.EVAL_ANSWER_MODEL（再回退到 settings.LLM_MODEL）
    answer_model: str = ""        # 空=跟随 settings 链
    answer_api_base: str = ""     # 空=跟随 settings 链
    answer_api_key: str = ""      # 空=跟随 settings 链

    # ── Layer 2: Diagnosis ──
    window_sizes: list[int] = field(default_factory=lambda: [0, 1, 2, 3])
    chunk_sizes: list[int] = field(default_factory=lambda: [400, 800])
    enable_route_ablation: bool = True
    enable_reranker_ablation: bool = True
    enable_decompose_analysis: bool = True

    # ── 输出 ──
    output_dir: str = "data/evaluation/results"
    output_tag: str = ""  # 报告文件名后缀

    # ── 检索 ──
    retrieval_k: int = 8   # RAGAS 评估检索 Top-K（8→给 reranker 更大候选池，提升 recall）
    use_rerank: bool = True

    # ── 快速模式 ──
    quick: bool = False  # 合并分组、减少指标，压到 ~5min


# 默认 recall 路由名称（metadata 路由见 adapters.py 的 CurrentDiagnosticRetriever.route_names）
ALL_RECALL_ROUTES = ["semantic", "keyword_bm25", "focus", "expanded", "kg_expand"]

# 耗时监控阈值（超过记警告，ms）
LATENCY_WARN_THRESHOLD = {
    "total": 3000,
    "recall": 1000,
    "rerank": 500,
    "window_expand": 200,
}
