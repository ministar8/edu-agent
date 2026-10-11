"""stage_trace 核心：阶段签名 / 追踪捕获 / 比对（从 stage_trace.py 拆出，行为等价）。"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import math
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from langchain_core.documents import Document

from rag.retrieval.evidence import TextEvidence

logger = logging.getLogger(__name__)


STAGE_TARGETS: tuple[tuple[str, str], ...] = (
    ("resolve_strategy", "resolve_retrieval_plan"),
    ("resolve_policy", "_resolve_thresholds"),
    ("decompose", "decompose"),
    ("recall_multi_route_async", "_amulti_route_search"),
    # RRF 融合有**两个入口**，此前只追踪了分解用的那个，导致主 RRF 成为观测盲区：
    #   - `weighted_rrf_merge`  仅**查询分解**时走（原始查询 1.5 : 子查询 1.0 加权）
    #   - `merge_route_results` **所有查询**都走（主 RRF，加权 RRF 公式）
    # 后果：实测 `fuse_rrf` 只出现 9/40，看着像「RRF 大部分时候没跑」，
    # 实际是主路径没被追踪（9 恰等于 decomposed 的条数）。补上 `fuse_rrf_main` 消除该误读。
    ("fuse_rrf", "weighted_rrf_merge"),
    ("fuse_rrf_main", "merge_route_results"),
    # ── 门面层三步（此前是观测盲区）────────────────────────────────
    # `afuse_documents` / `averify_evidence` 在 `aretrieve_evidence` 里是**函数内局部导入**
    # （`from rag.retrieval.fusion import afuse_documents`），因此**不是** `rag.retrieval.retriever` 的模块级属性，
    # 用 `getattr(R, ...)` 取不到。故目标支持 `"module:attr"` 写法 → 直接 patch 源模块的属性；
    # 局部导入每次调用都会重读源模块属性，所以 patch 生效。
    # 这样不必为了可追踪而把局部导入提到模块级（不动运行时模块，零风险）。
    #
    # ⚠️ 但「patch 生效」≠「会被调用」：这三个目标只在**证据层**被走到，
    # 而追踪入口曾经是文档层的 `aretrieve_documents` → 它们恒为 0 次。
    # 故 `record_query` / `probe_query_stability` **必须**从
    # `aretrieve_evidence_with_retry` 进入（见模块文档串）。
    # 这条依赖靠 `_stage_trigger_report` 的触发率表兜住：0 次会显式标出来。
    ("retrieve_evidence", "aretrieve_evidence"),
    ("fuse_documents", "fusion:afuse_documents"),
    ("verify", "verifier:averify_evidence"),
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
    if isinstance(value, TextEvidence):
        # 证据层的对应物：文档层比 `Document`，证据层比 `TextEvidence`。
        # 字段与下面的 `Document` 分支**刻意同构**（src / sec / hash / score / rerank / routes），
        # 这样「文档层→证据层」重构前后的最终签名仍可对照，不会因为换了载体就失去可比性。
        return {
            "src": value.source,
            "sec": value.section_path or value.chunk_id,
            "hash": hashlib.sha1(value.content.encode("utf-8")).hexdigest()[:12],
            "score": float(value.recall_score or 0.0),
            "routes": value.metadata.get("recall_routes") or "",
            "rerank": float(value.rerank_score or 0.0),
        }
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
    """在上下文内拦截检索链的阶段函数，把调用记录进 yield 出的列表。

    目标写法见 ``STAGE_TARGETS``：裸名 → ``rag.retrieval.retriever.<name>``；
    ``"module:attr"`` → ``rag.<module>.<attr>``（用于函数内局部导入的依赖）。
    """
    import importlib

    import rag.retrieval.retriever as R

    steps: list[StageStep] = []
    originals: list[tuple[Any, str, Any]] = []  # (所属模块, 属性名, 原函数)

    for stage, target in STAGE_TARGETS:
        if ":" in target:
            mod_name, attr = target.split(":", 1)
            try:
                module = importlib.import_module(f"rag.{mod_name}")
            except ImportError:
                logger.warning("模块不存在，跳过追踪: rag.%s", mod_name)
                continue
        else:
            module, attr = R, target

        original = getattr(module, attr, None)
        if original is None:
            logger.warning("阶段函数不存在，跳过追踪: %s.%s", module.__name__, attr)
            continue
        originals.append((module, attr, original))

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

        setattr(module, attr, wrapper)

    try:
        yield steps
    finally:
        for module, attr, original in originals:
            setattr(module, attr, original)


async def _retrieve_fused(query: str, *, k: int, use_rerank: bool):
    """从**证据层**入口检索 —— 与检索门禁（`retrieval_gate.run_gate`）**同一个入口**。

    为什么不能从 `aretrieve_documents` 进入：那是文档层，`afuse_documents` /
    `averify_evidence` 永远走不到，追踪里会出现两个恒为 0 的假指标
    （见模块文档串「追踪入口必须与生产一致」）。

    ``max_retries=0`` 是为了**可复现**：带重试时同一条 query 调用 `aretrieve_evidence`
    的次数会随 verdict 变化，阶段序列长度不稳定，「逐阶段比对」就失去意义了。
    """
    import rag.retrieval.retriever as R

    fused, _verdict = await R.aretrieve_evidence_with_retry(
        query=query,
        k=k,
        use_rerank=use_rerank,
        max_retries=0,
        use_llm_verify=False,
    )
    return fused


async def record_query(query: str, *, k: int = 5, use_rerank: bool = False) -> StageTrace:
    """跑一条 query，返回阶段级追踪。

    最终签名的载体是 ``fused.text_evidences`` —— 文档层的 ``list[Document]``
    在证据层已不存在，故取证据列表作对应物（`signature` 两个分支刻意同构）。
    """
    with trace_stages() as steps:
        fused = await _retrieve_fused(query, k=k, use_rerank=use_rerank)
    return StageTrace(query=query, steps=list(steps), final=signature(fused.text_evidences))


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
    finals: list[Any] = []
    for _ in range(max(1, repeats)):
        # 必须与 `record_query` 走**同一个入口**，否则探测的稳定性与录基线的东西不是一回事
        fused = await _retrieve_fused(query, k=k, use_rerank=use_rerank)
        finals.append(signature(fused.text_evidences))
    stable = all(f == finals[0] for f in finals[1:])
    return stable, finals


def _floats_close(a: Any, b: Any, *, rel_tol: float) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=rel_tol, abs_tol=1e-12)
    return False


# recall 层的输出依赖 Chroma 的**近似**向量检索，可能在 top-k 边界抖动
# （实测：首次访问少返回一个本该进 top-k 的候选）。
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


def _collect_volatile(
    exp_steps: list[dict[str, Any]],
    act_steps: list[dict[str, Any]],
    volatile_stages: frozenset[str],
    rel_tol: float,
) -> tuple[set[str], bool]:
    """第一遍：recall 层是否抖动，以及它输出了哪些文档（供判定下游是否吃到抖动输出）。"""
    volatile_hashes: set[str] = set()
    volatile_drifted = False
    for exp, act in zip(exp_steps, act_steps, strict=True):
        if exp.get("stage") not in volatile_stages:
            continue
        volatile_hashes |= _doc_hashes(exp.get("out")) | _doc_hashes(act.get("out"))
        if not _deep_equal(exp.get("out"), act.get("out"), rel_tol=rel_tol):
            volatile_drifted = True
    return volatile_hashes, volatile_drifted


def _judge_steps(
    exp_steps: list[dict[str, Any]],
    act_steps: list[dict[str, Any]],
    volatile_stages: frozenset[str],
    volatile_hashes: set[str],
    volatile_drifted: bool,
    volatile_ratio: float,
    rel_tol: float,
) -> tuple[list[str], list[str], int]:
    """第二遍：逐条判定，返回 ``(failures, advisories, max_delta)``。

    **"吃到抖动输出"的判定与顺序无关**：不能用"遍历到抖动之后就算污染"这种线性推断 ——
    比对前 steps 会按 (阶段名, 入参) 排序，`dedup_section` 会排在
    `recall_multi_route_async` **之前**，于是下游的差异会被当成严格失败。
    改为按**内容**判定：某阶段的入参里出现了 recall 输出中的文档哈希，就算受影响。
    """
    failures: list[str] = []
    advisories: list[str] = []
    max_delta = 0

    def _fed_by_recall(step: dict[str, Any]) -> bool:
        """该阶段的入参是否包含 recall 输出里的文档。"""
        return bool(_doc_hashes(step.get("in")) & volatile_hashes)

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
    return failures, advisories, max_delta


def _structural_mismatch(expected: dict[str, Any], actual: dict[str, Any]) -> str | None:
    """阶段集合 / 调用次数两个**结构守卫**；不一致时返回失败消息，否则 None。

    比**多重集**而不是原序列：`stages_called` 是调用发生的先后次序，
    而阶段内部存在并发（`_amulti_route_search` 走 asyncio.gather、
    去重走线程池），完成次序天然不定 —— 实测同一份代码两次运行的
    recall / dedup 交错顺序就不同。按序列比对会稳定误报。
    这里断言的是"调用了哪些阶段、各几次"，"以什么输入调用"由 steps 负责。
    """
    exp_stages = sorted(expected.get("stages_called", []))
    act_stages = sorted(actual.get("stages_called", []))
    if exp_stages != act_stages:
        return f"被调用的阶段集合不同：期望 {exp_stages}，实际 {act_stages}"
    exp_steps = expected.get("steps", [])
    act_steps = actual.get("steps", [])
    if len(exp_steps) != len(act_steps):
        return f"阶段调用次数不同：期望 {len(exp_steps)} 次，实际 {len(act_steps)} 次"
    return None


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
    """
    mismatch = _structural_mismatch(expected, actual)
    if mismatch is not None:
        return TraceComparison([mismatch], [], 0)

    exp_steps = expected.get("steps", [])
    act_steps = actual.get("steps", [])
    volatile_hashes, volatile_drifted = _collect_volatile(
        exp_steps, act_steps, volatile_stages, rel_tol
    )
    failures, advisories, max_delta = _judge_steps(
        exp_steps,
        act_steps,
        volatile_stages,
        volatile_hashes,
        volatile_drifted,
        volatile_ratio,
        rel_tol,
    )

    if not _deep_equal(expected.get("final"), actual.get("final"), rel_tol=rel_tol):
        failures.append("最终返回的文档序列变了")

    return TraceComparison(failures, advisories, max_delta)


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
