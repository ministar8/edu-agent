"""检索质量黄金集回归门禁。

为什么需要它
------------
RAG 检索链的改动（阈值常数、RRF 路由权重、切分策略、去重规则、集合路由）**无法用单测
证明"没让检索变差"** —— 单测只能证明"某个函数返回了预期值"，证明不了端到端命中质量。
本模块把 ``evals/sample_408.jsonl`` 变成可自动判定的回归门禁：
固定查询集 + 固定期望学科 + 固定指标 → 与基线对比，退化即失败。

设计取舍（读之前请先看这三条）
------------------------------
1. **指标锚定在「学科类目」而不是「具体 chunk_id」。**
   类目来自数据集自身的 ``subject`` 标签，是客观 ground truth，不需要人工维护 40 条期望；
   而 chunk 级期望会在任何一次切分/embedding 变更后大面积失效，维护成本远高于收益。

2. **用确定性哈希 embedding 跑（``USE_FAKE_EMBEDDING``），不依赖 TEI。**
   因此它衡量的是**检索管线**（路由 / 融合 / 阈值 / 去重 / 窗口展开）是否退化，
   **不是语义质量**。语义质量由 ``evaluation/cli.py`` 的 RAGAS 离线评测负责。
   推论：门禁必须与基线**同环境**对比，跨 embedding 实现比较数字没有意义。

3. **``empty_result_rate`` 与 ``mean_evidence_count`` 必须一起看。**
   只看 ``category_precision`` 会有一个致命盲区：**返回 0 条时精确率无定义/被算成完美**。
   这两个指标就是用来堵这个盲区的 —— 检索链"静默返回空"是最危险的退化形态。

用法::

    python -m evaluation.retrieval_gate                    # 跑门禁并与基线对比
    python -m evaluation.retrieval_gate --update-baseline  # 重录基线（需在 PR 里说明原因）
    python -m evaluation.retrieval_gate --limit 10         # 快速抽查
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 数据集 subject 标签 → 知识库集合名。这是黄金集的 ground truth 来源。
SUBJECT_TO_CATEGORY: dict[str, str] = {
    "ds": "data_structure",
    "co": "computer_organization",
    "os": "operating_system",
    "network": "computer_network",
}

DEFAULT_GOLDEN_PATH = "evals/sample_408.jsonl"
DEFAULT_BASELINE_PATH = "evals/retrieval_baseline.json"

# 门禁运行参数。写进基线文件，避免"拿不同配置的数字互相比较"。
GATE_K = 5
GATE_USE_RERANK = False


@dataclass
class MetricSpec:
    """指标的退化方向与容差。"""

    direction: str  # "higher" | "lower"
    tolerance: float


# 容差取 0.02（≈ 1/40 条查询），意味着**单条查询退化即失败**。
_METRIC_SPECS: dict[str, MetricSpec] = {
    "category_hit_at_1": MetricSpec("higher", 0.02),
    "category_hit_at_k": MetricSpec("higher", 0.02),
    "category_mrr": MetricSpec("higher", 0.02),
    "category_precision": MetricSpec("higher", 0.02),
    "empty_result_rate": MetricSpec("lower", 0.0),
    "mean_evidence_count": MetricSpec("higher", 0.5),
}


@dataclass
class QueryOutcome:
    """单条查询的检索结果（只保留计算指标所需的最小信息）。"""

    query: str
    expected_category: str
    hit_categories: list[str] = field(default_factory=list)

    @property
    def first_correct_rank(self) -> int | None:
        """首个命中目标学科的排名（1-based）；没有则 None。"""
        for index, cat in enumerate(self.hit_categories, 1):
            if cat == self.expected_category:
                return index
        return None


@dataclass
class RetrievalMetrics:
    """黄金集上的聚合指标。"""

    n_queries: int
    category_hit_at_1: float
    category_hit_at_k: float
    category_mrr: float
    category_precision: float
    empty_result_rate: float
    mean_evidence_count: float

    def as_dict(self) -> dict[str, float]:
        return {
            "n_queries": self.n_queries,
            "category_hit_at_1": round(self.category_hit_at_1, 4),
            "category_hit_at_k": round(self.category_hit_at_k, 4),
            "category_mrr": round(self.category_mrr, 4),
            "category_precision": round(self.category_precision, 4),
            "empty_result_rate": round(self.empty_result_rate, 4),
            "mean_evidence_count": round(self.mean_evidence_count, 4),
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

    for outcome in outcomes:
        rank = outcome.first_correct_rank
        if rank is not None:
            hit_at_k += 1
            rr_sum += 1.0 / rank
            if rank == 1:
                hit_at_1 += 1
        if not outcome.hit_categories:
            empty += 1
        correct_total += sum(
            1 for cat in outcome.hit_categories if cat == outcome.expected_category
        )
        returned_total += len(outcome.hit_categories)

    return RetrievalMetrics(
        n_queries=n,
        category_hit_at_1=hit_at_1 / n,
        category_hit_at_k=hit_at_k / n,
        category_mrr=rr_sum / n,
        category_precision=correct_total / returned_total if returned_total else 0.0,
        empty_result_rate=empty / n,
        mean_evidence_count=returned_total / n,
    )


def compare_to_baseline(current: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    """返回退化项的人类可读描述列表；空列表表示通过。**纯函数**。

    注意：``n_queries`` 只做一致性校验，不参与退化判定 —— 查询条数变化说明基线失效，
    应报错而不是当作退化。
    """
    regressions: list[str] = []

    if current.get("n_queries") != baseline.get("n_queries"):
        regressions.append(
            f"查询条数不一致：当前 {current.get('n_queries')} vs 基线 "
            f"{baseline.get('n_queries')} —— 基线已失效，请确认黄金集是否被改动"
        )
        return regressions

    for name, spec in _METRIC_SPECS.items():
        cur = float(current.get(name, 0.0))
        base = float(baseline.get(name, 0.0))
        if spec.direction == "higher":
            if cur < base - spec.tolerance:
                regressions.append(f"{name} 退化：{base:.4f} → {cur:.4f}（容差 {spec.tolerance}）")
        elif cur > base + spec.tolerance:
            regressions.append(f"{name} 退化：{base:.4f} → {cur:.4f}（容差 {spec.tolerance}）")

    return regressions


def load_golden_queries(path: str | Path, limit: int | None = None) -> list[tuple[str, str]]:
    """加载 (query, expected_category) 列表；跳过无法映射 subject 的行。"""
    filepath = Path(path)
    if not filepath.exists():
        raise FileNotFoundError(f"黄金集不存在: {filepath}")

    items: list[tuple[str, str]] = []
    with open(filepath, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("黄金集第 %d 行解析失败，跳过", line_num)
                continue
            query = str(raw.get("query", "")).strip()
            subject = str((raw.get("metadata") or {}).get("subject", "")).strip()
            category = SUBJECT_TO_CATEGORY.get(subject)
            if not query or not category:
                logger.warning("黄金集第 %d 行缺 query 或 subject 无法映射，跳过", line_num)
                continue
            items.append((query, category))
            if limit and len(items) >= limit:
                break
    return items


def configure_for_gate(persist_dir: str) -> None:
    """把 settings 切成"离线可跑"形态，并重置模块级单例。

    必须在跑检索前调用。之所以是函数而不是模块级副作用：``settings`` 是 import 期
    构造的单例，测试和 CLI 需要各自决定何时生效。

    ``CHROMA_PORT = 1`` 是为了让 ``VectorStoreManager`` 走 PersistentClient 分支
    （端口 1 不可能有真实服务），从而把索引落到临时目录而不是真实的 ``chroma_db/``。

    **LLM 也必须显式拉回假网关**（不只是设 ``USE_FAKE_MODEL``）：检索链的
    decompose / HyDE 会调 LLM，若这里漏掉，本地（.env 配了真实 key）会真的打线上模型
    —— 温度 0.3，基线不可复现且产生费用；CI（无 key）则抛
    ``openai.OpenAIError: Missing credentials``，实测让 40 条 query 里 6 条崩溃。
    settings 侧已有"USE_FAKE_MODEL 拉回假网关"的逻辑，这里再显式设一次是**故意的重复**：
    门禁的正确性不该依赖 settings 的默认推导，显式声明才能保证任何环境下行为一致。
    """
    from core.settings import GATEWAY_DEFAULT_MODEL, Gateway, make_model_ref, settings
    from rag import semantic_cache as sc
    from rag import vectorstore as vs

    settings.USE_FAKE_EMBEDDING = True
    settings.CHROMA_PORT = 1
    settings.CHROMA_PERSIST_DIR = persist_dir
    settings.SEMANTIC_CACHE_ENABLED = False
    settings.RERANK_ENABLED = False

    settings.USE_FAKE_MODEL = True
    fake_ref = make_model_ref(Gateway.FAKE, GATEWAY_DEFAULT_MODEL[Gateway.FAKE])
    settings.DEFAULT_MODEL = fake_ref
    settings.LLM_MODEL = fake_ref

    # 模块级单例在 import 期已按旧 settings 构造，必须重置
    vs._vector_store_manager = None
    sc._semantic_cache = None


def wait_for_index_ready(
    categories: list[str],
    *,
    retries: int = 8,
    delay: float = 0.5,
    repair: bool = True,
) -> dict[str, int]:
    """等每个集合的 HNSW 索引可查询，返回 {集合: 成功前的失败次数}。

    就绪检测实现在 ``VectorStoreManager.wait_until_ready``（生产路径同款）。

    ``repair=True`` 时，对"段文件未落盘"的集合做**一次重建后重试**。门禁这么做有理由：
    这是**一次性索引**，重建无副作用且只要几秒；而该故障在进程内无法等待恢复
    （实测「丢弃句柄」「重开 client」均无效，只有 ``delete_collection`` + 重新入库有效）。
    门禁的价值是稳定反映检索质量，不该被上游索引故障污染成"随机失败"。

    生产路径**不做**自动重建 —— 那里删除集合意味着真实数据丢失，必须人工确认。
    """
    from rag import vectorstore as vs

    manager = vs.get_vector_store_manager()
    ready: dict[str, int] = {}

    for category in categories:
        try:
            ready[category] = manager.wait_until_ready(category, retries=retries, delay=delay)
            continue
        except RuntimeError as exc:
            if not repair:
                raise
            logger.warning("集合 '%s' 索引不可查询，重建后重试：%s", category, exc)

        manager.delete_collection(category)
        build_index([category])
        ready[category] = manager.wait_until_ready(category, retries=retries, delay=delay)

    return ready


def build_index(categories: list[str] | None = None) -> dict[str, int]:
    """用与 ``rag.ingest`` 相同的管线把知识库索引进当前（临时）向量库。

    刻意复用 ``ingest`` 的同一条链路（load → clean → split → enhance → tag → add），
    这样门禁覆盖的是**真实入库路径**，而不是一条评测专用的旁路。
    """
    from rag import vectorstore as vs
    from rag.cleaner import clean_documents
    from rag.enhancer import enhance_documents
    from rag.ingest import DEFAULT_CATEGORIES
    from rag.knowledge_tagger import tag_chunks_with_knowledge_points
    from rag.loader import SUPPORTED_EXTENSIONS, load_single_file
    from rag.splitter import split_documents

    manager = vs.get_vector_store_manager()
    counts: dict[str, int] = {}
    knowledge_dir = Path("knowledge")

    for category in categories or DEFAULT_CATEGORIES:
        dir_path = knowledge_dir / category
        if not dir_path.is_dir():
            continue
        indexed = 0
        for filepath in sorted(p for p in dir_path.rglob("*") if p.is_file()):
            if filepath.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            documents = load_single_file(str(filepath))
            documents = clean_documents(
                documents, dedup=True, fuzzy_dedup=False, fuzzy_threshold=0.9
            )
            chunks = split_documents(documents)
            chunks = enhance_documents(chunks)
            for chunk in chunks:
                chunk.metadata["category"] = category
            chunks = tag_chunks_with_knowledge_points(chunks, fallback_category=category)
            indexed += len(manager.add_documents(chunks, collection_name=category))
        counts[category] = indexed
    return counts


async def run_gate(
    golden_path: str | Path = DEFAULT_GOLDEN_PATH,
    limit: int | None = None,
) -> tuple[RetrievalMetrics, list[QueryOutcome], list[tuple[str, str]]]:
    """在黄金集上跑完整检索链。

    Returns:
        ``(指标, 逐条结果, 抛异常的 query 列表)``。

    单条 query 抛异常**不再中断整轮** —— 之前一个异常会让门禁直接崩掉、什么指标都拿不到，
    值班的人只能看到 traceback。现在它被记成一条"空结果 + 错误原因"，门禁照样给出完整
    指标，并在最后单独列出错误、由调用方判为失败。

    这条路径是真实存在的：CI 无 LLM 凭据时 40 条里有 6 条会抛
    ``openai.OpenAIError: Missing credentials``（见 core.llm.get_llm 的说明）。
    """
    from rag.retriever import aretrieve_evidence_with_retry

    queries = load_golden_queries(golden_path, limit=limit)
    outcomes: list[QueryOutcome] = []
    errors: list[tuple[str, str]] = []

    for query, expected in queries:
        try:
            fused, _verdict = await aretrieve_evidence_with_retry(
                query=query,
                k=GATE_K,
                use_rerank=GATE_USE_RERANK,
                max_retries=0,
                use_llm_verify=False,
            )
        except Exception as exc:  # noqa: BLE001 — 门禁要把"任何异常"都算作失败证据
            errors.append((query, f"{type(exc).__name__}: {exc}"))
            outcomes.append(
                QueryOutcome(query=query, expected_category=expected, hit_categories=[])
            )
            continue

        categories = [str(ev.metadata.get("category", "")) for ev in fused.text_evidences]
        outcomes.append(
            QueryOutcome(
                query=query,
                expected_category=expected,
                hit_categories=categories,
            )
        )

    return compute_metrics(outcomes), outcomes, errors


def _build_report(
    metrics: RetrievalMetrics, outcomes: list[QueryOutcome], baseline: dict[str, Any] | None
) -> str:
    lines: list[str] = []
    lines.append("=" * 68)
    lines.append("  检索质量黄金集门禁")
    lines.append("=" * 68)

    current = metrics.as_dict()
    lines.append(f"{'指标':<24}{'当前':>10}{'基线':>10}   判定")
    for name, spec in _METRIC_SPECS.items():
        cur = float(current[name])
        base = float(baseline[name]) if baseline else None
        if base is None:
            verdict = "—"
        else:
            regressed = (
                cur < base - spec.tolerance
                if spec.direction == "higher"
                else (cur > base + spec.tolerance)
            )
            verdict = "退化" if regressed else "通过"
        base_str = f"{base:.4f}" if base is not None else "—"
        lines.append(f"{name:<24}{cur:>10.4f}{base_str:>10}   {verdict}")
    lines.append("")

    misses = [o for o in outcomes if o.first_correct_rank != 1]
    if misses:
        lines.append(f"首条未命中目标学科的查询（{len(misses)} 条）：")
        for outcome in misses:
            got = outcome.hit_categories[0] if outcome.hit_categories else "（空）"
            lines.append(
                f"  - {outcome.query[:34]:<34} 期望 {outcome.expected_category:<22} 实际 {got}"
            )
        lines.append("")

    empty = [o for o in outcomes if not o.hit_categories]
    if empty:
        lines.append(f"[严重] 返回空证据的查询（{len(empty)} 条）：")
        for outcome in empty:
            lines.append(f"  - {outcome.query[:50]}")
        lines.append("")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检索质量黄金集回归门禁")
    parser.add_argument("--golden", default=DEFAULT_GOLDEN_PATH, help="黄金集 jsonl 路径")
    parser.add_argument("--baseline", default=DEFAULT_BASELINE_PATH, help="基线 json 路径")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 条（抽查用）")
    parser.add_argument("--update-baseline", action="store_true", help="重录基线")
    parser.add_argument("--keep-index", action="store_true", help="保留临时索引目录（调试用）")
    parser.add_argument("--verbose", action="store_true", help="打印 INFO 日志")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    tmp_dir = tempfile.mkdtemp(prefix="retrieval_gate_")
    try:
        configure_for_gate(tmp_dir)
        start = time.perf_counter()
        counts = build_index()
        index_seconds = time.perf_counter() - start
        total = sum(counts.values())
        if total == 0:
            print("[错误] 索引为空 —— knowledge/ 目录缺失或全部解析失败", file=sys.stderr)
            return 2
        print(f"索引就绪：{total} chunks（{index_seconds:.1f}s）  {counts}")

        # 必须等 HNSW 落盘，否则会把 Chroma 的间歇性竞态误判成检索退化
        ready = wait_for_index_ready(sorted(counts))
        slow = {name: tries for name, tries in ready.items() if tries}
        if slow:
            print(f"[提示] 以下集合需要重试才可查询（Chroma 落盘竞态）：{slow}")

        start = time.perf_counter()
        metrics, outcomes, errors = asyncio.run(run_gate(args.golden, limit=args.limit))
        query_seconds = time.perf_counter() - start

        baseline: dict[str, Any] | None = None
        baseline_path = Path(args.baseline)
        if baseline_path.exists() and not args.update_baseline:
            baseline = json.loads(baseline_path.read_text(encoding="utf-8")).get("metrics")

        print(_build_report(metrics, outcomes, baseline))
        print(f"索引 {index_seconds:.1f}s / 检索 {query_seconds:.1f}s")

        if errors:
            print(f"\n[严重] {len(errors)} 条 query 抛异常（已按空结果计入指标）：")
            for query, reason in errors[:10]:
                print(f"  - {query[:38]:<38} {reason[:70]}")
            if len(errors) > 10:
                print(f"  … 另有 {len(errors) - 10} 条")

        payload = {
            "_meta": {
                "note": "由 evaluation.retrieval_gate 生成；改动检索链后请用 --update-baseline 重录并在 PR 说明原因",
                "embedding": "USE_FAKE_EMBEDDING (deterministic hashing)",
                "rerank_enabled": GATE_USE_RERANK,
                "k": GATE_K,
                "golden_path": str(args.golden),
                "indexed_chunks": total,
                "recorded_at": time.strftime("%Y-%m-%d"),
            },
            "metrics": metrics.as_dict(),
        }

        if args.update_baseline:
            if errors:
                # 带着异常录基线等于把故障固化成"标准"，必须先修
                print(
                    f"\n[拒绝] 有 {len(errors)} 条 query 抛异常，不录基线 —— "
                    "请先修掉异常，否则基线会把故障当成基准。"
                )
                return 2
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            baseline_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(f"基线已更新: {baseline_path}")
            return 0

        if errors:
            # 异常优先于指标退化上报：指标"看起来还行"是因为异常被记成了空结果，
            # 只报退化会把真正的原因盖掉。
            print("门禁未通过：存在抛异常的 query（见上），请先修异常。")
            return 1

        if baseline is None:
            print(f"[提示] 基线不存在（{baseline_path}），跳过对比。用 --update-baseline 生成。")
            return 0

        regressions = compare_to_baseline(metrics.as_dict(), baseline)
        if regressions:
            print("门禁未通过：")
            for item in regressions:
                print(f"  - {item}")
            return 1

        print("门禁通过：所有指标不低于基线。")
        return 0
    finally:
        if not args.keep_index:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
