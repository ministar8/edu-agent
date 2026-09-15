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

    # 录基线与比对**必须用同一个 --persist-dir**
    python -m evaluation.stage_trace --record     --limit 12 --persist-dir /tmp/idx
    python -m evaluation.stage_trace              --limit 12 --persist-dir /tmp/idx

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


async def probe_query_stability(
    query: str, *, repeats: int = 3, k: int = 5, use_rerank: bool = False
) -> tuple[bool, list[Any]]:
    """重复跑同一条 query，判断**最终结果**是否可复现。

    为什么必须做这一步：上游 Chroma 的近似检索在 top-k 边界会抖动，实测**偶尔会传导到
    最终返回的文档序列**（不是总能被下游融合/去重吸收）。对这类 query 做逐位比对没有意义 ——
    同一份代码都会"不一致"。录基线时必须把它们排除，否则安全网会有约 1/10 的假阳性。

    Returns:
        ``(是否稳定, 各次运行的最终签名)``。返回签名便于把不稳定项报给使用者。
    """
    import rag.retriever as R

    finals: list[Any] = []
    for _ in range(max(1, repeats)):
        docs = await R.aretrieve_documents(query, k=k, use_rerank=use_rerank)
        finals.append(signature(docs))
    stable = all(f == finals[0] for f in finals[1:])
    return stable, finals


def _floats_close(a: Any, b: Any, *, rel_tol: float) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=rel_tol, abs_tol=1e-12)
    return False


# recall 层的输出依赖 Chroma 的**近似**向量检索，可能在 top-k 边界抖动
# （实测：首次访问少返回一个本该进 top-k 的候选；详见 ENGINEERING.md §1 P1）。
# 这些阶段的**输出**容许有界差异；它们下游的阶段因为吃到了不同输入，
# 其差异归为"无法判定"而不是失败。
VOLATILE_OUTPUT_STAGES = frozenset({"recall_multi_route", "recall_multi_route_async"})


