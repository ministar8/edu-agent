"""评估运行器：协调 Layer 1 + Layer 2 的执行与报告生成"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.evaluation.config import EvaluationConfig
from app.evaluation.dataset import EvalSample, load_dataset, load_all_datasets
from app.evaluation.ragas_eval import run_ragas_evaluation
from app.evaluation.diagnosis import run_all_diagnostics
from app.evaluation.reporters import (
    build_metadata,
    write_json_report,
    write_markdown_report,
)

logger = logging.getLogger(__name__)

# 学科 → collection_name 映射（与 ingest.py 保持一致）
_COLLECTION_NAMES = {
    "data_structure": "data_structure",
    "computer_organization": "computer_organization",
    "operating_system": "operating_system",
    "computer_network": "computer_network",
    "questions": "questions",
    "learning_paths": "learning_paths",
}


def _resolve_collection(category: str | None) -> str:
    """将学科分类映射为 collection_name

    当 category 为空时返回空串，让检索器自动推断学科。
    """
    if category and category in _COLLECTION_NAMES:
        return _COLLECTION_NAMES[category]
    return ""


def run_evaluation(cfg: EvaluationConfig) -> dict[str, Any]:
    """执行一次完整的评估运行

    Args:
        cfg: 评估配置

    Returns:
        完整评估报告 dict
    """
    start = time.perf_counter()

    # ── 加载数据集 ──
    if cfg.dataset_path:
        all_samples: list[EvalSample] = load_dataset(cfg.dataset_path, limit=cfg.dataset_limit)
        dataset_name = cfg.dataset_path
    else:
        datasets = load_all_datasets(limit=cfg.dataset_limit)
        # 合并所有数据集
        all_samples = []
        for name, samples in datasets.items():
            all_samples.extend(samples)
        dataset_name = "all"

    if not all_samples:
        logger.warning("数据集为空，跳过评估")
        return {"_metadata": build_metadata(cfg.__dict__), "error": "empty dataset"}

    # ── 按学科分组样本 ──
    # 每条样本的 metadata.category 决定其检索的 collection；
    # 无 category 的样本使用空串（让检索器自动推断学科）
    # mixed 类别：按 cross_subject 首个学科分组（retrieve_contexts 会搜索全部）
    grouped: dict[str, list[EvalSample]] = {}
    for sample in all_samples:
        cat = sample.metadata.get("category", "")
        if cat == "mixed":
            cs_raw = sample.metadata.get("cross_subject", "")
            first_col = cs_raw.split(",")[0].strip() if cs_raw else ""
            col = _resolve_collection(first_col) if first_col else ""
        else:
            col = _resolve_collection(cat)
        grouped.setdefault(col, []).append(sample)

    # quick 模式：保留按学科分组，确保每条样本检索正确的 collection
    # （之前合并为 auto-route 会导致跨学科样本检索错误集合）
    if cfg.quick and len(grouped) > 1:
        logger.info("Quick 模式：保留 %d 个学科分组分别评估", len(grouped))

    collection_display = cfg.category or ",".join(sorted(grouped.keys())) or "auto"
    report: dict[str, Any] = {}
    report["_metadata"] = build_metadata({
        **cfg.__dict__,
        "dataset": dataset_name,
        "collection": collection_display,
        "sample_count": len(all_samples),
        "collection_groups": {k: len(v) for k, v in grouped.items()},
    })

    # ── Layer 1: RAGAS ──
    if cfg.layer in ("all", "ragas"):
        logger.info("开始 Layer 1: RAGAS 评估 (%d 条样本, %d 个分组)",
                    len(all_samples), len(grouped))
        layer1_start = time.perf_counter()

        ragas_result: dict[str, Any] = {}
        for col, samples in sorted(grouped.items()):
            logger.info("  RAGAS 分组 [%s]: %d 条样本", col or "auto", len(samples))
            group_result = run_ragas_evaluation(samples, col, cfg)
            # 合并：每个指标收集所有分组的分数
            if group_result.get("_meta", {}).get("error"):
                logger.warning("  RAGAS 分组 [%s] 执行失败: %s", col or "auto",
                               group_result["_meta"]["error"])
                continue
            has_metrics = False
            for metric_name, metric_val in group_result.items():
                if metric_name.startswith("_"):
                    continue
                raw = metric_val.get("raw_scores", []) if isinstance(metric_val, dict) else []
                if raw:
                    ragas_result.setdefault(metric_name, []).extend(raw)
                    has_metrics = True
            if not has_metrics:
                logger.warning("  RAGAS 分组 [%s] 无有效指标分数", col or "auto")

        # 对合并后的分数做聚合（保留 raw_scores 供下游分析）
        if ragas_result:
            from app.evaluation.ragas_eval import _aggregate_scores
            for metric_name, scores in ragas_result.items():
                if isinstance(scores, list) and scores:
                    aggregated = _aggregate_scores(scores)
                    aggregated["raw_scores"] = scores  # 保留原始分数
                    ragas_result[metric_name] = aggregated

        ragas_result["_meta"] = {
            "n": len(all_samples),
            "groups": len(grouped),
            "duration_ms": round((time.perf_counter() - layer1_start) * 1000, 3),
        }
        report["layer1"] = ragas_result
        logger.info("Layer 1 完成, 耗时 %.1fs", time.perf_counter() - layer1_start)

    # ── Layer 2: Diagnosis ──
    if cfg.layer in ("all", "diagnosis"):
        logger.info("开始 Layer 2: 诊断评估 (%d 条样本)", len(all_samples))
        layer2_start = time.perf_counter()

        # Layer 2 在每个非空分组上运行诊断，合并结果
        diag_results: dict[str, Any] = {}
        for col, samples in sorted(grouped.items()):
            if not col:
                continue
            logger.info("  Diagnosis 分组 [%s]: %d 条样本", col, len(samples))
            group_diag = run_all_diagnostics(samples, col, cfg)
            for key, val in group_diag.items():
                if key in diag_results:
                    # 合并策略：对含 sample_count 的扁平 dict 做加权平均，
                    # 对嵌套结构（by_route/by_group/results/breakdown）保留后一个分组的值
                    existing = diag_results[key]
                    if isinstance(existing, dict) and isinstance(val, dict):
                        if "sample_count" in existing and "sample_count" in val:
                            total_n = existing["sample_count"] + val["sample_count"]
                            merged = {}
                            for k in set(list(existing.keys()) + list(val.keys())):
                                if k == "sample_count":
                                    merged[k] = total_n
                                elif isinstance(existing.get(k), (int, float)) and isinstance(val.get(k), (int, float)):
                                    merged[k] = (existing[k] * existing["sample_count"] + val[k] * val["sample_count"]) / total_n
                                else:
                                    # 嵌套结构（dict/list）：保留后一个分组
                                    merged[k] = val[k]
                            merged["_merge_note"] = f"merged {total_n} samples across groups; nested structures from last group"
                            diag_results[key] = merged
                        else:
                            diag_results[f"{col}_{key}"] = val
                    else:
                        diag_results[f"{col}_{key}"] = val
                else:
                    diag_results[key] = val
        # 空分组样本也跑诊断（auto-route）
        if "" in grouped:
            auto_diag = run_all_diagnostics(grouped[""], "", cfg)
            for key, val in auto_diag.items():
                if key in diag_results:
                    diag_results[f"auto_{key}"] = val
                else:
                    diag_results[key] = val

        # 跨分组诊断：query_decomposition 不依赖 collection，对所有样本统一统计
        if cfg.enable_decompose_analysis:
            from app.evaluation.diagnosis import diagnose_query_decomposition
            diag_results["query_decomposition"] = diagnose_query_decomposition(all_samples, "", cfg)

        report["layer2"] = diag_results
        logger.info("Layer 2 完成, 耗时 %.1fs", time.perf_counter() - layer2_start)

    # ── 汇总 ──
    report["_metadata"]["total_duration_ms"] = round(
        (time.perf_counter() - start) * 1000, 3
    )

    return report


def save_report(report: dict[str, Any], output_dir: str, tag: str = "") -> dict[str, str]:
    """保存报告到文件

    Returns:
        {"json": str, "markdown": str} 文件路径
    """
    import os
    from datetime import datetime

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{tag}" if tag else ""
    base_name = f"eval_{ts}{suffix}"

    json_path = os.path.join(output_dir, f"{base_name}.json")
    md_path = os.path.join(output_dir, f"{base_name}.md")

    paths = {}

    json_written = write_json_report(report, json_path)
    paths["json"] = str(json_written)

    md_written = write_markdown_report(report, md_path)
    paths["markdown"] = str(md_written)

    return paths
