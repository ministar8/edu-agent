"""RAGAS Layer-1 评估：从旧工程迁移的最小可用版。"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from core.settings import settings
from evaluation.adapters import (
    build_embeddings_for_relevancy,
    build_judge_llm,
    fill_sample,
)
from evaluation.config import EvaluationConfig
from evaluation.dataset import EvalSample

if TYPE_CHECKING:
    # 仅类型检查期需要。ragas 属可选 `eval` 依赖组，CI **不装**（故带 import-not-found 忽略）；
    # 而本地跑过 `uv sync --group eval` 后它会被真实解析出来 —— 两端都要能过。
    from ragas.dataset_schema import EvaluationResult  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)


def _patch_ragas_json_fallback() -> None:
    """网关 JSON 缺字段时补默认，避免整批评测变 NaN（迁移自旧工程）。"""
    try:
        from ragas.prompt.pydantic_prompt import PydanticPrompt  # type: ignore[import-not-found]
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
        # ★ 必须在 `import ragas` **之前**：ragas 0.4.3 在 `ragas/llms/base.py` 顶部
        # 无条件 import 一个 `langchain-community>=0.4` 已移除的模块，会让 `import ragas`
        # 直接 ModuleNotFoundError。原因与安全性论证见 `evaluation._ragas_compat`。
        from evaluation._ragas_compat import ensure_ragas_importable

        ensure_ragas_importable()

        from datasets import Dataset  # type: ignore[import-not-found]
        from ragas import evaluate  # type: ignore[import-not-found]
        from ragas.metrics import (  # type: ignore[import-not-found]
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
            except Exception as e:
                # 注入失败 = 该指标会退回 RAGAS 默认 LLM，评测口径**悄悄变了**。
                # 这类"没报错但结果不可比"的情况最难排查，必须留痕。
                logger.warning("无法为指标 %s 注入 judge LLM：%s", getattr(m, "name", "?"), e)

    # ── answer_relevancy 的 embeddings 注入（必须显式做，失败必须摘指标） ──
    # ragas 0.4.3 的 `aevaluate` 里有这段兜底：
    #     if isinstance(metric, MetricWithEmbeddings) and metric.embeddings is None:
    #         embeddings = embedding_factory(_infer_embedding_provider_from_llm(llm), ...)
    #         metric.embeddings = embeddings
    # 所以「不注入」≠「跳过该指标」，而是被**静默换成 RAGAS 默认的 OpenAI embedding**。
    # 后果：① 该指标用与检索链（bge-m3）**不同源**的向量算相似度，与其余三个不再同口径；
    # ② 多出一个 OPENAI_API_KEY 的隐式依赖。与其静默换口径，不如摘掉它。
    dropped: list[str] = []
    metric_warnings: list[str] = []
    if any(getattr(m, "name", "") == "answer_relevancy" for m in metrics):
        emb = build_embeddings_for_relevancy()
        if emb is None:
            dropped.append("answer_relevancy")
            metrics = [m for m in metrics if getattr(m, "name", "") != "answer_relevancy"]
            logger.warning(
                "无法构建 embeddings，已将 answer_relevancy 从本次评测移除"
                "（否则 ragas 会静默换用默认 OpenAI embedding，口径不一致）"
            )
        else:
            # 直接赋 langchain Embeddings 即可，**不需要** LangchainEmbeddingsWrapper。
            # 依据（按 0.4.3 源码核实，非记忆）：
            #   · ResponseRelevancy 是 @dataclass，MetricWithEmbeddings 也是 dataclass，
            #     字段注解 Optional[Union[BaseRagasEmbeddings, BaseRagasEmbedding]]，**无 pydantic 校验器**；
            #   · init() 只判「非 None」+ hasattr(embeddings, "set_run_config") 鸭子类型探测；
            #   · calculate_similarity 只调 self.embeddings.embed_query / embed_documents —— 我们的实现两者都有。
            # 反面记录：0.4.3 的 LangchainEmbeddingsWrapper 已 deprecated，且构造参数名是 `embeddings=`
            # （不是 `langchain_embeddings=`）—— 与 LangchainLLMWrapper(langchain_llm=...) **不对称**，按对称性猜会 TypeError。
            answer_relevancy.embeddings = emb
            if settings.USE_FAKE_EMBEDDING:
                metric_warnings.append(
                    "USE_FAKE_EMBEDDING=true：answer_relevancy 用的是确定性哈希向量"
                    "（仅保留词汇重叠信号，无语义泛化），该数值不代表语义相关性，不得写入结论"
                )
                logger.warning(
                    "USE_FAKE_EMBEDDING=true → answer_relevancy 的 embedding 是哈希桩，数值不可用于结论"
                )

    _patch_ragas_json_fallback()
    records = [s.to_ragas_dict() for s in samples]
    dataset = Dataset.from_list(records)

    try:
        # ★ 必须显式收窄：`evaluate` 的注解是 `Union[EvaluationResult, Executor]`
        # （`return_executor=True` 才给 Executor），而 `__getitem__` 只定义在
        # `EvaluationResult` 上 → 静态检查器对 `result[name]` 报 bad-index。
        # 用 cast 而非 `# type: ignore`：这里不是「检查器误报」，是注解不够精确。
        result = cast("EvaluationResult", evaluate(dataset, metrics=metrics))
    except Exception as e:
        logger.error("ragas.evaluate 失败: %s", e, exc_info=True)
        return {"_meta": {"n": len(samples), "error": str(e)}}

    out: dict[str, Any] = {"_meta": {"n": len(samples)}}
    if dropped:
        out["_meta"]["dropped_metrics"] = dropped
    if metric_warnings:
        out["_meta"]["warnings"] = metric_warnings
    for name in cfg.ragas_metrics:
        if name not in metric_map:
            continue
        if name in dropped:
            # 显式留痕：n=0 表示「没测」，而不是「测了得 0 分」
            out[name] = {"mean": None, "n": 0, "skipped": "embeddings unavailable"}
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
    from core.settings import settings
    from evaluation.dataset import load_dataset

    samples = load_dataset(cfg.dataset_path, limit=cfg.dataset_limit)
    if not samples:
        return {"_meta": {"error": f"empty dataset: {cfg.dataset_path}"}}

    filled = await prepare_samples(samples, cfg)
    report = run_ragas_on_samples(filled, cfg)

    # ★ 报告自描述：把「本次实际生效的口径」写进去。
    # 动机：`cfg.use_rerank=True` 与实际是否重排**不是一回事** ——
    # `reranker.rerank()` 在 `settings.RERANK_ENABLED` 为假时提前返回原序，
    # 而 `_stage_rerank` 的 `did_rerank` 仍为 True（它判「调用了」而非「生效了」）。
    # 数字一旦离开运行现场，参数标签就只能靠报告里的这几行 —— 不能靠记忆。
    report.setdefault("_meta", {})
    report["_meta"]["run_config"] = {
        "dataset": cfg.dataset_path,
        "limit": cfg.dataset_limit,
        "retrieval_k": cfg.retrieval_k,
        "requested_use_rerank": cfg.use_rerank,
        "effective_rerank_enabled": bool(settings.RERANK_ENABLED),
        "embedding_fake": bool(settings.USE_FAKE_EMBEDDING),
        "embedding_model": None if settings.USE_FAKE_EMBEDDING else settings.EMBEDDING_MODEL,
        "metrics_requested": list(cfg.ragas_metrics),
        "n_filled": len(filled),
        "n_loaded": len(samples),
    }

    out_dir = Path(cfg.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = cfg.output_tag or "default"
    path = out_dir / f"ragas_{tag}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["_meta"]["report_path"] = str(path)
    logger.info("RAGAS 报告已写入 %s", path)
    return report
