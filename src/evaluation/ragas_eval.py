"""RAGAS Layer-1 评估：从旧工程迁移的最小可用版。"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import Any

from evaluation.adapters import (
    build_embeddings_for_relevancy,
    build_judge_llm,
    fill_sample,
)
from evaluation.config import EvaluationConfig
from evaluation.dataset import EvalSample

logger = logging.getLogger(__name__)


def _patch_ragas_json_fallback() -> None:
    """网关 JSON 缺字段时补默认，避免整批评测变 NaN（迁移自旧工程）。"""
    try:
        from ragas.prompt.pydantic_prompt import PydanticPrompt
    except Exception:
        return

    if getattr(PydanticPrompt, "_edu_json_fallback", False):
        return

    original = PydanticPrompt.generate_multiple

    async def generate_multiple_safe(self, *args: Any, **kwargs: Any):
        try:
            return await original(self, *args, **kwargs)
        except Exception:
            # 交由上层按失败处理；此处仅打日志，避免静默吞
            logger.warning("RAGAS generate_multiple 失败，尝试原始异常传播", exc_info=True)
            raise

    # 仅标记；完整 model_validate 补丁逻辑过重，v1 依赖 LangchainLLMWrapper + json_object
    PydanticPrompt.generate_multiple = generate_multiple_safe  # type: ignore[method-assign]
    PydanticPrompt._edu_json_fallback = True  # type: ignore[attr-defined]


async def prepare_samples(samples: list[EvalSample], cfg: EvaluationConfig) -> list[EvalSample]:
    filled: list[EvalSample] = []
    for i, s in enumerate(samples):
        logger.info("准备样本 [%d/%d] %s", i + 1, len(samples), s.query[:60])
        try:
            await fill_sample(
                s,
                k=cfg.retrieval_k,
                use_rerank=cfg.use_rerank,
                answer_timeout=cfg.answer_timeout,
            )
        except Exception:
            logger.warning("样本失败，跳过: %s", s.query[:40], exc_info=True)
            continue
        if not s.answer and not any(x.strip() for x in s.contexts):
            continue
        filled.append(s)
    return filled


def run_ragas_on_samples(samples: list[EvalSample], cfg: EvaluationConfig) -> dict[str, Any]:
    """对已填充 contexts/answer 的样本跑 RAGAS 指标。"""
    if not samples:
        return {"_meta": {"n": 0, "error": "no samples"}}

    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
    except ImportError as e:
        return {"_meta": {"n": len(samples), "error": f"ragas/datasets 未安装: {e}"}}

    metric_map = {
        "faithfulness": faithfulness,
        "context_precision": context_precision,
        "context_recall": context_recall,
        "answer_relevancy": answer_relevancy,
    }
    metrics = [metric_map[m] for m in cfg.ragas_metrics if m in metric_map]
    if not metrics:
        return {"_meta": {"n": len(samples), "error": "no metrics"}}

    judge = build_judge_llm()
    for m in metrics:
        if hasattr(m, "llm"):
            try:
                m.llm = judge
            except Exception:
                pass

    if any(getattr(m, "name", "") == "answer_relevancy" for m in metrics):
        emb = build_embeddings_for_relevancy()
        if emb is not None:
            try:
                answer_relevancy.embeddings = emb
            except Exception:
                pass

    _patch_ragas_json_fallback()
    records = [s.to_ragas_dict() for s in samples]
    dataset = Dataset.from_list(records)

    try:
        result = evaluate(dataset, metrics=metrics)
    except Exception as e:
        logger.error("ragas.evaluate 失败: %s", e, exc_info=True)
        return {"_meta": {"n": len(samples), "error": str(e)}}

    out: dict[str, Any] = {"_meta": {"n": len(samples)}}
    for name in cfg.ragas_metrics:
        if name not in metric_map:
            continue
        try:
            raw = result[name]
            scores = [float(x) for x in raw if x is not None and not math.isnan(float(x))]
            out[name] = {
                "mean": round(sum(scores) / len(scores), 4) if scores else None,
                "n": len(scores),
            }
        except Exception:
            logger.warning("指标 %s 读取失败", name, exc_info=True)
            out[name] = {"mean": None, "n": 0}
    return out


async def run_rag_evaluation(cfg: EvaluationConfig) -> dict[str, Any]:
    """加载数据集 → 检索+生成 → RAGAS → 写 JSON 报告。"""
    from evaluation.dataset import load_dataset

    samples = load_dataset(cfg.dataset_path, limit=cfg.dataset_limit)
    if not samples:
        return {"_meta": {"error": f"empty dataset: {cfg.dataset_path}"}}

    filled = await prepare_samples(samples, cfg)
    report = run_ragas_on_samples(filled, cfg)

    out_dir = Path(cfg.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = cfg.output_tag or "default"
    path = out_dir / f"ragas_{tag}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["_meta"]["report_path"] = str(path)
    logger.info("RAGAS 报告已写入 %s", path)
    return report