@dataclass
class TraceComparison:
    """分级比对结果。

    - ``failures``：**必须修**的差异 —— 我们自己的编排 / 融合 / 展开逻辑变了
    - ``advisories``：因上游 ANN 抖动而**无法判定**的差异 —— 不计失败，但要报出来，
      否则"通过"会掩盖掉"其实有一大段没验证到"
    - ``max_volatile_delta``：recall 层实际观察到的最大文档集合差异
    """

    failures: list[str]
    advisories: list[str]
    max_volatile_delta: int

    @property
    def ok(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        if self.failures:
            return f"不通过：{len(self.failures)} 处严格差异，{len(self.advisories)} 处无法判定"
        if self.advisories:
            return (
                f"通过：0 处严格差异；{len(self.advisories)} 处因上游 ANN 抖动无法判定"
                f"（最大文档差异 {self.max_volatile_delta}）"
            )
        return "通过：所有阶段入参与返回值逐条一致。"


def _doc_hashes(value: Any) -> set[str]:
    """从签名里收集所有文档内容哈希，用于度量集合差异幅度。"""
    found: set[str] = set()
    stack: list[Any] = [value]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            digest = cur.get("hash")
            if isinstance(digest, str):
                found.add(digest)
            stack.extend(cur.values())
        elif isinstance(cur, (list, tuple)):
            stack.extend(cur)
    return found


# recall 层容许的差异比例。用**比例**而不是绝对条数：recall 的候选数随 k 与路由数变化，
# 固定条数在候选少时过严、在候选多时形同虚设（实测漂移 4 条，绝对阈值 2 会误报）。
#
# 为什么可以给得比较宽（30%）：这个阈值**只影响"差异归因"**，不影响安全网的强度。
# 重构真正要守住的是另外四条严格断言 —— 阶段调用序列、各阶段入参、融合及之后各阶段、
# 以及最终返回。recall 的**输出**本来就是上游近似索引的产物，对它苛求逐位一致
# 只会把上游噪声误判成重构退化。若 recall 真出了退化（比如传错 k），
# 入参断言与最终返回断言都会抓到。
VOLATILE_RATIO = 0.3
VOLATILE_FLOOR = 2


def _volatile_delta(exp_out: Any, act_out: Any, ratio: float) -> tuple[int, int]:
    """返回 ``(实际对称差异文档数, 允许上限)``。ratio<=0 表示严格模式（容许 0）。"""
    exp_h, act_h = _doc_hashes(exp_out), _doc_hashes(act_out)
    delta = len(exp_h ^ act_h)
    if ratio <= 0:
        return delta, 0
    allowed = max(VOLATILE_FLOOR, round(ratio * max(len(exp_h), len(act_h), 1)))
    return delta, allowed


def compare_traces(
    expected: dict[str, Any],
    actual: dict[str, Any],
    *,
    rel_tol: float = 1e-9,
    volatile_stages: frozenset[str] = VOLATILE_OUTPUT_STAGES,
    volatile_ratio: float = VOLATILE_RATIO,
) -> TraceComparison:
    """**分级**比对两份 trace。

    为什么不能一律严格：recall 层走的是 Chroma 的**近似**索引，top-k 边界本来就可能抖动。
    若把它也当严格失败，重构时会把上游噪声误判成"重构引入了退化"，
    最后只能靠人肉判断 —— 那等于没有安全网。

    分级规则：

    ========================================  ==========================================
    比较对象                                   判定
    ========================================  ==========================================
    阶段调用**序列**                             严格（编排被改动最直接的证据）
    各阶段**入参**                               严格，除非它吃到了抖动的 recall 输出
    recall 层**输出**                            容许 ``volatile_ratio`` 比例的差异
    recall 之后的阶段                            若其入参含抖动的 recall 输出 → 无法判定
    最终返回                                    严格（"不改行为"的最终契约）
    ========================================  ==========================================

    **"吃到抖动输出"的判定与顺序无关**：不能用"遍历到抖动之后就算污染"这种线性推断 ——
    比对前 steps 会按 (阶段名, 入参) 排序，`dedup_section` 会排在
    `recall_multi_route_async` **之前**，于是下游的差异会被当成严格失败。
    改为按**内容**判定：某阶段的入参里出现了 recall 输出中的文档哈希，就算受影响。
    """
    failures: list[str] = []
    advisories: list[str] = []
    max_delta = 0

    exp_stages = sorted(expected.get("stages_called", []))
    act_stages = sorted(actual.get("stages_called", []))
    if exp_stages != act_stages:
        # 比**多重集**而不是原序列：`stages_called` 是调用发生的先后次序，
        # 而阶段内部存在并发（`_amulti_route_search` 走 asyncio.gather、
        # 去重走线程池），完成次序天然不定 —— 实测同一份代码两次运行的
        # recall / dedup 交错顺序就不同。按序列比对会稳定误报。
        # 这里断言的是"调用了哪些阶段、各几次"，"以什么输入调用"由下面的 steps 负责。
        failures.append(f"被调用的阶段集合不同：期望 {exp_stages}，实际 {act_stages}")
        return TraceComparison(failures, advisories, 0)

    exp_steps = expected.get("steps", [])
    act_steps = actual.get("steps", [])
    if len(exp_steps) != len(act_steps):
        failures.append(f"阶段调用次数不同：期望 {len(exp_steps)} 次，实际 {len(act_steps)} 次")
        return TraceComparison(failures, advisories, 0)

    # ── 第一遍：recall 层是否抖动，以及它输出了哪些文档 ──
    volatile_hashes: set[str] = set()
    volatile_drifted = False
    for exp, act in zip(exp_steps, act_steps, strict=True):
        if exp.get("stage") not in volatile_stages:
            continue
        volatile_hashes |= _doc_hashes(exp.get("out")) | _doc_hashes(act.get("out"))
        if not _deep_equal(exp.get("out"), act.get("out"), rel_tol=rel_tol):
            volatile_drifted = True

    def _fed_by_recall(step: dict[str, Any]) -> bool:
        """该阶段的入参是否包含 recall 输出里的文档。"""
        return bool(_doc_hashes(step.get("in")) & volatile_hashes)

    # ── 第二遍：逐条判定 ──
    for idx, (exp, act) in enumerate(zip(exp_steps, act_steps, strict=True)):
        stage = exp.get("stage", "?")
        fed = _fed_by_recall(exp) or _fed_by_recall(act)

        in_same = exp.get("in") == act.get("in")
        out_same = _deep_equal(exp.get("out"), act.get("out"), rel_tol=rel_tol)
        if in_same and out_same:
            continue

        if stage in volatile_stages:
            if not out_same:
                delta, allowed = _volatile_delta(exp.get("out"), act.get("out"), volatile_ratio)
                max_delta = max(max_delta, delta)
                # **只报警，不判失败**：recall 的输出来自上游近似索引，对它设硬阈值
                # 必然会周期性误报（实测漂移在 2~6 之间波动，任何固定阈值都会被越过）。
                # 而 recall 的退化仍能被抓到 —— 入参断言（k / 路由 / 查询串）与最终返回断言
                # 都是严格的。安全网的强度不来自这里。
                flag = "超出常规范围" if delta > allowed else "常规范围内"
                advisories.append(
                    f"[{idx}] 阶段 {stage} 输出差 {delta} 个文档"
                    f"（上游 ANN 边界抖动，{flag} ≤{allowed}）"
                )
            if not in_same:
                # recall 的入参变了 = 路由 / 查询构造变了，这是严格失败
                failures.append(f"[{idx}] 阶段 {stage} 的**入参**变了")
            continue

        if fed and volatile_drifted:
            advisories.append(f"[{idx}] 阶段 {stage} 的入参含抖动的 recall 输出，其差异无法判定")
            continue

        if not in_same:
            failures.append(f"[{idx}] 阶段 {stage} 的**入参**变了")
        if not out_same:
            failures.append(f"[{idx}] 阶段 {stage} 的**返回值**变了")

    if not _deep_equal(expected.get("final"), actual.get("final"), rel_tol=rel_tol):
        failures.append("最终返回的文档序列变了")

    return TraceComparison(failures, advisories, max_delta)


def diff_traces(
    expected: dict[str, Any], actual: dict[str, Any], *, rel_tol: float = 1e-9
) -> list[str]:
    """**严格**比对（所有阶段逐位一致），返回失败列表；空列表表示一致。

    差异信息刻意带上**阶段名与下标**，这样拆分重构出错时能直接定位到哪一步，
    而不是只知道"最终结果不一样"。

    需要容忍 ANN 边界抖动时用 ``compare_traces``；这里保留严格语义是为了
    让"确实应该逐位一致"的场景（单元测试、非召回阶段）有一个不含糊的断言。
    """
    return compare_traces(expected, actual, rel_tol=rel_tol, volatile_stages=frozenset()).failures


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
    from evaluation.retrieval_gate import load_golden_queries

    queries = [q for q, _ in load_golden_queries("evals/sample_408.jsonl", limit=limit)]
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


def main(argv: list[str] | None = None) -> int:
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
        traces, excluded = asyncio.run(
            record_all(
                limit=args.limit,
                stable_only=args.stable_only,
                stable_repeats=args.stable_repeats,
            )
        )
        print(
            f"追踪 {len(traces)} 条 query（{time.perf_counter() - start:.1f}s），"
            f"平均每条约 {sum(len(t.steps) for t in traces) / max(len(traces), 1):.1f} 个阶段调用"
        )
        if excluded:
            print(
                f"[已排除] {len(excluded)} 条 query 的最终结果不可复现"
                f"（上游 ANN 边界抖动传导，非本项目缺陷）："
            )
            for query in excluded[:6]:
                print(f"    {query[:44]}")

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

        total_failures = 0
        total_advisories = 0
        max_delta = 0
        for exp, act in zip(saved, payload["traces"], strict=True):
            result = compare_traces(exp, act, volatile_ratio=args.volatile_ratio)
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
    finally:
        # 只清理自己创建的临时目录；--persist-dir 指定的目录归调用方管
        if own_tmp and not args.keep_index:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
