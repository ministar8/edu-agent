"""评估运行配置。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class EvaluationConfig:
    dataset_path: str = "evals/datasets/golden/sample_408.jsonl"
    dataset_limit: int | None = None
    # 分层抽样：按 metadata.query_type 每类取 N 条（与 dataset_limit 互斥）。
    # 为什么需要它：黄金集里类型与学科都是**成块排列**的，取前 N 条会系统性偏到
    # 概念题 + ds/co（详见 evaluation.ragas.dataset._stratified_sample）。
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
    output_dir: str = "evals/results/generation/ragas"
    output_tag: str = ""
    # 生成答案时的超时（秒）
    answer_timeout: float = 90.0
    # RAGAS judge 运行参数：降低并发以避免云端限流/排队超时，同时限制重试次数。
    ragas_timeout: int = 120
    ragas_max_retries: int = 1
    ragas_max_wait: int = 3
    ragas_max_workers: int = 2
    ragas_batch_size: int = 2
    # answer_relevancy 的 strictness（默认 3 = 每条样本生成 3 个问题取平均）。
    # ★ judge 只支持 n=1 时（如 DeepSeek 官网）必须设为 1，否则 400：
    #   "Invalid n value (currently only n = 1 is supported)"。
    answer_relevancy_strictness: int = 3
    # 复用已生成的 samples.jsonl：跳过检索+生成，只跑 judge。
    # 用途：生成阶段个别样本超时/中断时，补生成后不必重跑全部 156 条。
    reuse_samples_path: str = ""
    include_details: bool = False
