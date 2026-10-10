"""门禁编排与 CLI（run_gate / main / 报告）。"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, NamedTuple

from ._baseline import (
    build_baseline_payload,
    check_baseline_sanity,
    compare_to_baseline,
    default_baseline_path,
    load_baseline,
)
from ._constants import DEFAULT_GOLDEN_PATH, GATE_K, _effective_category
from ._data import _METRIC_SPECS, QueryOutcome, RerankObservation, RetrievalMetrics, compute_metrics
from ._golden import chapter_of_source, load_golden_queries
from ._index import build_index, configure_for_gate, wait_for_index_ready
from ._modes import (
    GATE_RERANK_MODE_ERROR,
    GATE_USE_REAL_EMBEDDING,
    embedding_mode,
    rerank_backend,
    rerank_mode,
    rerank_requested,
)


class _GateRunResult(NamedTuple):
    """``run_gate`` 的返回值（具名以取代裸 6 元组；对位置解包向后兼容）。"""

    metrics: RetrievalMetrics
    outcomes: list[QueryOutcome]
    errors: list[tuple[str, str]]
    rerank_observations: list[RerankObservation]
    route_contributions: Counter[str]
    query_failures: list[str]


def _observe_query(
    query: str,
    expected: tuple[str, ...],
    expected_kps: tuple[str, ...],
    fused: Any,
    route_contributions: Counter[str],
) -> tuple[QueryOutcome, RerankObservation]:
    """把一条 query 的检索结果折叠成 ``(outcome, rerank 观察)``；顺带累计路由贡献。"""
    categories = [_effective_category(ev.metadata) for ev in fused.text_evidences]
    # 章级知识点：逐条证据的章（来自 source 文件名），按排名顺序排列。
    kp_labels = [chapter_of_source(ev.source) for ev in fused.text_evidences]
    # 路由贡献：每条证据自报的 `recall_routes`（同一文档可被多条路由命中，逐条计入）
    for ev in fused.text_evidences:
        for route in str(ev.metadata.get("recall_routes") or "").replace("|", ",").split(","):
            if route.strip():
                route_contributions[route.strip()] += 1
    # 记录 rerank 是否真的生效：rerank_score > 0 是「rerank 步骤确实跑过」的可靠信号
    # （真/假 rerank 都会写 >0，只有「跳过 / 异常降级」才写 0.0）。
    observation = RerankObservation(
        has_evidence=bool(fused.text_evidences),
        has_rerank_score=any(ev.rerank_score > 0 for ev in fused.text_evidences),
        rerank_used=bool(fused.metadata.get("rerank_used")),
        # ★ B2：新字段缺 ⇒ ""（未知，不回填）。
        rerank_status=str(fused.metadata.get("rerank_status", "") or ""),
    )
    outcome = QueryOutcome(
        query=query,
        expected_categories=expected,
        hit_categories=categories,
        expected_knowledge_points=list(expected_kps),
        hit_knowledge_points=kp_labels,
    )
    return outcome, observation


async def run_gate(
    golden_path: str | Path = DEFAULT_GOLDEN_PATH,
    limit: int | None = None,
) -> _GateRunResult:
    """在黄金集上跑完整检索链。

    Returns:
        ``_GateRunResult``（字段顺序与旧的 6 元组一致，故位置解包仍可用）：
        ``(指标, 逐条结果, 抛异常的 query 列表, rerank 观察列表, 路由贡献计数, 查询失败记录)``。
        观察列表供 ``_assert_route_preconditions`` 判定 rerank 是否真的执行了（反静默回退）；
        路由贡献计数是 ``"集合:路由" → 出现在最终证据里的次数``，用于回答
        「13 条召回路由里谁在干活、谁空转」—— 此前只能靠临时脚本统计。
        ★ 第 6 项是**整轮**收割下来的 `query_failures`（B7 每条 query 前 reset，
        故进程级列表结束时只剩最后一条 query —— 消费方必须读这份累计值，
        不能再去读 manager 的实时列表，否则「每条 query 前清空」会把前面几条的故障抹掉）。

    单条 query 抛异常**不再中断整轮** —— 之前一个异常会让门禁直接崩掉、什么指标都拿不到，
    值班的人只能看到 traceback。现在它被记成一条"空结果 + 错误原因"，门禁照样给出完整
    指标，并在最后单独列出错误、由调用方判为失败。

    这条路径是真实存在的：CI 无 LLM 凭据时 40 条里有 6 条会抛
    ``openai.OpenAIError: Missing credentials``（见 core.llm.get_llm 的说明）。
    """
    from rag.common.vectorstore import get_vector_store_manager
    from rag.retrieval.retriever import aretrieve_evidence_with_retry

    queries = load_golden_queries(golden_path, limit=limit)
    outcomes: list[QueryOutcome] = []
    errors: list[tuple[str, str]] = []
    rerank_observations: list[RerankObservation] = []
    route_contributions: Counter[str] = Counter()

    _mgr = get_vector_store_manager()
    # ★ 逐条 query 收割下来的失败记录（供末轮 `unexpected_query_failures` 比对）。
    #   起点先把**进入本函数之前**已经记录的失败收进累计值（建索引 / `wait_for_index_ready`
    #   的探针查询都会记）—— 第一条 query 的 reset 会把实时列表清空，
    #   不先收 = 把那些故障从门禁的检查里抹掉（静默丢失，正是 B7 要消灭的东西）。
    run_query_failures: list[str] = list(_mgr.query_failures)

    for query, expected, expected_kps in queries:
        # ★ B7 的 reset 调用点 ①：每条 query 之前清空进程级失败记录，**紧接着在
        #   `finally` 里收割进 `run_query_failures`**。两句必须成对出现 ——
        #   只 reset 不收割 = 把「前面那几条 query 的索引故障」直接扔掉（比不修更静默）；
        #   只收割不 reset = 每条都从第 1 条开始重复计数。
        #   `_query_failures` 是 append-only 的进程级列表，不 reset 就无法定位
        #   「到底是哪条 query 把集合查坏了」。
        _mgr.reset_query_failures()
        try:
            fused, _verdict = await aretrieve_evidence_with_retry(
                query=query,
                k=GATE_K,
                # 传「调用方是否要求重排」——disabled 态要求了、但部署开关会短路它
                use_rerank=rerank_requested(),
                max_retries=0,
                use_llm_verify=False,
            )
        except Exception as exc:  # noqa: BLE001 — 门禁要把"任何异常"都算作失败证据
            errors.append((query, f"{type(exc).__name__}: {exc}"))
            outcomes.append(
                QueryOutcome(
                    query=query,
                    expected_categories=expected,
                    hit_categories=[],
                    expected_knowledge_points=list(expected_kps),
                )
            )
            rerank_observations.append(RerankObservation(False, False, False))
            # ★ `finally` 在 `continue` 生效**之前**执行 ⇒ 异常路径的失败记录同样被收割。
            continue
        finally:
            run_query_failures.extend(_mgr.query_failures)

        outcome, observation = _observe_query(
            query, expected, expected_kps, fused, route_contributions
        )
        outcomes.append(outcome)
        rerank_observations.append(observation)

    return _GateRunResult(
        compute_metrics(outcomes),
        outcomes,
        errors,
        rerank_observations,
        route_contributions,
        run_query_failures,
    )


def _check_rerank_execution(
    mode: str, with_evidence: list[RerankObservation], reranked_count: int, used_count: int
) -> list[str]:
    """rerank 三态下 ``rerank_score`` / ``rerank_used`` 应处的位置（两个静默失效点）。"""
    violations: list[str] = []
    if mode == "on":
        # ``on``：有非空证据的 query 里**至少有一条** ``rerank_score > 0``。抓到「rerank
        # 一条都没执行」的静默回退（``depth.skip_rerank`` 被错误全局置 True，或 reranker
        # 异常降级写 0.0）。**不能用「每条都必须 >0」**：short 查询走 SHALLOW_DEPTH 会
        # **有意**跳过 rerank（省延迟，见 query_classifier），rerank_score 为 0 属预期。
        if with_evidence and not reranked_count:
            violations.append(
                f"rerank 路由开启，但 {len(with_evidence)} 条有证据的 query 里没有一条 "
                "rerank_score > 0 —— rerank 疑似完全没执行（depth.skip_rerank 被错误全局置 True，"
                "或 reranker 异常降级）"
            )
    else:
        # ``off`` / ``disabled``：所有证据 ``rerank_score`` 全为 0（反向验证：rerank 关不掉）。
        # ``disabled`` 是「要求了重排但部署关掉」的生产关闭态，若出现 ``rerank_score > 0``，
        # 说明**部署开关失效**。``rerank_used`` 必须全 False（守其自报失真）。
        if reranked_count:
            violations.append(
                f"rerank 路由为 {mode}，却有 {reranked_count} 条 query 证据里出现 "
                "rerank_score > 0 —— rerank 疑似被静默打开"
            )
        if used_count:
            violations.append(
                f"rerank 路由为 {mode}，却有 {used_count} 条 query 自报 rerank_used=True —— "
                "rerank_used 失真（应为 False），检查重排阶段是否绕过了部署开关"
            )
    return violations


def _check_rerank_status(mode: str, with_evidence: list[RerankObservation]) -> list[str]:
    """``rerank_status``（tier-0 原文）与派生 ``rerank_used`` 必须一致（状态已知时）。"""
    violations: list[str] = []
    # ★ B2：`off`/`degraded`/`failed` 永不得与 `rerank_used=True` 并存 ⇒ 守「未执行重排(off)
    #   不得被误报为重排成功」这条验收。缺字段（老链路 `rerank_status==""`）按未知跳过。
    known = [o for o in with_evidence if o.rerank_status]
    status_mismatch = sum(1 for o in known if o.rerank_used != (o.rerank_status == "success"))
    if status_mismatch:
        violations.append(
            f"{status_mismatch} 条 query 的 rerank_used 与其 rerank_status 派生值不一致 "
            f"（已知状态 {sorted({o.rerank_status for o in known})}）—— "
            "rerank_used 必须是 rerank_status==success 的派生量"
        )
    if mode in ("off", "disabled"):
        bogus_success = sum(1 for o in known if o.rerank_status == "success")
        if bogus_success:
            violations.append(
                f"rerank 路由为 {mode}，却有 {bogus_success} 条 query 的 rerank_status=success "
                "—— 未执行重排被误报为重排成功（B2 验收：off/disabled 不得出 success）"
            )
    return violations


def _check_signal_agreement(with_evidence: list[RerankObservation]) -> list[str]:
    """与 mode 无关的交叉验证：``rerank_score > 0`` 与 ``rerank_used`` 两信号必须一致。"""
    inconsistent = sum(1 for o in with_evidence if o.has_rerank_score and not o.rerank_used)
    if inconsistent:
        return [
            f"{inconsistent} 条 query 出现 rerank_score > 0 但 rerank_used=False —— "
            "两个信号自相矛盾，rerank_used 自报值失真"
        ]
    return []


def _assert_route_preconditions(rerank_observations: list[RerankObservation]) -> list[str]:
    """校验「本次运行声称的路由前提真的成立」，返回违反描述列表；空 = 通过。

    这是「验证，而不是假设」的落地：门禁不只比指标，还要证明它声称跑的那条路由
    **真的被执行了**，否则会出现「rerank 路由跑通、指标对上，但 rerank 根本没发生」
    的静默回退 —— 最危险的一类假绿。

    四条断言（对应四个静默失效点）：

    - ``on``：有非空证据的 query 里**至少有一条** ``rerank_score > 0``。
      抓到「rerank 一条都没执行」的静默回退（``depth.skip_rerank`` 被错误全局置 True，
      或 reranker 异常降级写 0.0）。**不能用「每条都必须 >0」**：short 查询走
      SHALLOW_DEPTH 会**有意**跳过 rerank（省延迟，见 query_classifier），它们的
      rerank_score 为 0 属预期，而非失效。
    - ``off`` / ``disabled``：所有证据 ``rerank_score`` 全为 0（反向验证：rerank 关不掉）。
      ``disabled`` 这条尤其关键 —— 它是「要求了重排但部署关掉」的生产关闭态，
      若这里出现 ``rerank_score > 0``，说明**部署开关失效**。
    - ``off`` / ``disabled``：``rerank_used`` 全为 False。这条专门守 ``rerank_used``
      自报失真（曾出现：开关关掉后链路仍返回 ``rerank_used=True``）。
    - 真实 embedding：``settings.USE_FAKE_EMBEDDING`` 必须为 False（configure_for_gate
      被改坏时，真实 embedding 会静默退回哈希假 embedding）。

    另有一条与 mode 无关的交叉验证：``rerank_score > 0`` 却自报 ``rerank_used=False``
    = 两个信号自相矛盾。
    """
    from core.settings import settings

    # 只关心有非空证据的 query：空结果本就没有 rerank_score，属预期而非失效。
    with_evidence = [o for o in rerank_observations if o.has_evidence]
    reranked_count = sum(1 for o in with_evidence if o.has_rerank_score)
    used_count = sum(1 for o in with_evidence if o.rerank_used)
    mode = rerank_mode()

    violations: list[str] = []
    violations += _check_rerank_execution(mode, with_evidence, reranked_count, used_count)
    violations += _check_rerank_status(mode, with_evidence)
    violations += _check_signal_agreement(with_evidence)

    if GATE_USE_REAL_EMBEDDING and settings.USE_FAKE_EMBEDDING:
        violations.append(
            "GATE_USE_REAL_EMBEDDING=1 但 settings.USE_FAKE_EMBEDDING 仍为 True —— "
            "真实 embedding 静默退回哈希假 embedding（configure_for_gate 被改坏）"
        )

    return violations


def _report_header() -> list[str]:
    """报告抬头：标题 + 路由口径（各路由指标不可互比，报告必须自证口径）。"""
    _rerank_label = {
        "off": "off",
        "on": f"on ({rerank_backend()})",
        "disabled": "disabled (requested, deployment off)",
    }[rerank_mode()]
    return [
        "=" * 68,
        "  检索质量黄金集门禁",
        f"  路由 embed={embedding_mode()}  rerank={_rerank_label}   k={GATE_K}",
        "=" * 68,
    ]


def _report_metric_table(metrics: RetrievalMetrics, baseline: dict[str, Any] | None) -> list[str]:
    """逐指标「当前 / 基线 / 判定」表。"""
    current = metrics.as_dict()
    lines = [f"{'指标':<24}{'当前':>10}{'基线':>10}   判定"]
    for name, spec in _METRIC_SPECS.items():
        cur = float(current[name])
        # 基线里可能没有这一项（新增指标 / 老基线未重录）—— 显示「—」而非硬取，
        # 否则 `baseline[name]` 会直接 KeyError 崩掉整轮报告。
        raw_base = baseline.get(name) if baseline else None
        base = float(raw_base) if raw_base is not None else None
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
    return lines


def _report_query_issues(outcomes: list[QueryOutcome]) -> list[str]:
    """首条未命中 + 返回空证据两类问题查询。"""
    lines: list[str] = []
    misses = [o for o in outcomes if o.first_correct_rank != 1]
    if misses:
        lines.append(f"首条未命中目标学科的查询（{len(misses)} 条）：")
        for outcome in misses:
            got = outcome.hit_categories[0] if outcome.hit_categories else "（空）"
            # 多值期望用 `/` 连接展示，如 `data_structure/questions`
            expected_label = "/".join(outcome.expected_categories)
            lines.append(f"  - {outcome.query[:34]:<34} 期望 {expected_label:<22} 实际 {got}")
        lines.append("")

    empty = [o for o in outcomes if not o.hit_categories]
    if empty:
        lines.append(f"[严重] 返回空证据的查询（{len(empty)} 条）：")
        for outcome in empty:
            lines.append(f"  - {outcome.query[:50]}")
        lines.append("")
    return lines


def _report_route_contributions(route_contributions: Counter[str]) -> list[str]:
    """路由贡献度：回答「13 条召回路由里谁在干活、谁空转」（此前只能靠临时脚本统计）。"""
    # ⚠️ 零贡献**不等于**该路由无用：黄金集全是概念题，`code_meta` / `exercise_meta` /
    # `answer_meta` / `table_meta` 本就只在对应场景（代码/习题/答案/表格查询）才命中。
    lines = [
        f"路由贡献度（最终证据里各路由出现次数，合计 {sum(route_contributions.values())} 次）："
    ]
    for name, count in route_contributions.most_common():
        lines.append(f"  {count:>5}  {name}")
    if not route_contributions:
        lines.append("  （无）")
    lines.append("")
    return lines


def _build_report(
    metrics: RetrievalMetrics,
    outcomes: list[QueryOutcome],
    baseline: dict[str, Any] | None,
    route_contributions: Counter[str] | None = None,
) -> str:
    lines: list[str] = []
    lines += _report_header()
    lines += _report_metric_table(metrics, baseline)
    lines += _report_query_issues(outcomes)
    if route_contributions is not None:
        lines += _report_route_contributions(route_contributions)
    return "\n".join(lines)


def unexpected_query_failures(failures: list[str], built: set[str]) -> list[str]:
    """从查询失败记录里挑出**真正算故障**的那些。

    检索链会查询 `answers` 等**可选集合** —— 它们不在 ``DEFAULT_CATEGORIES`` 里、
    本来就不存在，查询失败是**设计内的降级**（多路召回容忍单路失败）。
    只有「本次**真正建过索引**却仍然查不了」才是索引故障。

    判据用 `built` 集合过滤，**不去匹配错误字符串** —— 后者依赖 Chroma 的文案，
    升级即失效（本项目已有「靠字符串猜语义」的教训）。

    Args:
        failures: `VectorStoreManager.query_failures`，形如 `"集合: 异常类型"`。
        built: 本次实际建过索引的集合名。

    Returns:
        属于已建集合的失败记录；空列表表示没有索引故障。
    """
    return [f for f in failures if f.split(":", 1)[0] in built]


def report_retrieval_anomalies(failures: list[str], errors: list[tuple[str, str]]) -> int | None:
    """统一报出检索期的异常情况；需要提前退出时返回退出码，否则返回 None。

    ★ 检索期查询异常 = 索引坏了，**指标毫无意义**，必须在比对基线之前拦下。
    检索链对单路失败是**静默降级**（返回 `[]`），所以这不会被 `errors` 捕获 ——
    实测后果：HNSW 段文件未落盘时，集合可能通过建索引期的就绪检查、却在检索期失败，
    于是 `hit@1` 从 0.95 掉到 **0.725**，门禁却把它当成「检索质量退化」报出来。
    那既可能是**巨大的假回归**，也可能**掩盖真实退化** —— 两种都比「明确说不知道」更糟。

    ★ 抽成函数的原因不只是复用：`main()` 已达 126 行（规范 1 上限 60，结构规模棘轮冻结），
    **再加代码会被棘轮拦下** —— 那是棘轮按设计工作，正确反应是抽出来而不是放宽基线。
    """
    if failures:
        affected = sorted({f.split(":", 1)[0] for f in failures})
        print(
            f"\n[失败] 已建索引的集合中有 {len(failures)} 次检索期查询异常，"
            f"**指标不可信**，已跳过基线比对。\n"
            f"  受影响集合：{affected}\n"
            f"  典型原因：Chroma HNSW 段文件未落盘 —— 集合在建索引期的就绪检查**通过**，\n"
            f"  却在检索期失败，检索链静默返回空。此时指标只反映「索引坏了」。\n"
            f"  处理：**重跑门禁**。",
            file=sys.stderr,
        )
        return 2

    if errors:
        print(f"\n[严重] {len(errors)} 条 query 抛异常（已按空结果计入指标）：")
        for query, reason in errors[:10]:
            print(f"  - {query[:38]:<38} {reason[:70]}")
        if len(errors) > 10:
            print(f"  … 另有 {len(errors) - 10} 条")
    return None


class _Rejected(Exception):
    """门禁配置 / 前提错误 → 退出码 2（非指标退化）。"""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="检索质量黄金集回归门禁")
    parser.add_argument("--golden", default=DEFAULT_GOLDEN_PATH, help="黄金集 jsonl 路径")
    parser.add_argument(
        "--baseline",
        default=None,
        help="基线 json 路径（不传则按 (embedding, rerank) 组合自动选，见 SUPPORTED_ROUTES）",
    )
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 条（抽查用）")
    parser.add_argument("--update-baseline", action="store_true", help="重录基线")
    parser.add_argument(
        "--force-baseline",
        action="store_true",
        help="跳过重录前的合理性校验（仅在确认指标变化是预期的时候用，见 check_baseline_sanity）",
    )
    parser.add_argument("--keep-index", action="store_true", help="保留临时索引目录（调试用）")
    parser.add_argument("--verbose", action="store_true", help="打印 INFO 日志")
    return parser


def _resolve_baseline_path(args: argparse.Namespace) -> Path:
    """按 (embedding, rerank) 组合或显式 ``--baseline`` 定基线路径；口径非法抛 `_Rejected`。

    ★ 即使用户显式传 ``--baseline``，也要先校验当前组合，避免把 real/fake rerank 混录。
    """
    try:
        auto_baseline_path = Path(default_baseline_path())
    except ValueError as exc:
        raise _Rejected(str(exc)) from exc
    return Path(args.baseline) if args.baseline else auto_baseline_path


def _load_baseline_for_run(args: argparse.Namespace, baseline_path: Path) -> dict[str, Any] | None:
    """读基线并校验口径（``--update-baseline`` 时不读）；口径不符抛 `_Rejected`。"""
    if args.update_baseline:
        return None
    try:
        return load_baseline(baseline_path)
    except ValueError as exc:
        raise _Rejected(str(exc)) from exc


def _build_gate_index() -> tuple[dict[str, int], int, float] | None:
    """建临时索引并等 HNSW 就绪；索引为空返回 None。"""
    start = time.perf_counter()
    counts = build_index()
    index_seconds = time.perf_counter() - start
    total = sum(counts.values())
    if total == 0:
        print("[错误] 索引为空 —— knowledge/ 目录缺失或全部解析失败", file=sys.stderr)
        return None
    print(f"索引就绪：{total} chunks（{index_seconds:.1f}s）  {counts}")

    # 必须等 HNSW 落盘，否则会把 Chroma 的间歇性竞态误判成检索退化
    ready = wait_for_index_ready(sorted(counts))
    slow = {name: tries for name, tries in ready.items() if tries}
    if slow:
        print(f"[提示] 以下集合需要重试才可查询（Chroma 落盘竞态）：{slow}")
    return counts, total, index_seconds


def _update_baseline(
    args: argparse.Namespace,
    metrics: RetrievalMetrics,
    baseline_path: Path,
    errors: list[tuple[str, str]],
    payload: dict[str, Any],
) -> int:
    """重录基线：先拦异常与静默故障，再写盘；返回退出码。"""
    if errors:
        # 带着异常录基线等于把故障固化成"标准"，必须先修
        print(
            f"\n[拒绝] 有 {len(errors)} 条 query 抛异常，不录基线 —— "
            "请先修掉异常，否则基线会把故障当成基准。"
        )
        return 2

    # 合理性校验：拦「静默故障」（不抛异常但指标塌陷），见 check_baseline_sanity。
    suspicious = check_baseline_sanity(metrics, baseline_path)
    if suspicious and not args.force_baseline:
        print(
            f"\n[拒绝] 重录前的合理性校验未通过（{len(suspicious)} 处），**未写盘**：",
            file=sys.stderr,
        )
        for item in suspicious:
            print(f"  - {item}", file=sys.stderr)
        print(
            "\n  先判断这是「故障」还是「预期内的改动」：\n"
            "    · 故障（如 Chroma 索引竞态）→ 复跑一次，指标应回到原量级\n"
            "    · 预期内的改动（改语料 / 改切分 / 改检索链）→ 加 --force-baseline 重录，\n"
            "      并在提交说明里写清为什么指标会变这么多",
            file=sys.stderr,
        )
        return 2

    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    suffix = "（已跳过合理性校验）" if suspicious and args.force_baseline else ""
    print(f"基线已更新: {baseline_path}{suffix}")
    return 0


def _check_result(
    metrics: RetrievalMetrics,
    baseline: dict[str, Any] | None,
    baseline_path: Path,
    errors: list[tuple[str, str]],
) -> int:
    """本轮到结果的退出码：异常优先 → 缺基线 → 比退化。"""
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


def _validate_run(
    rerank_observations: list[RerankObservation],
    query_failures: list[str],
    counts: dict[str, int],
    errors: list[tuple[str, str]],
) -> int | None:
    """路由前提自检 + 检索期异常上报；需提前退出时返回退出码，否则 None。"""
    preconditions = _assert_route_preconditions(rerank_observations)
    if preconditions:
        print("\n[失败] 路由前提自检未通过（反静默回退）：", file=sys.stderr)
        for item in preconditions:
            print(f"  - {item}", file=sys.stderr)
        return 2
    return report_retrieval_anomalies(
        unexpected_query_failures(query_failures, set(counts)), errors
    )


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # 配置先校验：非法 mode 与未登记的路由组合都直接拒绝，不必花一分钟建索引再说。
    if GATE_RERANK_MODE_ERROR:
        print(f"[拒绝] {GATE_RERANK_MODE_ERROR}", file=sys.stderr)
        return 2

    # 基线先读、先校验：口径不对就没必要花一分钟建索引再告诉你。
    try:
        baseline_path = _resolve_baseline_path(args)
        baseline = _load_baseline_for_run(args, baseline_path)
    except _Rejected as exc:
        print(f"[拒绝] {exc}", file=sys.stderr)
        return 2

    tmp_dir = tempfile.mkdtemp(prefix="retrieval_gate_")
    try:
        configure_for_gate(tmp_dir)
        built = _build_gate_index()
        if built is None:
            return 2
        counts, total, index_seconds = built

        start = time.perf_counter()
        result = asyncio.run(run_gate(args.golden, limit=args.limit))
        query_seconds = time.perf_counter() - start

        code = _validate_run(
            result.rerank_observations, result.query_failures, counts, result.errors
        )
        if code is not None:
            return code

        print(_build_report(result.metrics, result.outcomes, baseline, result.route_contributions))
        print(f"索引 {index_seconds:.1f}s / 检索 {query_seconds:.1f}s")

        payload = build_baseline_payload(
            metrics=result.metrics,
            golden_path=args.golden,
            indexed_chunks=total,
            route_contributions=result.route_contributions,
            rerank_observations=result.rerank_observations,
        )

        if args.update_baseline:
            return _update_baseline(args, result.metrics, baseline_path, result.errors, payload)

        return _check_result(result.metrics, baseline, baseline_path, result.errors)
    finally:
        if not args.keep_index:
            shutil.rmtree(tmp_dir, ignore_errors=True)
