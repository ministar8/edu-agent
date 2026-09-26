"""RAGAS 评估 CLI。

uv sync --group eval
python -m evaluation.cli --dataset evals/sample_408.jsonl --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys


def _preflight(cfg) -> list[tuple[bool, str]]:
    """跑前探活：把「静默降级」变成「明确失败」。

    返回 ``[(是否阻塞, 说明)]``。★ 用**显式布尔**而不是「消息里含某关键词」判定阻塞：
    后者一旦有人改了措辞，拦截就会**静默失效** —— 这类保护措施必须看实际拦截效果，
    不能看它是否存在。

    ★ 为什么必须有这一步 —— 本机 `.env` 是 `RERANK_ENABLED=false`，
    而 `EvaluationConfig.use_rerank` 默认 `True`。两者不一致时，
    `reranker.rerank()` 会在 `if not settings.RERANK_ENABLED: return documents[:top_k]`
    处**提前返回原序**（一行重排都没跑），于是报告会把「未重排」标成「已重排」。
    ★ 2026-09-24：该「谎报」缺陷已在 `retriever.py` 侧修复（`_stage_rerank` 现在
    返回真实的 `rerank_used`，关闭时整段短路）。此处保留**显式声明开关** +
    **真实推理探活**，作为口径自描述的双保险 —— 不依赖下游字段语义不变。
    这类「没报错但口径变了」最难排查，所以探活不看 /health，不通就**退出码 2**。
    """
    import httpx

    from core.settings import settings

    problems: list[tuple[bool, str]] = []

    if cfg.use_rerank:
        url = f"{settings.RERANK_LOCAL_URL}/rerank"
        try:
            resp = httpx.post(
                url,
                json={"query": "探活", "texts": ["探活文本"], "raw_scores": False},
                timeout=30.0,
            )
            resp.raise_for_status()
        except Exception as e:
            problems.append((True, f"重排已请求但不可用：{url} → {type(e).__name__}: {e}"))
    else:
        problems.append(
            (
                False,
                "重排未启用（--no-rerank）：本次结果**不代表**生产路径（生产是 use_rerank=True）",
            )
        )

    if not settings.USE_FAKE_EMBEDDING:
        url = f"{settings.EMBEDDING_API_BASE}/embeddings"
        try:
            resp = httpx.post(
                url,
                json={"model": settings.EMBEDDING_MODEL, "input": ["探活"]},
                timeout=60.0,
            )
            resp.raise_for_status()
        except Exception as e:
            problems.append((True, f"真实 embedding 不可用：{url} → {type(e).__name__}: {e}"))
    else:
        problems.append(
            (False, "USE_FAKE_EMBEDDING=true：检索走确定性哈希向量，**语义质量结论无效**")
        )

    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="edu-agent RAGAS evaluation")
    parser.add_argument("--dataset", default="evals/sample_408.jsonl")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--sample-per-type",
        type=int,
        default=None,
        help=(
            "按 query_type 分层等距抽样，每类 N 条（与 --limit 互斥）。"
            "★ 不要用 --limit 控制成本：黄金集里 4 类查询是成块排列的，"
            "--limit 40 只会取到 40 条纯概念题，等于退回 0.1 之前的盲区。"
        ),
    )
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--no-rerank", action="store_true")
    parser.add_argument(
        "--metrics",
        default="faithfulness,context_precision,context_recall,answer_relevancy",
        help="逗号分隔",
    )
    parser.add_argument("--output-dir", default="evals/results")
    parser.add_argument("--tag", default="")
    parser.add_argument("--ragas-timeout", type=int, default=120, help="单个 judge 操作超时秒数")
    parser.add_argument("--ragas-max-retries", type=int, default=1, help="judge 最大重试次数")
    parser.add_argument("--ragas-max-wait", type=int, default=3, help="重试间隔上限秒数")
    parser.add_argument("--ragas-max-workers", type=int, default=2, help="judge 最大并发数")
    parser.add_argument("--ragas-batch-size", type=int, default=2, help="分批提交的样本数")
    parser.add_argument(
        "--include-details",
        action="store_true",
        help="保存逐条 query、上下文、来源和 RAGAS 分数明细",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="跳过跑前探活（仅用于明知降级仍要出数的场景）",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    from core.settings import settings
    from evaluation.config import EvaluationConfig
    from evaluation.ragas_eval import run_rag_evaluation

    cfg = EvaluationConfig(
        dataset_path=args.dataset,
        dataset_limit=args.limit,
        sample_per_type=args.sample_per_type,
        retrieval_k=args.k,
        use_rerank=not args.no_rerank,
        ragas_metrics=[m.strip() for m in args.metrics.split(",") if m.strip()],
        output_dir=args.output_dir,
        output_tag=args.tag,
        ragas_timeout=args.ragas_timeout,
        ragas_max_retries=args.ragas_max_retries,
        ragas_max_wait=args.ragas_max_wait,
        ragas_max_workers=args.ragas_max_workers,
        ragas_batch_size=args.ragas_batch_size,
        include_details=args.include_details,
    )

    # ★ 显式声明重排开关（照 `retrieval_gate.configure_for_gate` 的模式）。
    # 不这样做的话，`use_rerank=True` 会被 `.env` 的 RERANK_ENABLED=false 静默吃掉。
    # `reranker` 在调用期读 settings，因此这里的赋值确实生效。
    settings.RERANK_ENABLED = cfg.use_rerank

    notes = _preflight(cfg)
    log = logging.getLogger("evaluation.cli")
    for _is_blocking, msg in notes:
        log.warning("口径提示：%s", msg)

    blocking = [msg for is_blocking, msg in notes if is_blocking]
    if blocking and not args.skip_preflight:
        for b in blocking:
            log.error("探活失败：%s", b)
        print(
            json.dumps(
                {"_meta": {"error": "preflight failed", "problems": blocking}},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    report = asyncio.run(run_rag_evaluation(cfg))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not report.get("_meta", {}).get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
