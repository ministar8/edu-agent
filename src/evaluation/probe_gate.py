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

★ **语料边界（2026-10-01 实测）**：临时索引由 ``retrieval_gate.build_index()`` 建，
其语料是 ``rag.ingest.DEFAULT_CATEGORIES``（6 个目录）——**全是 legacy，零 L1/L2/L3**
（2505 条；生产索引 4085 条含分层）。**5 条探针的目标也确实全在 legacy 文件上**
（``07_查找.md`` / ``06_代码实现.md`` / ``04_文件管理.md`` / ``02_数据表示与运算.md``）。
⇒ 本门禁同样**测不到 L1/L2/L3 的退化**。详见 ``retrieval_gate.build_index`` 的 docstring。

判据为什么是「管线序」而不是「是否 survived」
--------------------------------------------
`dropped_by` 的取值**有序**（见 `candidate_trace.DROP_REASONS`）：

    not_recalled < section_dedup < rrf_threshold < rerank_topn
                 < rel_threshold < window_expand < survived

「前进一层」与「后退一层」**都是信息**。若只断言 `survived`，像 `#9` 从
`rrf_threshold` 前进到 `rerank_topn`（阈值层已修好、卡在下一层）这种**真实的进步**
会被判成「没变」—— 而那正是 §3⑦ 要测的东西。

用法::

    # 权威路由（真实 embedding + 真实 TEI rerank）
    GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1 \
        PYTHONPATH=src python -m evaluation.probe_gate

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

from evaluation import retrieval_gate as RG
from evaluation.candidate_trace import DROP_REASONS, load_probes, trace_probe

logger = logging.getLogger(__name__)

DEFAULT_PROBE_PATH = "evals/datasets/golden/retrieval_probes.jsonl"
DEFAULT_BASELINE_PATH = "evals/baselines/probe_baseline.json"

# 存活层级排序：**下标越大 = 目标存活得越久 = 越好**。
# 直接复用 `candidate_trace.DROP_REASONS` —— 它已经是管线顺序，**不要另建一份**
# （两份顺序迟早漂移，而漂移后门禁会静默给出反向判定）。
_STAGE_INDEX: dict[str, int] = {reason: i for i, reason in enumerate(DROP_REASONS)}


def _stage_index(dropped_by: str) -> int:
    """把 `dropped_by` 映射成可比较的进度值；未知取值按最差处理并告警。"""
    idx = _STAGE_INDEX.get(dropped_by)
    if idx is None:
        logger.warning(
            "未知的 dropped_by=%r —— 按最差（0）处理，请检查 candidate_trace", dropped_by
        )
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
        if _stage_index(cur) < _stage_index(base):
            regressions.append(
                f"probe #{pid} 退化：{base} → {cur}"
                f"（目标在**更早**的层丢失了；query={item['query'][:40]}）"
            )
    return regressions


def _format(observations: list[dict[str, Any]], baseline: dict[int, str] | None) -> str:
    lines = [f"{'probe':>7}  {'当前':<16} {'基线':<16} 目标"]
    for item in observations:
        base = baseline.get(item["id"], "—") if baseline else "—"
        mark = ""
        if baseline and item["id"] in baseline:
            d = _stage_index(item["dropped_by"]) - _stage_index(baseline[item["id"]])
            mark = " 前进" if d > 0 else (" 退化" if d < 0 else "")
        lines.append(
            f"#{item['id']:<6} {item['dropped_by']:<16} {base:<16} {item['target'][:40]}{mark}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="探针门禁：目标 chunk 存活层级的回归门禁")
    parser.add_argument("--probe", default=DEFAULT_PROBE_PATH, help="探针表 jsonl 路径")
    parser.add_argument("--baseline", default=DEFAULT_BASELINE_PATH, help="基线 json 路径")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

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

    if args.json:
        print(json.dumps(build_baseline_payload(observations), ensure_ascii=False, indent=2))
        return 0

    meta = _meta()
    print("=" * 78)
    print(
        f"  探针门禁   embed={meta['embedding_mode']} "
        f"rerank={meta['rerank_mode']}/{meta['rerank_backend']}  k={args.k}"
    )
    print("=" * 78)
    print(_format(observations, baseline))
    print()

    if args.update_baseline:
        baseline_path.write_text(
            json.dumps(build_baseline_payload(observations), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"基线已更新: {baseline_path}")
        return 0

    if baseline is None:
        print(
            f"[提示] 基线不存在（{baseline_path}）—— 只观测、不判定。"
            "确认本次结果合理后加 --update-baseline 录基线。"
        )
        return 0

    regressions = compare_to_baseline(observations, baseline)
    if regressions:
        print("[失败] 探针退化：", file=sys.stderr)
        for item in regressions:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("探针门禁通过：所有目标都不比基线丢失得更早。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
