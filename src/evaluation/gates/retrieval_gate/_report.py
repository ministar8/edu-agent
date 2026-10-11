"""门禁报告构建（从 _gate.py 拆出，行为等价）。"""

from __future__ import annotations

from collections import Counter
from typing import Any

from ._constants import GATE_K
from ._data import _METRIC_SPECS, QueryOutcome, RetrievalMetrics
from ._modes import embedding_mode, rerank_backend, rerank_mode


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
