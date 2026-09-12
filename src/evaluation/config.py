"""评估运行配置。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvaluationConfig:
    dataset_path: str = "evals/sample_408.jsonl"
    dataset_limit: int | None = None
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
