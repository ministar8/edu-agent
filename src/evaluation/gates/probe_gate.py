"""探针门禁：把「探针表」的目标 chunk 存活层级做成**可判定**的回归门禁。

为什么需要它（`docs/RETRIEVAL_PLAN.md` §3⑦）
--------------------------------------------
`retrieval_gate` 的 `kp_*` 是**章级**（`chapter_of_source` 只看文件名），因此
**测不到「小节级细节是否进了证据」** —— 例：「磁盘空闲空间管理」的正确 chunk 在
`04_文件管理.md :: 6.2空闲表法`，只要**同文件的任意** chunk 进了证据，`kp_hit@k` 就算命中。
于是这类缺陷可以长期藏在「门禁全绿」后面。

`candidate_trace` 能看见它，但它是**诊断工具**：跑生产索引（**无就绪屏障**，会间歇性撞
Chroma「Nothing found on disk」）、没有基线、没有退出码 —— **不可当门禁用**。

本模块把探针表变成门禁：跑在**临时索引 + 就绪屏障**上，对每条 probe 记录
**目标 chunk 在哪一层丢失**，并与基线比较。

★ **语料边界（2026-10-13 重测 —— 旧版「索引全是 legacy、零 L1/L2/L3」自 2026-10-10 起已失效）**：
**索引侧已经覆盖分层**：``retrieval_gate.build_index()`` 改用 ``rag.ingest_layers.build_all()``，
按生产顺序聚合 basic(L1) → advanced(L2) → exams+exam_practice(L3) → code → learning_paths
（``ingest_layers/__init__.py:29-59``），实测 2026 chunk，与生产库**逐位相等**
（``chroma_db/chroma.sqlite3`` 的 ``count(embeddings)`` 同为 2026）。
但**探针侧没跟上**：5 条 probe 的 ``expect_source`` = 4 条 L1 ``basic/``
（``data_structure/08_search.md`` · ``operating_system/04_file.md`` ×2 ·
``computer_organization/02_representation.md``）+ 1 条 ``code/operating_system``，
**没有一条指向 L2 ``advanced/`` 或 L3 ``exams/``**。
⇒ 覆盖限制仍在，但**原因换了**：不是「索引里没有那些层」，而是「探针没打那些层」——
补探针即可解除，不必动索引。旧结论里的 L1 部分也已不成立（``#4``/``#9``/``#17``/``#19``
正是 L1 小节级探针）。源头：``74b9eb5``「探针表改指新语料」只同步了路径串、没改这段结论。

判据为什么是「管线序」而不是「是否 survived」
--------------------------------------------
`dropped_by` 的取值**有序**（见 `probe_tracing.DROP_REASONS`）：

    not_recalled < section_dedup < rrf_threshold < rerank_topn
                 < rel_threshold < window_expand < survived

「前进一层」与「后退一层」**都是信息**。若只断言 `survived`，像 `#9` 从
`rrf_threshold` 前进到 `rerank_topn`（阈值层已修好、卡在下一层）这种**真实的进步**
会被判成「没变」—— 而那正是 §3⑦ 要测的东西。

★ **退 1 级只告警、不判退化**（`_STAGE_JITTER_TOLERANCE`，2026-10-13 加）：`dropped_by`
是**离散标签**，拿不到 `retrieval_gate` 那种连续容差，而坐在层边界上的目标会被检索侧的
**并列打破**推过阈值（归因见 `docs/ARCHITECTURE_RETRIEVAL.md` §6.3(b)：下游按分数单键排序处
如 `dedup_same_section`，并列次序受**并发路由完成次序**影响；该节实测 **HNSW 图本身确定**）
—— 实测同码、同语料、同基线连跑 3 次，`#18` 出现 1 次 `rerank_topn(3) → rrf_threshold(2)`
（恰好退 1 级）⇒ 假红 exit 1。故退 ≤1 级只告警、退 ≥2 级才判退化；告警行走 stderr，不静默。
（★ 本次翻动只做了现象取证，未单独归因到 §6.3(b) 那条链。）

用法::

    # 权威路由（真实 embedding + 真实 TEI rerank）
    GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1 \
        PYTHONPATH=src python -m evaluation.gates.probe_gate

    ... --update-baseline     # 重录基线（需说明为什么变化可接受）
    ... --json                # 机器可读
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from evaluation.gates import retrieval_gate as RG
from evaluation.probe_tracing import DROP_REASONS, load_probes, trace_probe

logger = logging.getLogger(__name__)

DEFAULT_PROBE_PATH = "evals/datasets/golden/retrieval_probes.jsonl"
DEFAULT_BASELINE_PATH = "evals/baselines/probe_baseline.json"

# 存活层级排序：**下标越大 = 目标存活得越久 = 越好**。
# 直接复用 `probe_tracing.DROP_REASONS` —— 它已经是管线顺序，**不要另建一份**
# （两份顺序迟早漂移，而漂移后门禁会静默给出反向判定）。
_STAGE_INDEX: dict[str, int] = {reason: i for i, reason in enumerate(DROP_REASONS)}

# ★ 层序抖动容差（2026-10-13 实测后加）。`dropped_by` 是**离散标签**，拿不到
#   `retrieval_gate` 那种连续容差（`_METRIC_SPECS`：category_*/kp_* 0.02、count 0.5），
#   而它由「目标在哪一层被截断」推导 —— 坐在层边界上的目标会被检索侧的**并列打破**
#   推过阈值（归因见 `docs/ARCHITECTURE_RETRIEVAL.md` §6.3(b)：下游按分数单键排序处如
#   `dedup_same_section`，其并列次序受**并发路由完成次序**影响；该节实测 HNSW 图本身
#   是确定的 ⇒ 别把账记到 HNSW 上）。实测：同码、同语料、同基线连跑 3 次，probe #18
#   出现 1 次 `rerank_topn(3) → rrf_threshold(2)`，恰好退 1 级 ⇒ 假红 exit 1（★ 这次翻动
#   只做了现象取证，**未单独归因**到 §6.3(b) 那条链）。
#   ⇒ 退 1 级记**告警不失败**，退 ≥2 级才判退化。代价：真实的「退一级」会被放过，
#   靠告警行留痕（不是静默）；要更严就配合多次取样取最差。
_STAGE_JITTER_TOLERANCE = 1


def _stage_index(dropped_by: str) -> int:
    """把 `dropped_by` 映射成可比较的进度值；未知取值按最差处理并告警。"""
    idx = _STAGE_INDEX.get(dropped_by)
    if idx is None:
        # 未知取值按比「not_recalled(0)」更差处理（-1）—— 宁可误报退化，不可漏报。
        logger.warning("未知的 dropped_by=%r —— 按最差（-1）处理，请检查 probe_tracing", dropped_by)
        return -1
    return idx


def run_probes(probe_path: str, *, k: int = 5) -> list[dict[str, Any]]:
    """在**临时索引 + 就绪屏障**上跑探针表，返回每条 probe 的观测。

    返回项的 `stages` 保留逐层排名 —— 基线只比 `dropped_by`，
    但出问题时靠它定位「是哪一层变了」。
    """
    tmp_dir = tempfile.mkdtemp(prefix="probe_gate_")
    RG.configure_for_gate(tmp_dir)
    counts = RG.build_index()
    if not counts:
        raise RuntimeError("临时索引为空 —— knowledge/ 目录缺失或全部解析失败")
    RG.wait_for_index_ready(sorted(counts))

    probes = load_probes(probe_path)
    if not probes:
        raise RuntimeError(f"探针表为空: {probe_path}")

    out: list[dict[str, Any]] = []
    for probe in probes:
        result = asyncio.run(trace_probe(probe, k=k, use_rerank=True))
        out.append(
            {
                "id": probe.id,
                "query": probe.query,
                "target": probe.target,
                "dropped_by": result.dropped_by,
                "stages": [{"key": s.key, "count": s.count, "rank": s.rank} for s in result.stages],
                "note": result.rerank_note,
                "rerank_scored": result.rerank_scored,
            }
        )
    return out


def _meta() -> dict[str, str]:
    """本次运行的口径。基线必须与之一致，否则数字不可比。"""
    return {
        "embedding_mode": RG.embedding_mode(),
        "rerank_mode": RG.rerank_mode(),
        "rerank_backend": RG.rerank_backend(),
    }


def load_baseline(path: Path) -> dict[int, str] | None:
    """读基线并**校验口径**；文件不存在返回 None。

    口径（embedding / rerank 三态 / rerank 实现）不一致时直接拒绝 ——
    否则会把「换了一条路由」误读成「检索退化」。
    """
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    recorded = payload.get("_meta") or {}
    current = _meta()
    for key, value in current.items():
        if recorded.get(key) is not None and str(recorded[key]) != value:
            raise ValueError(
                f"基线口径不匹配：{path} 记录 {key}={recorded[key]}，本次是 {value}。"
                "请用同一条路由，或先 --update-baseline 重录。"
            )
    return {int(item["id"]): str(item["dropped_by"]) for item in payload.get("probes", [])}


def build_baseline_payload(observations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "_meta": {
            **_meta(),
            "probe_path": DEFAULT_PROBE_PATH,
            "k": 5,
            "recorded_at": time.strftime("%Y-%m-%d"),
        },
        "probes": observations,
    }


def compare_to_baseline(observations: list[dict[str, Any]], baseline: dict[int, str]) -> list[str]:
    """返回退化项的人类可读描述；空列表表示通过。**纯函数**。

    判据：**目标不得在比基线更早的层丢失**（`_stage_index` 不得变小）。
    「前进」是允许的（那是改进），只拦「后退」。
    """
    regressions: list[str] = []
    seen = {item["id"] for item in observations}
    missing = sorted(set(baseline) - seen)
    if missing:
        regressions.append(
            f"基线里的 probe {missing} 在本次探针表中不存在 —— 基线已失效"
            "（探针被删？），请确认后 --update-baseline"
        )

    for item in observations:
        pid = item["id"]
        if pid not in baseline:
            regressions.append(
                f"probe #{pid} 不在基线里（新增探针？）—— 无法判定，请 --update-baseline"
            )
            continue
        cur, base = item["dropped_by"], baseline[pid]
        if _stage_index(cur) < _stage_index(base) - _STAGE_JITTER_TOLERANCE:
            regressions.append(
                f"probe #{pid} 退化：{base} → {cur}"
                f"（目标在**更早**的层丢失了 {_stage_index(base) - _stage_index(cur)} 级，"
                f"超出抖动容差 {_STAGE_JITTER_TOLERANCE}；query={item['query'][:40]}）"
            )
    return regressions


def jitter_warnings(observations: list[dict[str, Any]], baseline: dict[int, str]) -> list[str]:
    """退级幅度落在抖动容差带内的 probe —— **告警不判退化**（见 `_STAGE_JITTER_TOLERANCE`）。

    与 `compare_to_baseline` 同口径、同为纯函数；两者对同一条 probe 互斥。
    单独成函数而不是塞进 regressions，是为了让「红」仍然只表示真退化。
    """
    out: list[str] = []
    for item in observations:
        pid = item["id"]
        if pid not in baseline:
            continue
        cur, base = item["dropped_by"], baseline[pid]
        delta = _stage_index(base) - _stage_index(cur)
        if 0 < delta <= _STAGE_JITTER_TOLERANCE:
            out.append(
                f"probe #{pid} 层序抖动：{base} → {cur}（退 {delta} 级，在容差 "
                f"{_STAGE_JITTER_TOLERANCE} 内 ⇒ 不判退化；query={item['query'][:40]}）"
            )
    return out


def _assert_rerank_scored(observations: list[dict[str, Any]]) -> list[str]:
    """反假绿：重排路由开启时，探针的重排阶段必须**真的打了分**。

    为什么需要它：`dropped_by` 由「目标在哪一层被截断」推导，而截断（``rerank`` 的
    ``top_n``）在重排**没打分**时照样发生 —— 只是按 RRF 原序截，不是按重排分截。
    于是 TEI 不可达 / ``rerank()`` 静默降级时，`dropped_by` 仍可能与基线逐字一致，
    门禁就「假绿」了（这正是 ``retrieval_gate._assert_route_preconditions`` 在检索门禁
    里防的那类静默回退，本门禁此前没有）。`rerank_scored` 是 ``trace_probe`` 抓到的
    「rerank_topn 快照里有没有 rerank_score > 0」的直接信号。
    """
    if RG.rerank_mode() != "on":
        return []
    unscored = sorted(o["id"] for o in observations if not o.get("rerank_scored", True))
    if unscored:
        return [
            f"探针 {unscored} 的重排阶段被调用但未真正打分（rerank_score 全 0）—— "
            "dropped_by 不可信，门禁会假绿。请确认 TEI rerank 就绪（scripts/ops/tei_ready.py）"
            "或检查 RERANK_ENABLED 是否被静默关掉。"
        ]
    return []


def _format(observations: list[dict[str, Any]], baseline: dict[int, str] | None) -> str:
    lines = [f"{'probe':>7}  {'当前':<16} {'基线':<16} 目标"]
    for item in observations:
        base = baseline.get(item["id"], "—") if baseline else "—"
        mark = ""
        if baseline and item["id"] in baseline:
            d = _stage_index(item["dropped_by"]) - _stage_index(baseline[item["id"]])
            if d > 0:
                mark = " 前进"
            elif d < -_STAGE_JITTER_TOLERANCE:
                mark = " 退化"
            elif d < 0:
                mark = " 抖动"
            else:
                mark = ""
        lines.append(
            f"#{item['id']:<6} {item['dropped_by']:<16} {base:<16} {item['target'][:40]}{mark}"
        )
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="探针门禁：目标 chunk 存活层级的回归门禁")
    parser.add_argument("--probe", default=DEFAULT_PROBE_PATH, help="探针表 jsonl 路径")
    parser.add_argument("--baseline", default=DEFAULT_BASELINE_PATH, help="基线 json 路径")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    return parser


def _print_report(
    observations: list[dict[str, Any]], baseline: dict[int, str] | None, k: int
) -> None:
    """打印口径抬头 + 探针对比表。"""
    meta = _meta()
    print("=" * 78)
    print(
        f"  探针门禁   embed={meta['embedding_mode']} "
        f"rerank={meta['rerank_mode']}/{meta['rerank_backend']}  k={k}"
    )
    print("=" * 78)
    print(_format(observations, baseline))
    print()


def _write_baseline(baseline_path: Path, observations: list[dict[str, Any]]) -> int:
    """落盘基线并返回退出码。"""
    baseline_path.write_text(
        json.dumps(build_baseline_payload(observations), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"基线已更新: {baseline_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    baseline_path = Path(args.baseline)
    baseline: dict[int, str] | None = None
    if not args.update_baseline:
        try:
            baseline = load_baseline(baseline_path)
        except ValueError as exc:
            print(f"[拒绝] {exc}", file=sys.stderr)
            return 2

    try:
        observations = run_probes(args.probe, k=args.k)
    except RuntimeError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 2

    # 反假绿前置闸：重排没打分 ⇒ dropped_by 不可信，必须先拦（比基线比对更早，
    # 也别带着它录基线）。与检索门禁的 `_assert_route_preconditions` 同一职责。
    violations = _assert_rerank_scored(observations)
    if violations:
        print("[失败] 重排未真正打分（反静默回退）：", file=sys.stderr)
        for item in violations:
            print(f"  - {item}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(build_baseline_payload(observations), ensure_ascii=False, indent=2))
        return 0

    _print_report(observations, baseline, args.k)

    if args.update_baseline:
        return _write_baseline(baseline_path, observations)

    if baseline is None:
        print(
            f"[提示] 基线不存在（{baseline_path}）—— 只观测、不判定。"
            "确认本次结果合理后加 --update-baseline 录基线。"
        )
        return 0

    regressions = compare_to_baseline(observations, baseline)
    jitter = jitter_warnings(observations, baseline)
    if jitter:
        print(
            f"[告警] {len(jitter)} 条层序抖动（退 ≤{_STAGE_JITTER_TOLERANCE} 级 ⇒ 不判退化）：",
            file=sys.stderr,
        )
        for item in jitter:
            print(f"  - {item}", file=sys.stderr)
    if regressions:
        print("[失败] 探针退化：", file=sys.stderr)
        for item in regressions:
            print(f"  - {item}", file=sys.stderr)
        return 1

    if jitter:
        print(
            f"探针门禁通过：无超出容差（{_STAGE_JITTER_TOLERANCE} 级）的退化；"
            f"{len(jitter)} 条抖动已在上方告警。"
        )
    else:
        print("探针门禁通过：所有目标都不比基线丢失得更早。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
