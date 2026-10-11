"""检索链阶段级行为追踪：为拆分 `aretrieve_documents` 提供逐阶段等价性证据。

为什么需要它
------------
`aretrieve_documents` 曾是一个 428 行的单体编排函数（现已拆成 `pipeline.py` 里的阶段
函数）。证明这类拆分的无损，**"最终输出一致"不足够** —— 两处错误互相抵消也能得到
同样的输出。阶段级追踪记录
**每个阶段函数的入参与返回值**，把"输出一致"细化为"每一步都一致"，
任何阶段的行为变化都会定位到具体那一步，而不是只告诉你"结果不一样了"。

怎么做到不侵入源码
------------------
被追踪的阶段函数**已经是独立的模块级函数**（`_amulti_route_search` / `dedup_same_section` /
`rerank` / `sentence_window_expand` …），单体函数只是把它们串起来。所以只要在
`rag.retrieval.retriever` 上临时替换这些名字，就能记录"阶段之间的接口"，而不用改一行源码。
这个性质也决定了它对重构友好：**拆分只改变调用点，不改变这些函数的契约**，
因此同一份记录在拆分前后必须逐字匹配。

追踪入口必须与生产一致（2026-09-24 修）
--------------------------------------
本工具原先从 `aretrieve_documents` 进入 —— 那是**文档层**；而 `afuse_documents` /
`averify_evidence` 只在**证据层** `aretrieve_evidence` 里被调用。后果是
`STAGE_TARGETS` 里补的这两个目标**恒为 0 次**：patch 机制正确、符号也确实存在，
只是那段代码在追踪链路上**永远走不到**。

更隐蔽的是它为什么没被发现：验证「机制生效」时用的是 `aretrieve_evidence` 路径
（确能触发 1 次），而录基线用的是 `record_query`（走文档层）——
**验机制的入口 ≠ 录基线的入口**，两边都「通过」，却什么都没覆盖到。
这类缺陷比「补一个指标」更危险：它看着像「已覆盖」，实为新的盲区。

现在统一从 `aretrieve_evidence_with_retry` 进入（**与检索门禁同一个入口**），
链路 = 文档层 8 阶段 + 门面层 3 步（`aretrieve_evidence` → `afuse_documents` →
`averify_evidence`），是原先的**真超集**：`_stage_decompose_query` 在拿到预计算子查询时
会跳过 `decompose`，但 `aretrieve_evidence` 自己会直接调用模块级 `decompose`，
故该阶段仍被追踪到（已实测，非推断）。

刻意不追踪的东西
----------------
- `_safe_to_thread`：它是"把调用挪到线程"的实现细节，不是行为契约。
  重构中合法地改变线程策略不应导致失败。
- 顺序的严格性：阶段内部可能有并发调用（`_amulti_route_search` 走 ThreadPoolExecutor），
  完成次序天然不定。故比对前按 `(阶段名, 入参)` 归一化排序 —— 我们断言的是
  "每个阶段被同样的输入调用、返回同样的输出"，而不是"调用次序"。

用法::

    # 录基线与比对**必须用同一个 --persist-dir**
    python -m evaluation.diagnostics.stage_trace --record     --limit 12 --persist-dir /tmp/idx
    python -m evaluation.diagnostics.stage_trace              --limit 12 --persist-dir /tmp/idx

**必须固定索引目录（实测结论）**：默认模式下每次运行都会新建临时索引，
此时约 10 次里有 1 次会因上游 ANN 边界抖动而超出分级断言（recall 层已只报警，
超出的通常是它下游的阶段）。固定同一个 `--persist-dir` 后，实测 10/10 全部通过。
因此本工具**不适合直接作为 CI 门禁**（那会引入低频假失败），
而是重构期间的**本地诊断与验证工具**：录一次基线，改代码，再比对。

也正因为如此，**基线文件不进仓库** —— 它是某一次特定索引构建的产物，
放进去只会变成一份会过期的、偶尔变红的负债。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any

from evaluation.diagnostics._stage_trace_core import (
    STAGE_TARGETS,
    VOLATILE_RATIO,
    StageTrace,
    compare_traces,
    probe_query_stability,
    record_query,
)

DEFAULT_BASELINE_PATH = "evals/stage_baseline.json"


async def record_all(
    limit: int | None = None,
    *,
    k: int = 5,
    use_rerank: bool = False,
    stable_only: bool = False,
    stable_repeats: int = 3,
) -> tuple[list[StageTrace], list[str]]:
    """录一批 query 的阶段追踪。

    ``stable_only=True`` 时先探测每条 query 的**最终结果**是否可复现，只保留稳定的。
    Returns:
        ``(追踪列表, 被排除的 query 列表)``。
    """
    from evaluation.gates.retrieval_gate import load_golden_queries

    # `load_golden_queries` 返回 (query, category, knowledge_points) 三元组；
    # 这里只要 query。
    queries = [
        q
        for q, _cat, _kps in load_golden_queries(
            "evals/datasets/golden/sample_408.jsonl", limit=limit
        )
    ]
    traces: list[StageTrace] = []
    excluded: list[str] = []
    for query in queries:
        if stable_only:
            stable, _finals = await probe_query_stability(
                query, repeats=stable_repeats, k=k, use_rerank=use_rerank
            )
            if not stable:
                excluded.append(query)
                continue
        traces.append(await record_query(query, k=k, use_rerank=use_rerank))
    return traces, excluded


def _stage_trigger_report(traces: list[StageTrace]) -> str:
    """阶段触发率表。

    为什么工具本身必须打这张表：它此前只打印「比对结果」，而**触发率**才是发现
    「某阶段恒为 0 次」的唯一途径 —— 补了追踪目标但入口走不到时，比对会一路通过，
    因为基线与当前**双方都是 0**。0 次不一定是缺陷（如 `rerank` 在 `use_rerank=False`
    下本就该为 0），所以这里只标出来、由人判断，不自动判失败。
    """
    n = len(traces)
    counter: Counter[str] = Counter()
    for trace in traces:
        for step in trace.steps:
            counter[step.stage] += 1

    names = [stage for stage, _ in STAGE_TARGETS]
    width = max((len(s) for s in names), default=10)
    lines = [f"\n阶段触发率（{n} 条 query，共 {sum(counter.values())} 次阶段调用）："]
    for stage in names:
        got = counter.get(stage, 0)
        note = "  ← 0 次：需确认是「本就该 0」还是「观测盲区」" if got == 0 else ""
        lines.append(f"  {stage:<{width}} {got:>4}/{n}{note}")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检索链阶段级行为追踪")
    parser.add_argument("--baseline", default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--limit", type=int, default=12, help="追踪前 N 条 query")
    parser.add_argument("--record", action="store_true", help="录制基线")
    parser.add_argument(
        "--stable-only",
        action="store_true",
        help="录基线时先探测稳定性，排除最终结果不可复现的 query（强烈建议开启）",
    )
    parser.add_argument(
        "--stable-repeats",
        type=int,
        default=3,
        help="稳定性探测的重复次数（默认 3）",
    )
    parser.add_argument(
        "--volatile-ratio",
        type=float,
        default=VOLATILE_RATIO,
        help=f"recall 层差异超过该比例时在报告里标记（默认 {VOLATILE_RATIO}）",
    )
    parser.add_argument(
        "--persist-dir",
        default=None,
        help="固定索引目录（跨次复用同一个 HNSW 索引）。不传则每次新建临时目录。",
    )
    parser.add_argument("--keep-index", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def _setup_index(tmp_dir: str, own_tmp: bool) -> dict[str, int]:
    """配置并构建（或复用）索引，打印就绪信息，返回各集合 chunk 数。

    为什么允许固定索引目录：Chroma 的 HNSW 是**近似**索引，跨进程重建得到的图
    不一定逐位相同，于是原始召回结果（recall_multi_route*）会有微小差异 ——
    门禁的聚合指标会吸收掉这种差异，但阶段级追踪看得见，表现为"每次跑都有几处不同"。
    复用同一个持久化索引可以把这一层变量消掉，让"阶段级一致"成为可判定的断言。
    """
    from evaluation.gates.retrieval_gate import (
        build_index,
        configure_for_gate,
        wait_for_index_ready,
    )

    configure_for_gate(tmp_dir)
    start = time.perf_counter()
    counts = build_index()
    wait_for_index_ready(sorted(counts))
    print(
        f"索引就绪：{sum(counts.values())} chunks（{time.perf_counter() - start:.1f}s）"
        f"{'（复用 ' + tmp_dir + '）' if not own_tmp else ''}"
    )
    return counts


def _print_trace_summary(traces: list[StageTrace], excluded: list[str], elapsed: float) -> None:
    """打印：追踪条数 / 平均阶段调用数 + 阶段触发率表 + 被排除的不可复现 query。"""
    print(
        f"追踪 {len(traces)} 条 query（{elapsed:.1f}s），"
        f"平均每条约 {sum(len(t.steps) for t in traces) / max(len(traces), 1):.1f} 个阶段调用"
    )
    print(_stage_trigger_report(traces))
    if excluded:
        print(
            f"[已排除] {len(excluded)} 条 query 的最终结果不可复现"
            f"（上游 ANN 边界抖动传导，非本项目缺陷）："
        )
        for query in excluded[:6]:
            print(f"    {query[:44]}")


def _build_payload(traces: list[StageTrace]) -> dict[str, Any]:
    """把追踪结果打包成基线 payload。"""
    return {
        "_meta": {
            "note": "由 evaluation.diagnostics.stage_trace 生成；拆分检索链后必须与本文件逐阶段一致",
            "embedding": "USE_FAKE_EMBEDDING (deterministic hashing)",
            "rerank_enabled": False,
            "k": 5,
            "n_queries": len(traces),
            "recorded_at": time.strftime("%Y-%m-%d"),
        },
        "traces": [t.as_dict() for t in traces],
    }


def _compare_and_report(
    saved: list[dict[str, Any]], current: list[dict[str, Any]], volatile_ratio: float
) -> int:
    """逐条比对基线并打印差异；返回退出码（0 通过 / 1 有严格差异）。"""
    total_failures = 0
    total_advisories = 0
    max_delta = 0
    for exp, act in zip(saved, current, strict=True):
        result = compare_traces(exp, act, volatile_ratio=volatile_ratio)
        max_delta = max(max_delta, result.max_volatile_delta)
        if result.failures:
            total_failures += len(result.failures)
            print(f"\n[失败] {exp['query'][:44]}")
            for item in result.failures[:6]:
                print(f"    {item}")
        if result.advisories:
            total_advisories += len(result.advisories)
            print(f"\n[无法判定] {exp['query'][:44]}")
            for item in result.advisories[:4]:
                print(f"    {item}")

    if total_failures:
        print(f"\n阶段级比对未通过：{total_failures} 处严格差异")
        if total_advisories:
            print(f"（另有 {total_advisories} 处因上游 ANN 抖动无法判定）")
        return 1

    if total_advisories:
        print(
            f"\n阶段级比对通过：0 处严格差异；"
            f"{total_advisories} 处因上游 ANN 抖动无法判定（最大文档差异 {max_delta}）"
        )
        return 0

    print("\n阶段级比对通过：所有阶段入参与返回值逐条一致。")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    own_tmp = args.persist_dir is None
    tmp_dir = args.persist_dir or tempfile.mkdtemp(prefix="stage_trace_")
    try:
        _setup_index(tmp_dir, own_tmp)

        start = time.perf_counter()
        traces, excluded = asyncio.run(
            record_all(
                limit=args.limit,
                stable_only=args.stable_only,
                stable_repeats=args.stable_repeats,
            )
        )
        _print_trace_summary(traces, excluded, time.perf_counter() - start)

        payload = _build_payload(traces)
        baseline_path = Path(args.baseline)
        if args.record:
            baseline_path.parent.mkdir(parents=True, exist_ok=True)
            baseline_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
            )
            print(f"基线已写入 {baseline_path}")
            return 0

        if not baseline_path.exists():
            print(f"[提示] 基线不存在（{baseline_path}），用 --record 生成。")
            return 0

        saved = json.loads(baseline_path.read_text(encoding="utf-8"))["traces"]
        if len(saved) != len(payload["traces"]):
            print(f"[错误] 条数不一致：基线 {len(saved)} vs 当前 {len(payload['traces'])}")
            return 2

        return _compare_and_report(saved, payload["traces"], args.volatile_ratio)
    finally:
        # 只清理自己创建的临时目录；--persist-dir 指定的目录归调用方管
        if own_tmp and not args.keep_index:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
