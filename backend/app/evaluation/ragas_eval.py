"""Layer 1: RAGAS 标准指标评估

使用 RAGAS 原生指标 + 系统 LLM 作为 judge。
通过 protocols.py 接口与 RAG 实现解耦。
"""

from __future__ import annotations

import logging
import math
import time
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from datasets import Dataset

from app.config import settings
from app.evaluation.config import EvaluationConfig
from app.evaluation.dataset import EvalSample
from app.evaluation.adapters import get_retriever, get_eval_embedding
from app.rag.rag_utils import estimate_tokens as _estimate_tokens

logger = logging.getLogger(__name__)

# ── 答案生成 Prompt ──────────────────────────────────
_ANSWER_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "你是一名教学答疑助手。请基于以下检索到的教材内容，"
        "用中文回答学生的问题。回答应当准确、简洁，"
        "只使用上下文中提供的信息。如果上下文中没有足够信息，"
        "请明确说明。"
    )),
    ("human", "上下文：\n{context}\n\n问题：{question}"),
])


def _resolve_eval_llm_config(
    model: str,
    api_base: str,
    api_key: str,
    settings_model: str,
    settings_api_base: str,
    settings_api_key: str,
) -> tuple[str, str, str]:
    """解析评估 LLM 配置链：cfg > EVAL_* settings > 全局 settings

    Args:
        model/api_base/api_key: EvaluationConfig 传入的覆盖值
        settings_model/api_base/api_key: settings 中 eval 专用的配置项

    Returns:
        (model, api_base, api_key) 三元组
    """
    resolved_model = model or settings_model or settings.LLM_MODEL
    resolved_base = api_base or settings_api_base or settings.LLM_API_BASE
    resolved_key = api_key or settings_api_key or settings.LLM_API_KEY
    return resolved_model, resolved_base, resolved_key


def _is_deepseek_api(api_base: str, model: str) -> bool:
    """判断是否为 DeepSeek 系列 API（需传 enable_thinking 专有参数）"""
    return "deepseek" in (api_base or "").lower() or "deepseek" in (model or "").lower()


def _create_eval_llm(
    model: str,
    api_base: str,
    api_key: str,
    temperature: float = 0.0,
) -> ChatOpenAI:
    """创建评估专用的 ChatOpenAI 实例（不污染全局 settings/缓存）"""
    kwargs: dict[str, Any] = dict(
        api_key=api_key,
        base_url=api_base,
        model=model,
        temperature=temperature,
        streaming=False,
    )
    # enable_thinking 是 DeepSeek 专有参数，禁用思考模式以保证结构化输出稳定
    if _is_deepseek_api(api_base, model):
        kwargs["extra_body"] = {"enable_thinking": False}
    return ChatOpenAI(**kwargs)


def _get_answer_llm(cfg: EvaluationConfig) -> ChatOpenAI:
    """获取答案生成 LLM（独立配置，不篡改全局 settings）"""
    model, base, key = _resolve_eval_llm_config(
        cfg.answer_model, cfg.answer_api_base, cfg.answer_api_key,
        settings.EVAL_ANSWER_MODEL, settings.EVAL_ANSWER_API_BASE, settings.EVAL_ANSWER_API_KEY,
    )
    logger.info("Eval answer LLM: model=%s base=%s", model, base)
    return _create_eval_llm(model, base, key, temperature=0.3)


def _get_judge_llm(cfg: EvaluationConfig) -> ChatOpenAI:
    """获取评测 LLM（独立配置，不篡改全局 settings）"""
    model, base, key = _resolve_eval_llm_config(
        cfg.judge_model, cfg.judge_api_base, cfg.judge_api_key,
        settings.EVAL_JUDGE_MODEL, settings.EVAL_JUDGE_API_BASE, settings.EVAL_JUDGE_API_KEY,
    )
    logger.info("Eval judge LLM: model=%s base=%s", model, base)
    return _create_eval_llm(model, base, key, temperature=0.0)


