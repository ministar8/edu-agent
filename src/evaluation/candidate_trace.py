"""候选追踪探针：定位「正确 chunk 在哪一层从候选池中消失」。

为什么需要它
------------
`stage_trace` 记录的是**阶段之间的接口**（入参/返回值是否与基线一致），
`retrieval_gate` 记录的是**学科级聚合指标**。两者都回答不了这个问题：
**某个具体的正确 chunk，是在哪一层被筛掉的？**

本模块把它变成**枚举**（`dropped_by`），而不是靠推断。之所以必须枚举：
`_stage_rerank` 内部有两道独立的漏斗（`rerank()` 的 `top_n` 截断、
`_apply_rerank_threshold` 的相对阈值），只看最终结果**无法区分**是哪一个，
而两者的修法完全不同 —— 放宽阈值救不回被 `top_n` 截掉的文档。

链路（每一层都可能吃掉候选）
--------------------------
```
召回池 ──dedup_same_section──► 同section去重
       ──score >= 有效阈值───► RRF 阈值过滤
       ──rerank() 只返回 top_n─► 重排截断     ★ 明细看不到这一层
       ──_apply_rerank_threshold(min_keep)─► 相对阈值
       ──sentence_window_expand / merge_window_into_anchors─► 最终证据
```

实现方式：在 `rag.retriever` 上**临时替换**这几个阶段名来记录快照
（与 `stage_trace` 同一手法），不改一行源码。

★ **测量纪律**：语义缓存会把「缓存命中」混进「检索质量」，
所以本工具**强制关闭语义缓存**（`SEMANTIC_CACHE_ENABLED=False`），并在报告里声明。

用法::

    uv run python -m evaluation.candidate_trace                    # 跑默认 probe 表
    uv run python -m evaluation.candidate_trace --probe evals/retrieval_probes.jsonl
    uv run python -m evaluation.candidate_trace --json             # 机器可读
    uv run python -m evaluation.candidate_trace --limit 2          # 只跑前 N 条
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

DEFAULT_PROBE_PATH = "evals/retrieval_probes.jsonl"

# 正确 chunk 的「消失点」枚举。**必须封闭** —— 自由文本会让归因退化成猜。
DROP_REASONS: tuple[str, ...] = (
    "not_recalled",  # 从未进入召回池
    "section_dedup",  # 被同 section 去重（max_per_section）挤掉
    "rrf_threshold",  # RRF 融合分低于有效阈值
    "rerank_topn",  # 被 rerank() 的 top_n 截断（★ 明细观测不到的一层）
    "rel_threshold",  # 被 _apply_rerank_threshold 的相对阈值筛掉
    "window_expand",  # 在窗口展开 / 合并阶段消失
    "survived",  # 活到最终证据
)

# (快照键, 中文名, rag.retriever 上的属性名)
_STAGES: tuple[tuple[str, str, str], ...] = (
    ("recall", "召回池", "_stage_recall_and_merge"),
    ("section_dedup", "同section去重后", "dedup_same_section"),
    ("rrf_threshold", "RRF阈值过滤后", "_stage_dedup_and_threshold"),
    ("rerank_topn", "重排top_n截断后", "rerank"),
    ("rel_threshold", "相对阈值过滤后", "_apply_rerank_threshold"),
    ("final", "最终证据", "_stage_expand_windows"),
)

# 消失点 → 归因：键是「最后一个还能看到它的阶段」
_LOSS_BY_LAST_SEEN: dict[str, str] = {
    "recall": "section_dedup",
    "section_dedup": "rrf_threshold",
    "rrf_threshold": "rerank_topn",
    "rerank_topn": "rel_threshold",
    "rel_threshold": "window_expand",
}


# ── 数据模型 ──────────────────────────────────────────


@dataclass(frozen=True)
class Probe:
    """一条探针：查询 + 正确 chunk 的定位方式。"""

    id: int
    query: str
    expect_source: str
    expect_section: str
    note: str = ""

    def matches(self, doc: Document) -> bool:
        meta = doc.metadata or {}
        source = str(meta.get("source_file") or meta.get("source") or "")
        section = str(meta.get("section.path") or meta.get("heading_path") or "")
        return self.expect_source in source and self.expect_section in section

    @property
    def target(self) -> str:
        return f"{self.expect_source} :: {self.expect_section}"


@dataclass
class StageSnapshot:
    key: str
    label: str
    count: int
    rank: int | None  # 目标在快照中的 1-based 排名；None = 不在
    top: list[str] = field(default_factory=list)


@dataclass
class TraceResult:
    probe: Probe
    stages: list[StageSnapshot]
    dropped_by: str
    plan: dict[str, Any] = field(default_factory=dict)
    rerank_note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.probe.id,
            "query": self.probe.query,
            "target": self.probe.target,
            "dropped_by": self.dropped_by,
            "plan": self.plan,
            "rerank_note": self.rerank_note,
            "stages": [
                {"key": s.key, "label": s.label, "count": s.count, "rank": s.rank, "top": s.top}
                for s in self.stages
            ],
        }


def load_probes(path: str | Path = DEFAULT_PROBE_PATH, limit: int | None = None) -> list[Probe]:
    """读 probe 表（jsonl，`#` 开头为注释）。"""
    filepath = Path(path)
    if not filepath.exists():
        raise FileNotFoundError(f"probe 表不存在: {filepath}")
    probes: list[Probe] = []
    for line_no, line in enumerate(filepath.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("probe 表第 %d 行解析失败，跳过", line_no)
            continue
        probes.append(
            Probe(
                id=int(raw["id"]),
                query=str(raw["query"]),
                expect_source=str(raw["expect_source"]),
                expect_section=str(raw["expect_section"]),
                note=str(raw.get("note") or ""),
            )
        )
        if limit and len(probes) >= limit:
            break
    return probes


# ── 快照抓取 ──────────────────────────────────────────


def _extract(key: str, out: Any) -> list[Document]:
    """把各阶段的返回值统一成 ``list[Document]``。"""
    if key in ("recall", "section_dedup"):
        # list[tuple[Document, float]]
        return [doc for doc, _score in out]
    if key == "rrf_threshold":
        # (filtered, len(deduped), len(filtered))
        return list(out[0])
    if key == "final":
        # _WindowOutcome(docs=..., elapsed_ms=...)
        return list(out.docs)
    return list(out)


@contextmanager
def _capture():
    """在上下文内替换 `rag.retriever` 的阶段名，把每次调用的输出记进列表。

    ★ **必须按「所属阶段」限定抓取范围**，不能全局抓：
    `dedup_same_section` 在**分解路径的每个子查询分支**里都会被调用一次
    （`_stage_recall_and_merge._branch_search`），`rerank` 在 **HyDE 兜底**里也会被调用。
    若不加限定，快照会取到分支级的那次调用 —— 实测表现为
    「召回池 19 条 → 同section去重后 63 条」这种**条数反而变多**的反常。
    故用两个开关把内部漏斗限定在各自的外层阶段内。
    """
    import rag.retriever as R

    events: list[tuple[str, Any]] = []
    plan_box: dict[str, Any] = {}
    originals: dict[str, Any] = {}
    flags = {"in_dedup_stage": False, "in_rerank_stage": False}

    def _wrap_stage(attr: str, on_enter, on_exit, record_key: str | None):
        original = getattr(R, attr, None)
        if original is None:
            logger.warning("阶段函数不存在，跳过追踪: rag.retriever.%s", attr)
            return

        originals[attr] = original

        async def wrapper(*args, **kwargs):
            on_enter()
            try:
                out = await original(*args, **kwargs)
            finally:
                on_exit()
            if record_key is not None:
                events.append((record_key, _extract(record_key, out)))
            return out

        setattr(R, attr, wrapper)

    def _wrap_inner(attr: str, flag: str, record_key: str):
        original = getattr(R, attr, None)
        if original is None:
            return
        originals[attr] = original

        if inspect.iscoroutinefunction(original):

            async def wrapper(*args, **kwargs):
                out = await original(*args, **kwargs)
                if flags[flag]:
                    events.append((record_key, _extract(record_key, out)))
                return out

        else:

            def wrapper(*args, **kwargs):
                out = original(*args, **kwargs)
                if flags[flag]:
                    events.append((record_key, _extract(record_key, out)))
                return out

        setattr(R, attr, wrapper)

    # 计划阶段：只为拿到 effective_threshold / k / use_rerank 供报告解释
    plan_attr = "_stage_resolve_plan"
    orig_plan = getattr(R, plan_attr, None)
    if orig_plan is not None:
        originals[plan_attr] = orig_plan

        def plan_wrapper(*args, **kwargs):
            out = orig_plan(*args, **kwargs)
            plan_box.update(
                {
                    "effective_threshold": round(float(out.effective_threshold), 4),
                    "k": int(out.k),
                    "coarse_k": int(out.coarse_k),
                    "use_rerank": bool(out.use_rerank),
                    "depth": str(out.depth.depth),
                    "retrieval_layer": str(out.retrieval_layer),
                }
            )
            return out

        setattr(R, plan_attr, plan_wrapper)

    _wrap_stage("_stage_recall_and_merge", lambda: None, lambda: None, "recall")
    _wrap_stage(
        "_stage_dedup_and_threshold",
        lambda: flags.__setitem__("in_dedup_stage", True),
        lambda: flags.__setitem__("in_dedup_stage", False),
        "rrf_threshold",
    )
    _wrap_stage(
        "_stage_rerank",
        lambda: flags.__setitem__("in_rerank_stage", True),
        lambda: flags.__setitem__("in_rerank_stage", False),
        None,
    )
    _wrap_stage("_stage_expand_windows", lambda: None, lambda: None, "final")

    _wrap_inner("dedup_same_section", "in_dedup_stage", "section_dedup")
    _wrap_inner("rerank", "in_rerank_stage", "rerank_topn")
    _wrap_inner("_apply_rerank_threshold", "in_rerank_stage", "rel_threshold")

    try:
        yield events, plan_box
    finally:
        for attr, original in originals.items():
            setattr(R, attr, original)


def _rank(docs: list[Document], probe: Probe) -> int | None:
    for index, doc in enumerate(docs, 1):
        if probe.matches(doc):
            return index
    return None


def _summarize(doc: Document, width: int = 46) -> str:
    meta = doc.metadata or {}
    source = str(meta.get("source_file") or meta.get("source") or "?")
    section = str(meta.get("section.path") or "")
    section = section.rsplit(">", 1)[-1].strip() if ">" in section else section
    score = meta.get("rerank_score")
    prefix = f"{float(score):.4f}  " if score else "        "
    return f"{prefix}{source} :: {section[:width]}"


def _resolve_drop_reason(stages: list[StageSnapshot]) -> str:
    last_seen: str | None = None
    for snap in stages:
        if snap.rank is not None:
            last_seen = snap.key
        elif last_seen is not None:
            return _LOSS_BY_LAST_SEEN.get(last_seen, "window_expand")
    if last_seen is None:
        return "not_recalled"
    return "survived" if stages and stages[-1].key == last_seen else "window_expand"


async def trace_probe(probe: Probe, *, k: int = 5, use_rerank: bool = True) -> TraceResult:
    """跑一条 probe，返回逐层快照与归因。"""
    import rag.retriever as R

    with _capture() as (events, plan_box):
        await R.aretrieve_documents(probe.query, k=k, use_rerank=use_rerank)

    # 同一阶段可能被调用多次（HyDE 会再走一遍召回与重排）——取**首次**，
    # 因为主链路的顺序就是首次出现的那一轮。
    first: dict[str, list[Document]] = {}
    for key, docs in events:
        first.setdefault(key, docs)

    stages: list[StageSnapshot] = []
    for key, label, _attr in _STAGES:
        docs = first.get(key)
        if docs is None:
            continue
        rank = _rank(docs, probe)
        stages.append(
            StageSnapshot(
                key=key,
                label=label,
                count=len(docs),
                rank=rank,
                top=[_summarize(d) for d in docs[:3]],
            )
        )

    note = ""
    if sum(1 for key, _ in events if key == "recall") > 1:
        note = "召回被调用多次（HyDE 触发），快照取首轮；结论可能不完整"
    elif first.get("rerank_topn") and not any(
        (d.metadata or {}).get("rerank_score") for d in first["rerank_topn"]
    ):
        note = (
            "重排阶段被调用但**没有真正打分**（RERANK_ENABLED=false 时 rerank() 提前返回）"
            " —— 用 --rerank 重跑才能看到重排漏斗"
        )

    return TraceResult(
        probe=probe,
        stages=stages,
        dropped_by=_resolve_drop_reason(stages),
        plan=plan_box,
        rerank_note=note,
    )


# ── 报告 ──────────────────────────────────────────────


def _format(result: TraceResult) -> str:
    lines = [f"=== #{result.probe.id}  {result.probe.query}"]
    lines.append(
        f"    目标：{result.probe.target}"
        + (f"    （{result.probe.note}）" if result.probe.note else "")
    )
    if result.plan:
        lines.append(
            f"    计划：k={result.plan.get('k')} coarse_k={result.plan.get('coarse_k')} "
            f"阈值={result.plan.get('effective_threshold')} "
            f"重排={result.plan.get('use_rerank')} 层={result.plan.get('retrieval_layer')}"
        )
    for snap in result.stages:
        mark = f"rank {snap.rank} ✓" if snap.rank is not None else "缺失 ✗"
        lines.append(f"    {snap.label:<18}{snap.count:>4} 条 | 目标 {mark}")
    lines.append(f"    ⇒ dropped_by = {result.dropped_by}")
    if result.rerank_note:
        lines.append(f"    ⚠ {result.rerank_note}")

    # 消失点的前 3 条：看是什么把它挤掉的
    for snap in result.stages:
        if snap.rank is None and snap.top:
            lines.append(f"    ★ 「{snap.label}」前 3 条：")
            for item in snap.top:
                lines.append(f"        {item}")
            break
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="候选追踪：定位正确 chunk 在哪一层消失")
    parser.add_argument("--probe", default=DEFAULT_PROBE_PATH, help="probe 表 jsonl 路径")
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 条")
    parser.add_argument(
        "--rerank",
        dest="rerank",
        action="store_true",
        default=True,
        help="强制开启重排（默认；诊断重排漏斗必须开，否则该层是空转）",
    )
    parser.add_argument("--no-rerank", dest="rerank", action="store_false", help="强制关闭重排")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # ★ 测量纪律：语义缓存会把「缓存命中」混进「检索质量」，强制关闭。
    from core.settings import settings

    settings.SEMANTIC_CACHE_ENABLED = False
    settings.RERANK_ENABLED = args.rerank
    import rag.semantic_cache as sc

    sc._semantic_cache = None

    probes = load_probes(args.probe, limit=args.limit)
    if not probes:
        print("[错误] probe 表为空", flush=True)
        return 2

    results = [asyncio.run(trace_probe(p, k=args.k, use_rerank=True)) for p in probes]

    if args.json:
        print(json.dumps([r.as_dict() for r in results], ensure_ascii=False, indent=2))
        return 0

    print("=" * 68)
    print(f"  候选追踪   语义缓存=off   重排={'on' if args.rerank else 'off'}")
    print("=" * 68)
    for result in results:
        print(_format(result))
        print()

    print("归因汇总：")
    for result in results:
        print(f"  #{result.probe.id:<3} {result.dropped_by}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
