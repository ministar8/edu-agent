"""评估运行配置。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvaluationConfig:
    dataset_path: str = "evals/sample_408.jsonl"
    dataset_limit: int | None = None
    # 分层抽样：按 metadata.query_type 每类取 N 条（与 dataset_limit 互斥）。
    # 为什么需要它：黄金集里类型与学科都是**成块排列**的，取前 N 条会系统性偏到
    # 概念题 + ds/co（详见 evaluation.dataset._stratified_sample）。
    sample_per_type: int | None = None
    ragas_metrics: list[str] = field(
        default_factory=lambda: [
            "faithfulness",
            "context_precision",
            "context_recall",
            "answer_relevancy",
        ]
    )
    retrieval_k: int = 5
    use_rerank: bool = True
    output_dir: str = "evals/results"
    output_tag: str = ""
    # 生成答案时的超时（秒）
    answer_timeout: float = 90.0
    # RAGAS judge 运行参数：降低并发以避免云端限流/排队超时，同时限制重试次数。
    ragas_timeout: int = 120
    ragas_max_retries: int = 1
    ragas_max_wait: int = 3
    ragas_max_workers: int = 2
    ragas_batch_size: int = 2
    include_details: bool = False