def retrieve_contexts(
    query: str,
    collection_name: str,
    cfg: EvaluationConfig,
    cross_subject_collections: list[str] | None = None,
) -> list[str]:
    """检索相关上下文（通过接口，与 RAG 实现解耦）

    Args:
        cross_subject_collections: 跨学科样本需搜索的多个 collection，
            如 ["operating_system", "computer_organization"]。
            非空时按 collection 分别检索并合并去重。
    """
    retriever = get_retriever()

    if cross_subject_collections:
        # 跨学科：分别检索每个 collection，合并去重
        all_contents: list[str] = []
        seen: set[str] = set()
        per_col_k = max(cfg.retrieval_k // len(cross_subject_collections), 3)
        for col in cross_subject_collections:
            try:
                docs = retriever.retrieve(
                    query=query,
                    collection_name=col,
                    k=per_col_k,
                    use_rerank=cfg.use_rerank,
                )
                for d in docs:
                    content = d["content"]
                    if content not in seen:
                        seen.add(content)
                        all_contents.append(content)
            except Exception as e:
                logger.warning("Cross-subject retrieve failed for %s: %s", col, e)
        return all_contents
    else:
        docs = retriever.retrieve(
            query=query,
            collection_name=collection_name,
            k=cfg.retrieval_k,
            use_rerank=cfg.use_rerank,
        )
        return [d["content"] for d in docs]


def _normalize_content(content: Any) -> str:
    """归一化 LLM 返回的 content 为字符串

    DashScope 某些模型返回 [{"text": "..."}] 而非纯字符串。
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)
    return str(content)


# 答案缓存：避免重复评估时重生成，节省 token
_answer_cache: dict[str, str] = {}
_ANSWER_CACHE_MAX = 500

# Token 消耗统计
_token_counter: dict[str, int] = {
    "answer_input": 0, "answer_output": 0, "answer_calls": 0,
    "cache_hits": 0, "empty_context_skips": 0,
}

# 上下文 token 预算（粗估：中文×1.5 + ASCII×0.25）
_CONTEXT_TOKEN_BUDGET = 4000


def _truncate_contexts(contexts: list[str], budget: int = _CONTEXT_TOKEN_BUDGET) -> list[str]:
    """按 token 预算截断上下文，避免全量灌入 LLM"""
    result: list[str] = []
    used = 0
    for ctx in contexts:
        t = _estimate_tokens(ctx)
        if used + t > budget:
            # 截断当前 context 到剩余预算
            remaining = budget - used
            if remaining > 100:
                # 按 token 比例估算字符截断位置
                char_budget = int(len(ctx) * remaining / max(t, 1))
                result.append(ctx[:char_budget] + "...")
            break
        result.append(ctx)
        used += t
    return result


def _answer_cache_key(query: str, contexts: list[str]) -> str:
    """答案缓存 key：query + contexts 摘要"""
    import hashlib
    ctx_hash = hashlib.md5("||".join(contexts).encode()).hexdigest()[:8]
    return f"{query}::{ctx_hash}"


def generate_answer(query: str, contexts: list[str], cfg: EvaluationConfig, use_cache: bool = True) -> str:
    """基于上下文生成答案（带缓存 + 上下文截断）"""
    # 缓存命中
    cache_key = _answer_cache_key(query, contexts) if use_cache else ""
    if cache_key and cache_key in _answer_cache:
        _token_counter["cache_hits"] += 1
        return _answer_cache[cache_key]

    # 截断上下文
    truncated = _truncate_contexts(contexts)
    context_text = "\n\n".join(truncated)
    llm = _get_answer_llm(cfg)
    messages = _ANSWER_PROMPT.format_messages(question=query, context=context_text)
    response = llm.invoke(messages)
    answer = _normalize_content(response.content)

    # Token 统计
    _token_counter["answer_input"] += _estimate_tokens(context_text) + _estimate_tokens(query)
    _token_counter["answer_output"] += _estimate_tokens(answer)
    _token_counter["answer_calls"] += 1

    # 写入缓存
    if cache_key:
        if len(_answer_cache) >= _ANSWER_CACHE_MAX:
            _answer_cache.clear()
        _answer_cache[cache_key] = answer

    return answer


def run_ragas_evaluation(
    samples: list[EvalSample],
    collection_name: str,
    cfg: EvaluationConfig,
) -> dict[str, Any]:
    """执行 RAGAS 评估

    流程：
    1. 对每条样本：检索上下文 → 生成答案
    2. 用 RAGAS 原生指标 + judge LLM 计算分数
    3. 聚合输出

    Returns:
        {"faithfulness": {mean, std, p50, p90, ...},
         "context_precision": {...},
         "context_recall": {...},
         "answer_relevancy": {...},
         "_meta": {...}}
    """
    start = time.perf_counter()
    ragas_records: list[dict[str, Any]] = []

    # 重置计数器（防止上次异常中断导致脏数据）
    _token_counter.update({"answer_input": 0, "answer_output": 0, "answer_calls": 0,
                           "cache_hits": 0, "empty_context_skips": 0})

    skipped = 0
    for idx, sample in enumerate(samples):
        logger.info("RAGAS [%d/%d] %s", idx + 1, len(samples), sample.query[:60])

        # 检索上下文（如果未预置）
        if not sample.contexts:
            try:
                # 跨学科样本：从 metadata.cross_subject 提取多集合
                cross_cols = None
                cs_raw = sample.metadata.get("cross_subject", "")
                if cs_raw:
                    cross_cols = [c.strip() for c in cs_raw.split(",") if c.strip()]
                contexts = retrieve_contexts(
                    sample.query, collection_name, cfg,
                    cross_subject_collections=cross_cols,
                )
            except Exception as e:
                logger.warning("RAGAS [%d/%d] 检索失败，跳过: %s", idx + 1, len(samples), e)
                skipped += 1
                continue
        else:
            contexts = sample.contexts

        # 空 context 检测：跳过 LLM 调用，避免生成废话浪费 token
        has_valid_context = bool(contexts) and any(c.strip() for c in contexts)

        # 生成答案（如果未预置）
        if not sample.answer and has_valid_context:
            try:
                answer = generate_answer(sample.query, contexts, cfg)
            except Exception as e:
                logger.warning("RAGAS [%d/%d] 答案生成失败: %s", idx + 1, len(samples), e)
                answer = ""
        elif sample.answer:
            answer = sample.answer
        else:
            answer = ""

        if not has_valid_context and not answer:
            logger.info("RAGAS [%d/%d] 空 context 且无预置答案，跳过", idx + 1, len(samples))
            _token_counter["empty_context_skips"] += 1
            skipped += 1
            continue

        record = sample.to_ragas_dict()
        record["contexts"] = contexts
        record["answer"] = answer
        ragas_records.append(record)

    if skipped:
        logger.warning("RAGAS: 跳过 %d/%d 条样本（检索失败）", skipped, len(samples))

    if not ragas_records:
        return {}

    # ── RAGAS 原生计算 ──
    from ragas import evaluate as ragas_evaluate
    from ragas.metrics import (
        faithfulness,
        context_precision,
        context_recall,
        answer_relevancy,
    )

    dataset = Dataset.from_list(ragas_records)

    # 配置 judge LLM（覆盖 RAGAS 默认的 GPT-4）
    judge_llm = _get_judge_llm(cfg)

    # 选择启用的指标
    metric_map = {
        "faithfulness": faithfulness,
        "context_precision": context_precision,
        "context_recall": context_recall,
        "answer_relevancy": answer_relevancy,
    }
    metrics_to_compute = [
        metric_map[name] for name in cfg.ragas_metrics if name in metric_map
    ]

    if not metrics_to_compute:
        logger.warning("没有启用的 RAGAS 指标")
        return {"_meta": {"n": len(ragas_records), "error": "no metrics enabled"}}

    # 获取 embedding（仅 answer_relevancy 需要，其他指标不需要）
    eval_embedding = None
    if "answer_relevancy" in cfg.ragas_metrics:
        try:
            eval_embedding = get_eval_embedding()
        except Exception as e:
            logger.warning("Embedding 初始化失败，跳过 answer_relevancy: %s", e)
            metrics_to_compute = [m for m in metrics_to_compute if m != answer_relevancy]
            if not metrics_to_compute:
                return {"_meta": {"n": len(ragas_records), "error": f"embedding unavailable: {e}"}}

    try:
        ragas_result = ragas_evaluate(
            dataset,
            metrics=metrics_to_compute,
            llm=judge_llm,
            embeddings=eval_embedding.langchain_embeddings if eval_embedding else None,
        )
    except Exception as e:
        logger.error("RAGAS evaluate 失败: %s", e)
        return {"_meta": {"n": len(ragas_records), "error": str(e)}}

    # NaN 诊断：输出每条样本的原始分数用于排查
    # RAGAS 0.4.x EvaluationResult.__contains__ 会触发 __getitem__(0) 导致 KeyError
    # 安全方式：直接访问 _scores_dict 或 try/except
    result_scores = getattr(ragas_result, "_scores_dict", {})

    # 记录实际使用的模型配置（提前解析，供 NaN 诊断和 _meta 使用）
    judge_model_name, judge_base, _ = _resolve_eval_llm_config(
        cfg.judge_model, cfg.judge_api_base, cfg.judge_api_key,
        settings.EVAL_JUDGE_MODEL, settings.EVAL_JUDGE_API_BASE, settings.EVAL_JUDGE_API_KEY,
    )
    answer_model_name, answer_base, _ = _resolve_eval_llm_config(
        cfg.answer_model, cfg.answer_api_base, cfg.answer_api_key,
        settings.EVAL_ANSWER_MODEL, settings.EVAL_ANSWER_API_BASE, settings.EVAL_ANSWER_API_KEY,
    )

    nan_metrics = []
    for metric_name in cfg.ragas_metrics:
        if metric_name in metric_map and metric_name in result_scores:
            vals = [float(s) for s in result_scores[metric_name]]
            nan_count = sum(1 for v in vals if isinstance(v, float) and math.isnan(v))
            if nan_count > 0:
                nan_metrics.append(f"{metric_name}={nan_count}/{len(vals)} NaN")
    if nan_metrics:
        logger.warning("RAGAS NaN detected: %s — judge model may be incompatible (model=%s base=%s)",
                       ", ".join(nan_metrics), judge_model_name, judge_base)

    # ── 聚合结果（单次遍历，同时计算统计 + 附加 raw_scores）──
    aggregated: dict[str, dict[str, float]] = {}

    for metric_name in cfg.ragas_metrics:
        if metric_name not in metric_map:
            continue
        try:
            scores = result_scores.get(metric_name, ragas_result[metric_name])
            vals = [float(s) for s in scores]
            aggregated[metric_name] = _aggregate_scores(vals)
            aggregated[metric_name]["raw_scores"] = vals
        except (KeyError, TypeError, ValueError) as e:
            logger.warning("无法读取指标 %s: %s", metric_name, e)

    aggregated["_meta"] = {
        "n": len(ragas_records),
        "duration_ms": round((time.perf_counter() - start) * 1000, 3),
        "judge_model": judge_model_name,
        "judge_api_base": judge_base,
        "answer_model": answer_model_name,
        "answer_api_base": answer_base,
        "skipped": skipped,
        "token_stats": {
            "answer_input_est": _token_counter["answer_input"],
            "answer_output_est": _token_counter["answer_output"],
            "answer_llm_calls": _token_counter["answer_calls"],
            "cache_hits": _token_counter["cache_hits"],
            "empty_context_skips": _token_counter["empty_context_skips"],
            # RAGAS judge LLM token 粗估：每条样本每指标 ~2K input + ~300 output
            "judge_input_est": len(ragas_records) * len(metrics_to_compute) * 2000,
            "judge_output_est": len(ragas_records) * len(metrics_to_compute) * 300,
        },
    }

    return aggregated


def _aggregate_scores(scores: list[float]) -> dict[str, float | int]:
    """对分数列表做聚合统计（自动过滤 NaN）"""
    if not scores:
        return {}
    # 过滤 NaN：一粒老鼠屎不坏一锅汤
    nan_count = sum(1 for s in scores if isinstance(s, float) and math.isnan(s))
    valid_scores = [s for s in scores if not (isinstance(s, float) and math.isnan(s))]
    if not valid_scores:
        return {"mean": float('nan'), "n": len(scores), "nan_count": nan_count}
    sorted_scores = sorted(valid_scores)
    n = len(sorted_scores)
    mean_val = sum(sorted_scores) / n
    variance = sum((s - mean_val) ** 2 for s in sorted_scores) / n
    # 小样本分位数修正：n<10 时 p90 退化为 max，改用插值
    def _percentile(vals: list[float], p: float) -> float:
        if len(vals) <= 1:
            return vals[0]
        k = (len(vals) - 1) * p
        f_idx = int(k)
        c_idx = min(f_idx + 1, len(vals) - 1)
        frac = k - f_idx
        return vals[f_idx] + frac * (vals[c_idx] - vals[f_idx])
    return {
        "mean": round(mean_val, 4),
        "std": round(variance ** 0.5, 4) if n > 1 else 0.0,
        "min": round(sorted_scores[0], 4),
        "max": round(sorted_scores[-1], 4),
        "p50": round(_percentile(sorted_scores, 0.5), 4),
        "p90": round(_percentile(sorted_scores, 0.9), 4),
        "n": len(scores),
        "valid_n": n,
        "nan_count": nan_count,
    }
