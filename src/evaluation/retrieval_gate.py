"""检索质量黄金集回归门禁。

为什么需要它
------------
RAG 检索链的改动（阈值常数、RRF 路由权重、切分策略、去重规则、集合路由）**无法用单测
证明"没让检索变差"** —— 单测只能证明"某个函数返回了预期值"，证明不了端到端命中质量。
本模块把 ``evals/sample_408.jsonl`` 变成可自动判定的回归门禁：
固定查询集 + 固定期望学科 + 固定指标 → 与基线对比，退化即失败。

设计取舍（读之前请先看这三条）
------------------------------
1. **指标锚定在「学科类目」而不是「具体 chunk_id」。**
   类目来自数据集自身的 ``subject`` 标签，是客观 ground truth，不需要人工维护 40 条期望；
   而 chunk 级期望会在任何一次切分/embedding 变更后大面积失效，维护成本远高于收益。

2. **用确定性哈希 embedding 跑（``USE_FAKE_EMBEDDING``），不依赖 TEI。**
   因此它衡量的是**检索管线**（路由 / 融合 / 阈值 / 去重 / 窗口展开）是否退化，
   **不是语义质量**。语义质量由 ``evaluation/cli.py`` 的 RAGAS 离线评测负责。
   推论：门禁必须与基线**同环境**对比，跨 embedding 实现比较数字没有意义。

3. **``empty_result_rate`` 与 ``mean_evidence_count`` 必须一起看。**
   只看 ``category_precision`` 会有一个致命盲区：**返回 0 条时精确率无定义/被算成完美**。
   这两个指标就是用来堵这个盲区的 —— 检索链"静默返回空"是最危险的退化形态。

4. **重排路由按三态区分，而且只测「接线」不测「质量」。**
   生产是 ``use_rerank=True``，门禁曾经一直跑 ``False`` —— 重排相关的代码
   （候选池 expand 倍率、预筛选、``_apply_rerank_threshold``、``rerank_score`` 写入）
   **从未被门禁覆盖**。现在用 ``GATE_RERANK_MODE`` 表达三种口径：

   - ``off``      : ``use_rerank=False``、``RERANK_ENABLED=False`` —— 调用方不要求重排
   - ``on``       : ``use_rerank=True`` 、``RERANK_ENABLED=True``  —— 要求且启用；默认假打分，
                    真实 embedding 发布前可加 ``GATE_USE_REAL_RERANK=1`` 改用 TEI
   - ``disabled`` : ``use_rerank=True`` 、``RERANK_ENABLED=False`` —— **要求了但部署关掉**

   ``disabled`` 是为「生产 ``.env`` 把 rerank 关掉」这个状态补的。它与 ``off`` 的差别
   **不在最终结果，而在代码路径**：``off`` 在闸 2 早返回，``disabled`` 会进入重排阶段
   才被部署开关短路 —— 两者的候选池大小不同（见 ``docs/RERANK_SWITCH_ANALYSIS.md``），
   故指标不可互比。``on`` 走 ``USE_FAKE_RERANK``（确定性字符 bigram 余弦，不需要 TEI），
   但假打分的**分数分布与 bge-reranker 不同**，绝对阈值的行为不代表生产，所以任何一条
   路由的指标**只能与同环境基线比**。``main()`` 会校验 ``_meta.rerank_mode``。

5. **真实 embedding 单独一条，用来补上「语义质量」这个口径空白。**
   默认路由跑确定性哈希 embedding，**只能证明管线没退化**；它上面那几条固定的
   ``hit@1`` 未命中全是跨学科词汇重合，光看假口径无法区分"生产问题"与"假 embedding
   的伪影"。``GATE_USE_REAL_EMBEDDING=1`` 用 ``.env`` 里的 TEI bge-m3 跑同一条链路
   —— 那条路由上仍然未命中的，才值得当成真问题去查。
   ⚠️ **它不进 CI**（CI 无 TEI），定位是发布前的手动对照。
   ``main()`` 会同时校验 ``_meta.embedding_mode`` 与 ``_meta.rerank_mode``；
   ``(embed, rerank)`` 组合**未在 ``SUPPORTED_ROUTES`` 登记时直接拒绝** ——
   宁可明确拒绝，也不要跑出一条没有基线、只能"跳过对比"的假绿。

用法::

    python -m evaluation.retrieval_gate                    # 默认：假 embedding + rerank off
    python -m evaluation.retrieval_gate --update-baseline  # 重录基线（需在 PR 里说明原因）
    python -m evaluation.retrieval_gate --limit 10         # 快速抽查

    # 重排路由（用确定性假打分，无需 TEI）
    GATE_RERANK_MODE=on python -m evaluation.retrieval_gate
    GATE_RERANK_MODE=on python -m evaluation.retrieval_gate --update-baseline
    # 兼容旧写法：GATE_USE_RERANK=1 等价于 GATE_RERANK_MODE=on

    # 生产关闭态（要求重排但部署关掉；复现 .env 的 RERANK_ENABLED=false）
    GATE_RERANK_MODE=disabled python -m evaluation.retrieval_gate

    # 真实 embedding 路由（本地手动跑；需要 TEI 在 .env 配的地址上）
    GATE_USE_REAL_EMBEDDING=1 python -m evaluation.retrieval_gate
    GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=disabled python -m evaluation.retrieval_gate

    # 真实 embedding + 真实 TEI rerank（发布前基线；会调用本地 reranker）
    GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1 \
        python -m evaluation.retrieval_gate --update-baseline
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import shutil
import sys
import tempfile
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 数据集 subject 标签 → 知识库集合名。这是黄金集的 ground truth 来源。
SUBJECT_TO_CATEGORY: dict[str, str] = {
    "ds": "data_structure",
    "co": "computer_organization",
    "os": "operating_system",
    "network": "computer_network",
}

# 「历年真题」集合的类目名。它**不是学科**，故不在 SUBJECT_TO_CATEGORY 里 ——
# 但对**出题类**查询它是**合法证据来源**（见 `load_golden_queries`）。
QUESTIONS_CATEGORY = "questions"

DEFAULT_GOLDEN_PATH = "evals/sample_408.jsonl"
DEFAULT_BASELINE_PATH = "evals/retrieval_baseline.json"
# 重排路由**单独一份基线**：两条路由的指标口径不同（候选池 expand 倍率、粗排 k、
# 是否过双重阈值都不同），混用等于拿苹果比橘子。
RERANK_BASELINE_PATH = "evals/retrieval_baseline_rerank.json"
# 真实 embedding 路由的基线。**与假 embedding 的数字不可比** —— 这是本仓库最危险的
# 一类跨口径对比：两条路由的 hit@1 差异可能全部来自"真/假 embedding"，
# 而不是来自代码改动。
REAL_EMBED_BASELINE_PATH = "evals/retrieval_baseline_real_embed.json"
# 「要求重排但部署关掉」路由的基线（生产 .env 的 RERANK_ENABLED=false 态）。
# 它**不能**复用 RERANK_BASELINE_PATH：两条路由的候选池大小不同（off 在闸 2 早返回，
# disabled 会进入重排阶段才被短路），数字不可互比。
RERANK_DISABLED_BASELINE_PATH = "evals/retrieval_baseline_fake_disabled.json"
# 真实 embedding × 部署关掉重排 —— 唯一真正复现「生产」的组合。
REAL_EMBED_RERANK_DISABLED_BASELINE_PATH = "evals/retrieval_baseline_real_disabled.json"
# 真实 embedding × 真实 TEI rerank —— 发布前语义质量基线。
REAL_EMBED_RERANK_BASELINE_PATH = "evals/retrieval_baseline_real_rerank.json"


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


# 门禁运行参数。写进基线文件，避免"拿不同配置的数字互相比较"。
GATE_K = 5

# ── 路由：rerank 三态 × embedding 两态 ────────────────────────────
#
# rerank 三态（`GATE_RERANK_MODE`）取代了早期的布尔开关 `GATE_USE_RERANK`。
# 布尔表达不了 `disabled` —— 「调用方要求重排、但部署把它关掉」这个**生产关闭态**
# 与 `off`（调用方压根不要求）的 `RERANK_ENABLED` 都是 False，布尔区分不出来，
# 基线口径校验会把两条路由误判成同一条。
#
#   off      : use_rerank=False, RERANK_ENABLED=False  调用方不要求
#   on       : use_rerank=True,  RERANK_ENABLED=True   要求且启用（走假打分）
#   disabled : use_rerank=True,  RERANK_ENABLED=False  要求了但部署关掉 ← 生产关闭态
RERANK_MODES: tuple[str, ...] = ("off", "on", "disabled")


def _resolve_rerank_mode() -> tuple[str, str]:
    """解析 ``GATE_RERANK_MODE``；返回 ``(mode, error)``，``error`` 非空表示配置非法。

    非法值**不静默回退** —— 门禁最怕"看起来跑通了，其实跑的是另一条路由"。
    错误留给 ``main()`` 报出并返回退出码 2（配置错误，非指标退化）。
    """
    raw = os.environ.get("GATE_RERANK_MODE", "").strip().lower()
    if raw:
        if raw in RERANK_MODES:
            return raw, ""
        return "off", f"GATE_RERANK_MODE={raw!r} 非法 —— 可选值：{', '.join(RERANK_MODES)}"
    # 兼容旧写法：GATE_USE_RERANK=1 等价于 mode=on
    if _env_flag("GATE_USE_RERANK"):
        return "on", ""
    return "off", ""


GATE_RERANK_MODE, GATE_RERANK_MODE_ERROR = _resolve_rerank_mode()

# 真实 rerank 只允许和真实 embedding 一起录制，避免把 fake/real 混成同一条基线。
# 默认关闭：fake embedding 的门禁仍使用确定性 fake rerank，保持既有基线可复现。
GATE_USE_REAL_RERANK = _env_flag("GATE_USE_REAL_RERANK")

# 各 mode 对应的 settings 覆盖：(RERANK_ENABLED, USE_FAKE_RERANK)。
# `disabled` 下重排不会执行，故 `USE_FAKE_RERANK` 无意义，取 False。
_MODE_SETTINGS: dict[str, tuple[bool, bool]] = {
    "off": (False, False),
    "on": (True, True),
    "disabled": (False, False),
}

# 真实 embedding 路由开关。**默认关闭**，且**只能在本地跑**（需要 TEI，CI 里没有）。
# 打开：`GATE_USE_REAL_EMBEDDING=1 python -m evaluation.retrieval_gate`
#
# ★ 为什么需要它：默认路由跑 `USE_FAKE_EMBEDDING`（字符 bigram 哈希），它**只保留
# 词汇重叠信号、没有语义泛化能力** —— 门禁因此只能证明「管线没退化」，**证明不了
# 语义质量**。后果很具体：默认路由上那几条固定的 `hit@1` 未命中全是**跨学科词汇
# 重合**，光看假口径无法判断它们是生产问题还是假 embedding 的伪影。这条路由就是
# 用来回答这个问题的。
#
# ⚠️ 它**不进 CI**（CI 无 TEI）。定位是「改动检索语义后、发布前的手动对照」，
# 所以没有对应的 CI 步骤是**有意为之**，不是遗漏。
GATE_USE_REAL_EMBEDDING = _env_flag("GATE_USE_REAL_EMBEDDING")

# 已登记的路由组合 → 基线路径。**未登记的组合一律拒绝**（见 `default_baseline_path`）：
# 宁可明确拒绝，也不要跑出一条没有基线、只能"跳过对比"的假绿。
# 前三条沿用历史文件名，避免重命名既有基线。
SUPPORTED_ROUTES: dict[tuple[str, str], str] = {
    ("fake", "off"): DEFAULT_BASELINE_PATH,
    ("fake", "on"): RERANK_BASELINE_PATH,
    ("fake", "disabled"): RERANK_DISABLED_BASELINE_PATH,
    ("real", "off"): REAL_EMBED_BASELINE_PATH,
    ("real", "on"): REAL_EMBED_RERANK_BASELINE_PATH,
    ("real", "disabled"): REAL_EMBED_RERANK_DISABLED_BASELINE_PATH,
}


def embedding_mode() -> str:
    """当前运行的 embedding 口径：``"real"`` | ``"fake"``。"""
    return "real" if GATE_USE_REAL_EMBEDDING else "fake"


def rerank_mode() -> str:
    """当前运行的 rerank 口径：``"off"`` | ``"on"`` | ``"disabled"``。"""
    return GATE_RERANK_MODE


def rerank_backend() -> str:
    """当前 rerank 实现：``"real"``（TEI）或 ``"fake"``（确定性本地打分）。"""
    return "real" if GATE_USE_REAL_RERANK else "fake"


def rerank_requested() -> bool:
    """检索链的 ``use_rerank`` 入参 —— 「调用方是否**要求**重排」。

    ``off`` → False；``on`` / ``disabled`` → True。
    注意它**不等于**「是否真的会重排」：``disabled`` 下调用方要求了，但部署开关
    （``settings.RERANK_ENABLED``）会在重排阶段把它短路掉。
    """
    return GATE_RERANK_MODE != "off"


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


@dataclass
class MetricSpec:
    """指标的退化方向与容差。"""

    direction: str  # "higher" | "lower"
    tolerance: float


# 容差取 0.02（≈ 1/40 条查询），意味着**单条查询退化即失败**。
_METRIC_SPECS: dict[str, MetricSpec] = {
    "category_hit_at_1": MetricSpec("higher", 0.02),
    "category_hit_at_k": MetricSpec("higher", 0.02),
    "category_mrr": MetricSpec("higher", 0.02),
    "category_precision": MetricSpec("higher", 0.02),
    "empty_result_rate": MetricSpec("lower", 0.0),
    "mean_evidence_count": MetricSpec("higher", 0.5),
    # ── 章级知识点口径（比学科细一档；学科级已饱和，测不出改动） ──
    "kp_hit_at_k": MetricSpec("higher", 0.02),
    "kp_mrr": MetricSpec("higher", 0.02),
    # 被标注的查询条数。容差 0、方向 higher ⇒ **标注被误删会立刻失败**。
    "kp_annotated": MetricSpec("higher", 0.0),
}


@dataclass
class QueryOutcome:
    """单条查询的检索结果（只保留计算指标所需的最小信息）。"""

    query: str
    # 多值：出题类查询的合法证据来源有两处（对应学科讲义 / 历年真题），
    # 见 `load_golden_queries`。单值会把它判成「学科未命中」。
    expected_categories: tuple[str, ...]
    hit_categories: list[str] = field(default_factory=list)
    # 章级知识点（见 `chapter_of_source`）：期望值来自黄金集标注，命中值是逐条证据的章。
    expected_knowledge_points: list[str] = field(default_factory=list)
    hit_knowledge_points: list[str] = field(default_factory=list)

    @property
    def first_correct_rank(self) -> int | None:
        """首个命中**任一**目标类目的排名（1-based）；没有则 None。"""
        expected = set(self.expected_categories)
        for index, cat in enumerate(self.hit_categories, 1):
            if cat in expected:
                return index
        return None

    @property
    def first_correct_kp_rank(self) -> int | None:
        """首个命中目标知识点的排名（1-based）。

        无标注（``expected_knowledge_points`` 为空）时返回 None —— 这类查询不进
        ``kp_hit@k`` / ``kp_mrr`` 的分母，否则「未标注」会被误判成「未命中」。
        """
        if not self.expected_knowledge_points:
            return None
        expected = set(self.expected_knowledge_points)
        for index, label in enumerate(self.hit_knowledge_points, 1):
            if label in expected:
                return index
        return None


@dataclass
class RetrievalMetrics:
    """黄金集上的聚合指标。

    ``kp_*`` 三项按**章级知识点**度量（载体见 ``chapter_of_source``），是比「学科」
    细一档的中间层 —— 学科级已饱和（``category_hit_at_k = 1.0``），测不出检索改动。
    """

    n_queries: int
    category_hit_at_1: float
    category_hit_at_k: float
    category_mrr: float
    category_precision: float
    empty_result_rate: float
    mean_evidence_count: float
    kp_hit_at_k: float = 0.0
    kp_mrr: float = 0.0
    kp_annotated: float = 0.0

    def as_dict(self) -> dict[str, float]:
        return {
            "n_queries": self.n_queries,
            "category_hit_at_1": round(self.category_hit_at_1, 4),
            "category_hit_at_k": round(self.category_hit_at_k, 4),
            "category_mrr": round(self.category_mrr, 4),
            "category_precision": round(self.category_precision, 4),
            "empty_result_rate": round(self.empty_result_rate, 4),
            "mean_evidence_count": round(self.mean_evidence_count, 4),
            "kp_hit_at_k": round(self.kp_hit_at_k, 4),
            "kp_mrr": round(self.kp_mrr, 4),
            "kp_annotated": round(self.kp_annotated, 4),
        }


def compute_metrics(outcomes: list[QueryOutcome]) -> RetrievalMetrics:
    """把逐条检索结果聚合成指标。**纯函数**，不依赖任何运行时环境。"""
    if not outcomes:
        return RetrievalMetrics(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)

    n = len(outcomes)
    hit_at_1 = 0
    hit_at_k = 0
    rr_sum = 0.0
    empty = 0
    correct_total = 0
    returned_total = 0
    # 知识点口径：只有被标注过的查询才进分母（未标注 ≠ 未命中）。
    kp_annotated = 0
    kp_hit_at_k = 0
    kp_rr_sum = 0.0

    for outcome in outcomes:
        rank = outcome.first_correct_rank
        if rank is not None:
            hit_at_k += 1
            rr_sum += 1.0 / rank
            if rank == 1:
                hit_at_1 += 1
        if not outcome.hit_categories:
            empty += 1
        expected = set(outcome.expected_categories)
        correct_total += sum(1 for cat in outcome.hit_categories if cat in expected)
        returned_total += len(outcome.hit_categories)

        if outcome.expected_knowledge_points:
            kp_annotated += 1
            kp_rank = outcome.first_correct_kp_rank
            if kp_rank is not None:
                kp_hit_at_k += 1
                kp_rr_sum += 1.0 / kp_rank

    return RetrievalMetrics(
        n_queries=n,
        category_hit_at_1=hit_at_1 / n,
        category_hit_at_k=hit_at_k / n,
        category_mrr=rr_sum / n,
        category_precision=correct_total / returned_total if returned_total else 0.0,
        empty_result_rate=empty / n,
        mean_evidence_count=returned_total / n,
        kp_hit_at_k=kp_hit_at_k / kp_annotated if kp_annotated else 0.0,
        kp_mrr=kp_rr_sum / kp_annotated if kp_annotated else 0.0,
        kp_annotated=float(kp_annotated),
    )


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


def chapter_of_source(source: str) -> str:
    """从证据的 ``source``（知识库文件名）取**章级知识点标签**。

    ``"05_树与二叉树.md"`` → ``"树与二叉树"``

    ★ 为什么「章」的载体取**文件**而不是 H1 标题：实测 H1 不均匀 ——
    大文件里 H1 = 章（`二、二叉树Binary tree`），小文件里 H1 = 具体主题
    （`3.链栈` / `8.虚拟机`），还有 `1定义` / `3性质` 这类碎片；
    而文件恰好是标准章单元（`05_树与二叉树` / `03_存储系统` / `05_传输层` …）。
    """
    name = Path(str(source)).stem if source else ""
    # 去掉两位编号前缀（`05_树与二叉树` → `树与二叉树`）。
    # 用长度+字符判断而非正则：4 位年份前缀（`2019_408_exam`）不会被误剥。
    if len(name) > 2 and name[:2].isdigit() and name[2] in "_-":
        name = name[3:]
    return name.strip()


def _parse_expected_kps(value: Any) -> tuple[str, ...]:
    """解析黄金集里的 ``metadata.knowledge_points`` 标注。

    容忍两种形态：
    - ``list``（门禁直读 JSONL 时的原形）；
    - 逗号串（``evaluation.dataset`` 会把 list **join 成逗号串**，见其 `:57`）。

    两种都收，是为了让同一份黄金集既能被门禁读、也能被 RAGAS 链路读而不失真。
    """
    if value is None:
        return ()
    items = [str(v) for v in value] if isinstance(value, list) else str(value).split(",")
    return tuple(s.strip() for s in items if s.strip())


def load_golden_queries(
    path: str | Path, limit: int | None = None
) -> list[tuple[str, tuple[str, ...], tuple[str, ...]]]:
    """加载 ``(query, expected_categories, expected_knowledge_points)`` 列表。

    跳过无法映射 subject 的行。``knowledge_points`` 缺失时返回空 tuple ——
    该条不参与 ``kp_hit@k``（未标注 ≠ 未命中，见 ``QueryOutcome.first_correct_kp_rank``）。

    ★ ``expected_categories`` 是**多值**（2026-09-24 起）。原因：对**出题类**查询，
    返回历年真题（`questions` 集合）**恰恰是正确行为** —— 但 `questions` 不是学科，
    原先只认 `SUBJECT_TO_CATEGORY` 映射出的那一个类目，于是「返回真题」被判成
    「学科未命中」（实测 generate 类 `cat@1` 一度只有 0.0312，几乎全判错）。
    现在出题类的合法来源是**「对应学科的讲义」或「历年真题」二者之一**。
    """
    filepath = Path(path)
    if not filepath.exists():
        raise FileNotFoundError(f"黄金集不存在: {filepath}")

    items: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
    with open(filepath, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                logger.warning("黄金集第 %d 行解析失败，跳过", line_num)
                continue
            query = str(raw.get("query", "")).strip()
            meta = raw.get("metadata") or {}
            subject = str(meta.get("subject", "")).strip()
            category = SUBJECT_TO_CATEGORY.get(subject)
            if not query or not category:
                logger.warning("黄金集第 %d 行缺 query 或 subject 无法映射，跳过", line_num)
                continue
            categories: tuple[str, ...] = (category,)
            if str(meta.get("query_type") or "") == "generate":
                categories = (category, QUESTIONS_CATEGORY)
            items.append((query, categories, _parse_expected_kps(meta.get("knowledge_points"))))
            if limit and len(items) >= limit:
                break
    return items


def configure_for_gate(persist_dir: str) -> None:
    """把 settings 切成"离线可跑"形态，并重置模块级单例。

    必须在跑检索前调用。之所以是函数而不是模块级副作用：``settings`` 是 import 期
    构造的单例，测试和 CLI 需要各自决定何时生效。

    ``CHROMA_PORT = 1`` 是为了让 ``VectorStoreManager`` 走 PersistentClient 分支
    （端口 1 不可能有真实服务），从而把索引落到临时目录而不是真实的 ``chroma_db/``。

    **LLM 也必须显式拉回假网关**（不只是设 ``USE_FAKE_MODEL``）：检索链的
    decompose / HyDE 会调 LLM，若这里漏掉，本地（.env 配了真实 key）会真的打线上模型
    —— 温度 0.3，基线不可复现且产生费用；CI（无 key）则抛
    ``openai.OpenAIError: Missing credentials``，实测让 40 条 query 里 6 条崩溃。
    settings 侧已有"USE_FAKE_MODEL 拉回假网关"的逻辑，这里再显式设一次是**故意的重复**：
    门禁的正确性不该依赖 settings 的默认推导，显式声明才能保证任何环境下行为一致。

    同理，``rerank`` 三态由 ``GATE_RERANK_MODE`` 决定，覆盖见 ``_MODE_SETTINGS``：

    - ``on``：默认打开 ``RERANK_ENABLED`` 与 ``USE_FAKE_RERANK``，用于无 TEI 的确定性门禁；
      真实 embedding 发布前若设置 ``GATE_USE_REAL_RERANK=1``，则改用 `.env` 中的 TEI reranker，
      并写入独立的真实 embedding + 真实 rerank 基线。
    - ``disabled``：``RERANK_ENABLED=False``，但检索链**仍然** ``use_rerank=True``
      —— 这正是要复现的生产关闭态（要求了但部署关掉）。该态必须断言"一条都没重排"，
      否则说明部署开关失效（见 ``_assert_route_preconditions``）。

    真实 embedding 路由（``GATE_USE_REAL_EMBEDDING``）是唯一**需要** TEI 的一条：
    它关掉 ``USE_FAKE_EMBEDDING``，改用 ``.env`` 里的 ``EMBEDDING_API_BASE``
    （这里不写死地址 —— 生产地址由 ``.env`` 提供）。**LLM 仍然拉回假网关**：
    那件事与 embedding 无关，且 CI/本地都不该为了跑门禁去打真实模型。
    """
    from core.settings import GATEWAY_DEFAULT_MODEL, Gateway, make_model_ref, settings
    from rag import semantic_cache as sc
    from rag import vectorstore as vs

    settings.USE_FAKE_EMBEDDING = not GATE_USE_REAL_EMBEDDING
    settings.CHROMA_PORT = 1
    settings.CHROMA_PERSIST_DIR = persist_dir
    settings.SEMANTIC_CACHE_ENABLED = False
    if GATE_USE_REAL_RERANK:
        settings.RERANK_ENABLED = True
        settings.USE_FAKE_RERANK = False
    else:
        settings.RERANK_ENABLED, settings.USE_FAKE_RERANK = _MODE_SETTINGS[GATE_RERANK_MODE]

    settings.USE_FAKE_MODEL = True
    fake_ref = make_model_ref(Gateway.FAKE, GATEWAY_DEFAULT_MODEL[Gateway.FAKE])
    settings.DEFAULT_MODEL = fake_ref
    settings.LLM_MODEL = fake_ref

    # 模块级单例在 import 期已按旧 settings 构造，必须重置
    vs._vector_store_manager = None
    sc._semantic_cache = None


def wait_for_index_ready(
    categories: list[str],
    *,
    retries: int = 8,
    delay: float = 0.5,
    repair: bool = True,
) -> dict[str, int]:
    """等每个集合的 HNSW 索引可查询，返回 {集合: 成功前的失败次数}。

    就绪检测实现在 ``VectorStoreManager.wait_until_ready``（生产路径同款）。

    ``repair=True`` 时，对"段文件未落盘"的集合做**一次重建后重试**。门禁这么做有理由：
    这是**一次性索引**，重建无副作用且只要几秒；而该故障在进程内无法等待恢复
    （实测「丢弃句柄」「重开 client」均无效，只有 ``delete_collection`` + 重新入库有效）。
    门禁的价值是稳定反映检索质量，不该被上游索引故障污染成"随机失败"。

    生产路径**不做**自动重建 —— 那里删除集合意味着真实数据丢失，必须人工确认。
    """
    from rag import vectorstore as vs

    manager = vs.get_vector_store_manager()
    ready: dict[str, int] = {}

    for category in categories:
        try:
            ready[category] = manager.wait_until_ready(category, retries=retries, delay=delay)
            continue
        except RuntimeError as exc:
            if not repair:
                raise
            logger.warning("集合 '%s' 索引不可查询，重建后重试：%s", category, exc)

        manager.delete_collection(category)
        build_index([category])
        ready[category] = manager.wait_until_ready(category, retries=retries, delay=delay)

    return ready


def build_index(categories: list[str] | None = None) -> dict[str, int]:
    """用与 ``rag.ingest`` 相同的管线把知识库索引进当前（临时）向量库。

    刻意复用 ``ingest`` 的同一条链路（load → clean → split → enhance → tag → add），
    这样门禁覆盖的是**真实入库路径**，而不是一条评测专用的旁路。
    """
    from rag import vectorstore as vs
    from rag.cleaner import clean_documents
    from rag.enhancer import enhance_documents
    from rag.ingest import DEFAULT_CATEGORIES
    from rag.knowledge_tagger import tag_chunks_with_knowledge_points
    from rag.loader import SUPPORTED_EXTENSIONS, load_single_file
    from rag.splitter import split_documents

    manager = vs.get_vector_store_manager()
    counts: dict[str, int] = {}
    knowledge_dir = Path("knowledge")

    for category in categories or DEFAULT_CATEGORIES:
        dir_path = knowledge_dir / category
        if not dir_path.is_dir():
            continue
        indexed = 0
        for filepath in sorted(p for p in dir_path.rglob("*") if p.is_file()):
            if filepath.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            documents = load_single_file(str(filepath))
            documents = clean_documents(
                documents, dedup=True, fuzzy_dedup=False, fuzzy_threshold=0.9
            )
            chunks = split_documents(documents)
            chunks = enhance_documents(chunks)
            for chunk in chunks:
                chunk.metadata["category"] = category
            chunks = tag_chunks_with_knowledge_points(chunks, fallback_category=category)
            indexed += len(manager.add_documents(chunks, collection_name=category))
        counts[category] = indexed
    return counts


class RerankObservation(NamedTuple):
    """单条 query 的 rerank 观察，供 ``_assert_route_preconditions`` 反静默回退。

    - ``has_evidence``：该 query 是否返回了非空证据（空结果不参与断言）
    - ``has_rerank_score``：证据里出现 ``rerank_score > 0`` —— 重排确实跑过
    - ``rerank_used``：链路**自报**的「本次是否用过重排」

    后两者是**两个独立信号**：交叉验证才能抓出"自报值失真"
    （曾出现：部署开关关掉重排后仍返回 ``rerank_used=True``）。
    """

    has_evidence: bool
    has_rerank_score: bool
    rerank_used: bool


async def run_gate(
    golden_path: str | Path = DEFAULT_GOLDEN_PATH,
    limit: int | None = None,
) -> tuple[
    RetrievalMetrics,
    list[QueryOutcome],
    list[tuple[str, str]],
    list[RerankObservation],
    Counter[str],
]:
    """在黄金集上跑完整检索链。

    Returns:
        ``(指标, 逐条结果, 抛异常的 query 列表, rerank 观察列表, 路由贡献计数)``。
        观察列表供 ``_assert_route_preconditions`` 判定 rerank 是否真的执行了（反静默回退）；
        路由贡献计数是 ``"集合:路由" → 出现在最终证据里的次数``，用于回答
        「13 条召回路由里谁在干活、谁空转」—— 此前只能靠临时脚本统计。

    单条 query 抛异常**不再中断整轮** —— 之前一个异常会让门禁直接崩掉、什么指标都拿不到，
    值班的人只能看到 traceback。现在它被记成一条"空结果 + 错误原因"，门禁照样给出完整
    指标，并在最后单独列出错误、由调用方判为失败。

    这条路径是真实存在的：CI 无 LLM 凭据时 40 条里有 6 条会抛
    ``openai.OpenAIError: Missing credentials``（见 core.llm.get_llm 的说明）。
    """
    from rag.retriever import aretrieve_evidence_with_retry

    queries = load_golden_queries(golden_path, limit=limit)
    outcomes: list[QueryOutcome] = []
    errors: list[tuple[str, str]] = []
    rerank_observations: list[RerankObservation] = []
    route_contributions: Counter[str] = Counter()

    for query, expected, expected_kps in queries:
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
            continue

        categories = [str(ev.metadata.get("category", "")) for ev in fused.text_evidences]
        # 章级知识点：逐条证据的章（来自 source 文件名），按排名顺序排列。
        kp_labels = [chapter_of_source(ev.source) for ev in fused.text_evidences]
        # 路由贡献：每条证据自报的 `recall_routes`（同一文档可被多条路由命中，逐条计入）
        for ev in fused.text_evidences:
            for route in str(ev.metadata.get("recall_routes") or "").replace("|", ",").split(","):
                if route.strip():
                    route_contributions[route.strip()] += 1
        # 记录 rerank 是否真的生效：rerank_score > 0 是「rerank 步骤确实跑过」的可靠信号
        # （真/假 rerank 都会写 >0，只有「跳过 / 异常降级」才写 0.0）。
        rerank_observations.append(
            RerankObservation(
                has_evidence=bool(fused.text_evidences),
                has_rerank_score=any(ev.rerank_score > 0 for ev in fused.text_evidences),
                rerank_used=bool(fused.metadata.get("rerank_used")),
            )
        )
        outcomes.append(
            QueryOutcome(
                query=query,
                expected_categories=expected,
                hit_categories=categories,
                expected_knowledge_points=list(expected_kps),
                hit_knowledge_points=kp_labels,
            )
        )

    return (
        compute_metrics(outcomes),
        outcomes,
        errors,
        rerank_observations,
        route_contributions,
    )


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

    violations: list[str] = []
    # 只关心有非空证据的 query：空结果本就没有 rerank_score，属预期而非失效。
    with_evidence = [o for o in rerank_observations if o.has_evidence]
    reranked_count = sum(1 for o in with_evidence if o.has_rerank_score)
    used_count = sum(1 for o in with_evidence if o.rerank_used)
    mode = rerank_mode()

    if mode == "on":
        if with_evidence and not reranked_count:
            violations.append(
                f"rerank 路由开启，但 {len(with_evidence)} 条有证据的 query 里没有一条 "
                "rerank_score > 0 —— rerank 疑似完全没执行（depth.skip_rerank 被错误全局置 True，"
                "或 reranker 异常降级）"
            )
    else:
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

    # 与 mode 无关的交叉验证：两个信号必须一致。
    inconsistent = sum(1 for o in with_evidence if o.has_rerank_score and not o.rerank_used)
    if inconsistent:
        violations.append(
            f"{inconsistent} 条 query 出现 rerank_score > 0 但 rerank_used=False —— "
            "两个信号自相矛盾，rerank_used 自报值失真"
        )

    if GATE_USE_REAL_EMBEDDING and settings.USE_FAKE_EMBEDDING:
        violations.append(
            "GATE_USE_REAL_EMBEDDING=1 但 settings.USE_FAKE_EMBEDDING 仍为 True —— "
            "真实 embedding 静默退回哈希假 embedding（configure_for_gate 被改坏）"
        )

    return violations


def _build_report(
    metrics: RetrievalMetrics,
    outcomes: list[QueryOutcome],
    baseline: dict[str, Any] | None,
    route_contributions: Counter[str] | None = None,
) -> str:
    lines: list[str] = []
    lines.append("=" * 68)
    lines.append("  检索质量黄金集门禁")
    # 把路由写进标题：各路由的指标不可互比，报告必须自证口径
    _rerank_label = {
        "off": "off",
        "on": f"on ({rerank_backend()})",
        "disabled": "disabled (requested, deployment off)",
    }[rerank_mode()]
    lines.append(f"  路由 embed={embedding_mode()}  rerank={_rerank_label}   k={GATE_K}")
    lines.append("=" * 68)

    current = metrics.as_dict()
    lines.append(f"{'指标':<24}{'当前':>10}{'基线':>10}   判定")
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

    # ── 路由贡献度 ──────────────────────────────────────────────
    # 回答「13 条召回路由里谁在干活、谁空转」—— 此前只能靠临时脚本统计。
    # ⚠️ 零贡献**不等于**该路由无用：黄金集全是概念题，`code_meta` / `exercise_meta` /
    # `answer_meta` / `table_meta` 本就只在对应场景（代码/习题/答案/表格查询）才命中。
    if route_contributions is not None:
        lines.append(
            f"路由贡献度（最终证据里各路由出现次数，合计 {sum(route_contributions.values())} 次）："
        )
        for name, count in route_contributions.most_common():
            lines.append(f"  {count:>5}  {name}")
        if not route_contributions:
            lines.append("  （无）")
        lines.append("")

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


def build_baseline_payload(
    *,
    metrics: RetrievalMetrics,
    golden_path: str | Path,
    indexed_chunks: int,
    route_contributions: Counter[str] | None = None,
) -> dict[str, Any]:
    """构造基线 JSON 的载荷（`_meta` 里记录口径，供 `load_baseline` 校验）。

    ``_meta.route_contributions`` 记录本次各路由的贡献条数 —— 它不是**指标**（无方向/容差，
    故不参与退化判定），而是**口径快照**：将来某条路由静默变成 0 贡献时，可与它对比发现。
    """
    return {
        "_meta": {
            "note": "由 evaluation.retrieval_gate 生成；改动检索链后请用 --update-baseline 重录并在 PR 说明原因",
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
    }


# ── 重录基线前的合理性校验（2026-09-24）───────────────────────────────
# 阈值取值依据：
#   · **偏离 0.10** —— 正常的数据/代码改动远小于此。实测：1.2 改切分让 `cat@k` 动 0.013、
#     `cat_prec` 动 0.031；空结果保底让 real 路由 `cat@k` 动 0.013。
#     而一次 Chroma 索引竞态让 `cat@k` 从 0.7949 掉到 0.5705（Δ0.22）—— 量级差一个数量级。
#   · **空结果率「任何上升」** —— 与 `_METRIC_SPECS` 里 `empty_result_rate` 的
#     容差 0 保持一致（该指标方向 lower、容差 0）。**只查上升**：下降是好事；
#     且不能写成「>0 即拒」—— `real` 路由在修复前合法地处于 0.0192，那样会误伤。
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


def main(argv: list[str] | None = None) -> int:
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
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    # 配置先校验：非法 mode 与未登记的路由组合都直接拒绝，不必花一分钟建索引再说。
    if GATE_RERANK_MODE_ERROR:
        print(f"[拒绝] {GATE_RERANK_MODE_ERROR}", file=sys.stderr)
        return 2

    # 基线先读、先校验：口径不对就没必要花一分钟建索引再告诉你。
    # 即使用户显式传 --baseline，也要先校验当前组合，避免把 real/fake rerank 混录。
    try:
        auto_baseline_path = Path(default_baseline_path())
    except ValueError as exc:
        print(f"[拒绝] {exc}", file=sys.stderr)
        return 2
    baseline_path = Path(args.baseline) if args.baseline else auto_baseline_path

    baseline: dict[str, Any] | None = None
    if not args.update_baseline:
        try:
            baseline = load_baseline(baseline_path)
        except ValueError as exc:
            print(f"[拒绝] {exc}", file=sys.stderr)
            return 2

    tmp_dir = tempfile.mkdtemp(prefix="retrieval_gate_")
    try:
        configure_for_gate(tmp_dir)
        start = time.perf_counter()
        counts = build_index()
        index_seconds = time.perf_counter() - start
        total = sum(counts.values())
        if total == 0:
            print("[错误] 索引为空 —— knowledge/ 目录缺失或全部解析失败", file=sys.stderr)
            return 2
        print(f"索引就绪：{total} chunks（{index_seconds:.1f}s）  {counts}")

        # 必须等 HNSW 落盘，否则会把 Chroma 的间歇性竞态误判成检索退化
        ready = wait_for_index_ready(sorted(counts))
        slow = {name: tries for name, tries in ready.items() if tries}
        if slow:
            print(f"[提示] 以下集合需要重试才可查询（Chroma 落盘竞态）：{slow}")

        start = time.perf_counter()
        metrics, outcomes, errors, rerank_observations, route_contributions = asyncio.run(
            run_gate(args.golden, limit=args.limit)
        )
        query_seconds = time.perf_counter() - start

        preconditions = _assert_route_preconditions(rerank_observations)
        if preconditions:
            print("\n[失败] 路由前提自检未通过（反静默回退）：", file=sys.stderr)
            for item in preconditions:
                print(f"  - {item}", file=sys.stderr)
            return 2

        from rag import vectorstore as vs

        code = report_retrieval_anomalies(
            unexpected_query_failures(vs.get_vector_store_manager().query_failures, set(counts)),
            errors,
        )
        if code is not None:
            return code

        print(_build_report(metrics, outcomes, baseline, route_contributions))
        print(f"索引 {index_seconds:.1f}s / 检索 {query_seconds:.1f}s")

        payload = build_baseline_payload(
            metrics=metrics,
            golden_path=args.golden,
            indexed_chunks=total,
            route_contributions=route_contributions,
        )

        if args.update_baseline:
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
    finally:
        if not args.keep_index:
            shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
