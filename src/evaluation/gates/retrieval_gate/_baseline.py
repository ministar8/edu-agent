"""基线 I/O 与退化比对（load_baseline / compare_to_baseline / …）。"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

from evaluation.provenance import build_provenance

from ._constants import GATE_K
from ._data import _METRIC_SPECS, RerankObservation, RetrievalMetrics
from ._modes import (
    GATE_USE_REAL_EMBEDDING,
    GATE_USE_REAL_RERANK,
    SUPPORTED_ROUTES,
    embedding_mode,
    rerank_backend,
    rerank_mode,
)


def default_baseline_path() -> str:
    """按当前 ``(embedding, rerank)`` 组合选基线路径。

    Raises:
        ValueError: 组合未在 ``SUPPORTED_ROUTES`` 登记（由 ``main()`` 转成退出码 2）。
    """
    combo = (embedding_mode(), rerank_mode())
    if combo == ("real", "on") and not GATE_USE_REAL_RERANK:
        raise ValueError(
            "真实 embedding + rerank=on 需要显式设置 GATE_USE_REAL_RERANK=1，"
            "否则会误用 fake rerank，不能录成真实基线。"
        )
    if GATE_USE_REAL_RERANK and combo != ("real", "on"):
        raise ValueError(
            "GATE_USE_REAL_RERANK=1 只适用于真实 embedding + rerank=on，"
            f"当前是 embed={combo[0]} rerank={combo[1]}。"
        )
    path = SUPPORTED_ROUTES.get(combo)
    if path is None:
        supported = ", ".join(f"{e}+{r}" for e, r in sorted(SUPPORTED_ROUTES))
        raise ValueError(
            f"路由组合 embed={combo[0]} rerank={combo[1]} 未登记基线 —— "
            f"已登记：{supported}。该组合要么没有意义，要么尚未定义基线口径。"
        )
    return path


def load_baseline(path: Path) -> dict[str, Any] | None:
    """读基线并**校验口径**；文件不存在返回 None。

    口径校验三项，都必须与本次运行一致：

    - ``_meta.rerank_mode``（三态；旧基线只有布尔 ``rerank_enabled``，做兼容映射）
    - ``_meta.rerank_backend``（``fake`` 或 ``real``；历史基线缺失时兼容放行）
    - ``_meta.embedding_mode``

    少了这一步，不同路由的数字会被拿来互比 —— 那恰恰是最容易得出错误结论的一类
    对比（见 MEMORY 的「基线口径必须一致」）。**embedding 这一项尤其危险**：
    真/假 embedding 之间的差距很大，会被误读成"代码改动带来的改善/退化"。
    历史基线没有这些字段时放行（兼容）。

    Raises:
        ValueError: 口径不匹配。由调用方转成退出码 2（"配置错误"，非"指标退化"）。
    """
    if not path.exists():
        return None

    recorded = json.loads(path.read_text(encoding="utf-8"))
    meta = recorded.get("_meta", {})

    # 优先读三态 `rerank_mode`；旧基线只有布尔 `rerank_enabled`，做兼容映射。
    # 布尔映射不出 `disabled`（它与 `off` 的 RERANK_ENABLED 同为 False），
    # 这正是必须升三态的原因 —— 否则两条路由会被误判成同口径。
    recorded_mode = meta.get("rerank_mode")
    if recorded_mode is None:
        legacy = meta.get("rerank_enabled")
        if legacy is not None:
            recorded_mode = "on" if bool(legacy) else "off"
    if recorded_mode is not None and str(recorded_mode) != rerank_mode():
        raise ValueError(
            f"基线口径不匹配：{path} 记录 rerank_mode={recorded_mode}，"
            f"本次运行是 {rerank_mode()}。三条 rerank 路由的指标不可直接比较 —— "
            "请改用对应路由的基线，或先 `--update-baseline` 重录。"
        )

    recorded_embed = meta.get("embedding_mode")
    recorded_backend = meta.get("rerank_backend")
    if recorded_backend is not None and str(recorded_backend) != rerank_backend():
        raise ValueError(
            f"基线口径不匹配：{path} 记录 rerank_backend={recorded_backend}，"
            f"本次运行是 {rerank_backend()}。真实/假 rerank 的指标不可直接比较 —— "
            "请改用对应路由的基线，或先 `--update-baseline` 重录。"
        )

    recorded_embed = meta.get("embedding_mode")
    if recorded_embed is not None and str(recorded_embed) != embedding_mode():
        raise ValueError(
            f"基线口径不匹配：{path} 记录 embedding_mode={recorded_embed}，"
            f"本次运行是 {embedding_mode()}。真/假 embedding 的指标不可直接比较 "
            "（差异可能全部来自 embedding 本身，而非代码改动）—— "
            "请改用对应路由的基线，或先 `--update-baseline` 重录。"
        )
    return recorded.get("metrics")


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
        if name not in baseline:
            # 基线缺少该项（新增指标 / 老基线未重录）。**不能拿 0.0 当基准** ——
            # 那会让新指标静默「通过」，正是本项目一直在消灭的假绿。
            regressions.append(
                f"基线缺少指标 {name} —— 无法判定，请先 `--update-baseline` 重录"
                "（属配置问题，不是指标退化）"
            )
            continue
        cur = float(current.get(name, 0.0))
        base = float(baseline[name])
        if spec.direction == "higher":
            if cur < base - spec.tolerance:
                regressions.append(f"{name} 退化：{base:.4f} → {cur:.4f}（容差 {spec.tolerance}）")
        elif cur > base + spec.tolerance:
            regressions.append(f"{name} 退化：{base:.4f} → {cur:.4f}（容差 {spec.tolerance}）")

    return regressions


def build_baseline_payload(
    *,
    metrics: RetrievalMetrics,
    golden_path: str | Path,
    indexed_chunks: int,
    route_contributions: Counter[str] | None = None,
    rerank_observations: list[RerankObservation] | None = None,
) -> dict[str, Any]:
    """构造基线 JSON 的载荷（`_meta` 里记录口径，供 `load_baseline` 校验）。

    ``_meta.route_contributions`` 记录本次各路由的贡献条数 —— 它不是**指标**（无方向/容差，
    故不参与退化判定），而是**口径快照**：将来某条路由静默变成 0 贡献时，可与它对比发现。

    ★ ``_meta.rerank_status_counts``（修复批 Important-3，B2 四态送达基线工件）：
      本次逐 query 的 tier-0 重排状态分布（`off`/`success`/`degraded`/`failed`；
      老链路没写该字段的按 ``unknown`` 单列，**不折进任何一态**）。同样是口径快照、
      非指标。此前基线**完全不导出**该状态 ⇒ 「四态已实现」在工件面上零证据
      （实测 9 份基线含该字样 = 0）。★ 本字段自本批起对**新录制**的基线生效；
      历史 9 份基线（含 pre_task9 一代）**没有**这个键，引用时必须区分这两件事。
      `rerank_observations=None` ⇒ 不写该键（没观察 = 没证据，不造空分布冒充「全未知」）。
    """
    payload: dict[str, Any] = {
        "_meta": {
            "note": "由 evaluation.gates.retrieval_gate 生成；改动检索链后请用 --update-baseline 重录并在 PR 说明原因",
            "embedding_mode": embedding_mode(),
            "embedding": (
                "real TEI bge-m3"
                if GATE_USE_REAL_EMBEDDING
                else "USE_FAKE_EMBEDDING (deterministic hashing)"
            ),
            "rerank_mode": rerank_mode(),
            "rerank_backend": rerank_backend(),
            # 知识点口径的粒度载体（见 chapter_of_source）。写进基线以便自证口径。
            "kp_granularity": "chapter(file)",
            # 各路由贡献条数（口径快照，非指标）
            "route_contributions": dict(route_contributions or {}),
            "k": GATE_K,
            "golden_path": str(golden_path),
            "indexed_chunks": indexed_chunks,
            "recorded_at": time.strftime("%Y-%m-%d"),
        },
        "metrics": metrics.as_dict(),
        **build_provenance("src/evaluation/gates/retrieval_gate/_baseline.py"),
    }
    if rerank_observations is not None:
        status_counts: Counter[str] = Counter(
            (o.rerank_status or "unknown") for o in rerank_observations
        )
        payload["_meta"]["rerank_status_counts"] = dict(status_counts)
    return payload


_BASELINE_SANITY_MAX_DELTA = 0.10


def check_baseline_sanity(metrics: RetrievalMetrics, baseline_path: Path) -> list[str]:
    """重录基线前的合理性校验；返回「可疑点」列表（空 = 通过）。

    为什么需要它：`--update-baseline` 原先只拒绝「有 query 抛异常」的情况，而
    **静默返回空不抛异常** —— 实测一次 Chroma 索引竞态让 16/156 条 query 返回空
    （`empty` 0 → 0.1026、`cat@k` 0.7949 → 0.5705），门禁照样把故障态写成了基线，
    复跑才发现。**录制侧的静默失败与判定侧的静默失败同样危险。**

    旧基线不存在、读不出、或口径不一致（`load_baseline` 抛 ValueError）时返回空列表 ——
    此时「偏离」无从谈起，不该拦。调用方可用 `--force-baseline` 覆盖本校验。
    """
    try:
        recorded = load_baseline(baseline_path)
    except ValueError:
        return []
    if not recorded:
        return []

    current = metrics.as_dict()
    problems: list[str] = []

    old_empty = float(recorded.get("empty_result_rate") or 0.0)
    new_empty = current["empty_result_rate"]
    if new_empty > old_empty:
        problems.append(
            f"空结果率上升 {new_empty - old_empty:+.4f}（{old_empty:.4f} → {new_empty:.4f}）"
            " —— 静默返回空是最危险的退化形态；先确认索引健康、再决定是否接受"
        )

    for name, _spec in _METRIC_SPECS.items():
        old = recorded.get(name)
        if old is None or name == "empty_result_rate":
            continue
        delta = abs(float(current[name]) - float(old))
        if delta > _BASELINE_SANITY_MAX_DELTA:
            problems.append(
                f"{name} 偏离旧基线 {delta:.4f}（{float(old):.4f} → {current[name]:.4f}）"
                f" —— 超过 {_BASELINE_SANITY_MAX_DELTA} 的正常改动量级"
            )
    return problems
