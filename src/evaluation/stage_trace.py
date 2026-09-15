"""检索链阶段级行为追踪：为拆分 `aretrieve_documents` 提供逐阶段等价性证据。

为什么需要它
------------
`aretrieve_documents` 是 428 行的单体编排函数。要把它拆成阶段函数，**"最终输出一致"
不足以证明拆分无损** —— 两处错误互相抵消也能得到同样的输出。阶段级追踪记录
**每个阶段函数的入参与返回值**，把"输出一致"细化为"每一步都一致"，
任何阶段的行为变化都会定位到具体那一步，而不是只告诉你"结果不一样了"。

怎么做到不侵入源码
------------------
被追踪的阶段函数**已经是独立的模块级函数**（`_multi_route_search` / `dedup_same_section` /
`rerank` / `sentence_window_expand` …），单体函数只是把它们串起来。所以只要在
`rag.retriever` 上临时替换这些名字，就能记录"阶段之间的接口"，而不用改一行源码。
这个性质也决定了它对重构友好：**拆分只改变调用点，不改变这些函数的契约**，
因此同一份记录在拆分前后必须逐字匹配。

刻意不追踪的东西
----------------
- `_safe_to_thread`：它是"把调用挪到线程"的实现细节，不是行为契约。
  重构中合法地改变线程策略不应导致失败。
- 顺序的严格性：阶段内部可能有并发调用（`_multi_route_search` 走 ThreadPoolExecutor），
  完成次序天然不定。故比对前按 `(阶段名, 入参)` 归一化排序 —— 我们断言的是
  "每个阶段被同样的输入调用、返回同样的输出"，而不是"调用次序"。

用法::

    python -m evaluation.stage_trace --record   # 录基线到 evals/stage_baseline.json
    python -m evaluation.stage_trace            # 与基线比对
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import inspect
import json
import logging
import math
import shutil
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

logger = logging.getLogger(__name__)

DEFAULT_BASELINE_PATH = "evals/stage_baseline.json"

# (阶段标签, rag.retriever 上的属性名)。顺序仅用于展示。
STAGE_TARGETS: tuple[tuple[str, str], ...] = (
    ("resolve_strategy", "resolve_retrieval_strategy"),
    ("resolve_policy", "_resolve_retrieval_policy"),
    ("decompose", "decompose"),
    ("recall_multi_route", "_multi_route_search"),
    ("recall_multi_route_async", "_amulti_route_search"),
    ("fuse_rrf", "weighted_rrf_merge"),
    ("dedup_section", "dedup_same_section"),
    ("rerank", "rerank"),
    ("apply_threshold", "_apply_rerank_threshold"),
    ("should_hyde", "should_trigger_hyde"),
    ("expand_window", "sentence_window_expand"),
)


def signature(value: Any) -> Any:
    """把任意阶段 I/O 转成稳定、可 JSON、可比对的形式。

    `Document` 只取"身份 + 排序相关"字段（来源 / 章节 / 内容哈希 / 分数 / 命中路由），
    不把整段正文塞进基线 —— 否则基线文件会被正文撑爆，且正文改动会淹没真正的行为变化。

    **浮点保留全精度**（不做 round）：调用次序变化会让浮点加法的最后几位不同，
    round 到 1e-6 反而会在边界上产生随机差异。比对时用容差处理。
    """
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, Document):
        meta = value.metadata or {}
        return {
            "src": meta.get("source_file") or meta.get("source") or "",
            "sec": meta.get("section.id") or meta.get("section_id") or "",
            "hash": hashlib.sha1(value.page_content.encode("utf-8")).hexdigest()[:12],
            "score": float(meta.get("recall_score") or 0.0),
            "routes": meta.get("recall_routes") or "",
            "rerank": float(meta.get("rerank_score") or 0.0),
        }
    if callable(value):
        # repr(function) 含内存地址 → 必须用 qualname，否则基线每次都不同
        return f"<callable {getattr(value, '__qualname__', '?')}>"
    if isinstance(value, (list, tuple)):
        return [signature(v) for v in value]
    if isinstance(value, dict):
        return {str(k): signature(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (set, frozenset)):
        return sorted(str(v) for v in value)
    return f"<{type(value).__name__}>"


@dataclass(frozen=True)
class StageStep:
    stage: str
    inputs: Any
    outputs: Any

    def as_dict(self) -> dict[str, Any]:
        return {"stage": self.stage, "in": self.inputs, "out": self.outputs}


@dataclass
class StageTrace:
    query: str
    steps: list[StageStep]
    final: Any

    def normalized(self) -> list[dict[str, Any]]:
        """按 (阶段名, 入参) 排序，消除并发调用带来的次序不确定性。"""
        ordered = sorted(
            self.steps,
            key=lambda s: (s.stage, json.dumps(s.inputs, sort_keys=True, ensure_ascii=False)),
        )
        return [s.as_dict() for s in ordered]

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "stages_called": [s.stage for s in self.steps],
            "steps": self.normalized(),
            "final": self.final,
        }


@contextmanager
def trace_stages():
    """在上下文内拦截 `rag.retriever` 的阶段函数，把调用记录进 yield 出的列表。"""
    import rag.retriever as R

    steps: list[StageStep] = []
    originals: dict[str, Any] = {}

    for stage, attr in STAGE_TARGETS:
        original = getattr(R, attr, None)
        if original is None:
            logger.warning("阶段函数不存在，跳过追踪: rag.retriever.%s", attr)
            continue
        originals[attr] = original

        if inspect.iscoroutinefunction(original):

            async def wrapper(*args, _s=stage, _f=original, **kwargs):
                ins = signature((args, kwargs))
                out = await _f(*args, **kwargs)
                steps.append(StageStep(_s, ins, signature(out)))
                return out

        else:

            def wrapper(*args, _s=stage, _f=original, **kwargs):
                ins = signature((args, kwargs))
                out = _f(*args, **kwargs)
                steps.append(StageStep(_s, ins, signature(out)))
                return out

        setattr(R, attr, wrapper)

    try:
        yield steps
    finally:
        for attr, original in originals.items():
            setattr(R, attr, original)


async def record_query(query: str, *, k: int = 5, use_rerank: bool = False) -> StageTrace:
    """跑一条 query，返回阶段级追踪。"""
    import rag.retriever as R

    with trace_stages() as steps:
        docs = await R.aretrieve_documents(query, k=k, use_rerank=use_rerank)
    return StageTrace(query=query, steps=list(steps), final=signature(docs))


def _floats_close(a: Any, b: Any, *, rel_tol: float) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=rel_tol, abs_tol=1e-12)
    return False


def diff_traces(
    expected: dict[str, Any], actual: dict[str, Any], *, rel_tol: float = 1e-9
) -> list[str]:
    """逐阶段比对两份 trace，返回人类可读的差异列表；空列表表示一致。

    差异信息刻意带上**阶段名与下标**，这样拆分重构出错时能直接定位到哪一步，
    而不是只知道"最终结果不一样"。
    """
    problems: list[str] = []

    exp_stages, act_stages = expected.get("stages_called", []), actual.get("stages_called", [])
    if exp_stages != act_stages:
        problems.append(f"被调用的阶段序列不同：期望 {exp_stages}，实际 {act_stages}")
        return problems

    exp_steps, act_steps = expected.get("steps", []), actual.get("steps", [])
    if len(exp_steps) != len(act_steps):
        problems.append(f"阶段调用次数不同：期望 {len(exp_steps)} 次，实际 {len(act_steps)} 次")

    for idx, (exp, act) in enumerate(zip(exp_steps, act_steps, strict=False)):
        stage = exp.get("stage", "?")
        if exp.get("in") != act.get("in"):
            problems.append(f"[{idx}] 阶段 {stage} 的**入参**变了")
        if not _deep_equal(exp.get("out"), act.get("out"), rel_tol=rel_tol):
            problems.append(f"[{idx}] 阶段 {stage} 的**返回值**变了")

    if not _deep_equal(expected.get("final"), actual.get("final"), rel_tol=rel_tol):
        problems.append("最终返回的文档序列变了")

    return problems


def _deep_equal(a: Any, b: Any, *, rel_tol: float) -> bool:
    if _floats_close(a, b, rel_tol=rel_tol):
        return True
    if type(a) is not type(b):
        # int/float 混用在 JSON 往返后会变成 float，这里放行数值型
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            return math.isclose(float(a), float(b), rel_tol=rel_tol, abs_tol=1e-12)
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_deep_equal(a[k], b[k], rel_tol=rel_tol) for k in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(
            _deep_equal(x, y, rel_tol=rel_tol) for x, y in zip(a, b, strict=True)
        )
    return a == b


async def record_all(
    limit: int | None = None, *, k: int = 5, use_rerank: bool = False
) -> list[StageTrace]:
    from evaluation.retrieval_gate import load_golden_queries

    queries = [q for q, _ in load_golden_queries("evals/sample_408.jsonl", limit=limit)]
    traces: list[StageTrace] = []
    for query in queries:
        traces.append(await record_query(query, k=k, use_rerank=use_rerank))
    return traces


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="检索链阶段级行为追踪")
    parser.add_argument("--baseline", default=DEFAULT_BASELINE_PATH)
    parser.add_argument("--limit", type=int, default=12, help="追踪前 N 条 query")
    parser.add_argument("--record", action="store_true", help="录制基线")
    parser.add_argument(
        "--persist-dir",
        default=None,
        help="固定索引目录（跨次复用同一个 HNSW 索引）。不传则每次新建临时目录。",
    )
    parser.add_argument("--keep-index", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)

    from evaluation.retrieval_gate import (
        build_index,
        configure_for_gate,
        wait_for_index_ready,
    )

    # 为什么允许固定索引目录：Chroma 的 HNSW 是**近似**索引，跨进程重建得到的图
    # 不一定逐位相同，于是原始召回结果（recall_multi_route*）会有微小差异 ——
    # 门禁的聚合指标会吸收掉这种差异，但阶段级追踪看得见，表现为"每次跑都有几处不同"。
    # 复用同一个持久化索引可以把这一层变量消掉，让"阶段级一致"成为可判定的断言。
    own_tmp = args.persist_dir is None
    tmp_dir = args.persist_dir or tempfile.mkdtemp(prefix="stage_trace_")
    try:
        configure_for_gate(tmp_dir)
        start = time.perf_counter()
        counts = build_index()
        wait_for_index_ready(sorted(counts))
        print(
            f"索引就绪：{sum(counts.values())} chunks（{time.perf_counter() - start:.1f}s）"
            f"{'（复用 ' + tmp_dir + '）' if not own_tmp else ''}"
        )

        start = time.perf_counter()
        traces = asyncio.run(record_all(limit=args.limit))
        print(
            f"追踪 {len(traces)} 条 query（{time.perf_counter() - start:.1f}s），"
            f"平均每条约 {sum(len(t.steps) for t in traces) / len(traces):.1f} 个阶段调用"
        )

        payload = {
            "_meta": {
                "note": "由 evaluation.stage_trace 生成；拆分检索链后必须与本文件逐阶段一致",
                "embedding": "USE_FAKE_EMBEDDING (deterministic hashing)",
                "rerank_enabled": False,
                "k": 5,
                "n_queries": len(traces),
                "recorded_at": time.strftime("%Y-%m-%d"),
            },
            "traces": [t.as_dict() for t in traces],
        }

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

        total_problems = 0
        for exp, act in zip(saved, payload["traces"], strict=True):
            problems = diff_traces(exp, act)
            if problems:
                total_problems += len(problems)
                print(f"\n[差异] {exp['query'][:44]}")
                for p in problems[:6]:
                    print(f"    {p}")

        if total_problems:
            print(f"\n阶段级比对未通过：共 {total_problems} 处差异")
            return 1
        print("\n阶段级比对通过：所有阶段入参与返回值逐条一致。")
        return 0
    finally:
        # 只清理自己创建的临时目录；--persist-dir 指定的目录归调用方管
        if own_tmp and not args.keep_index:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
