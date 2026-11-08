"""TaskPolicy 解析入口（主路径 ① 的「策略」这一半）。

模型真源：`schema.task_policy.TaskPolicy`（安全/披露：进不进池、答案给不给）。
分类/构建规则见 `docs/RETRIEVAL_POLICY.md` §4。
本模块保持 `resolve_task_policy` / `classify_task_mode` 兼容 API。

★ 与 `retrieval_plan.py` 分工：本文件 → **策略**（TaskPolicy）；
  那边 → **计算预算**（RetrievalStrategy/depth 的 k、skip_*）。不要混称「Plan」。
★ 三层勿混（`docs/RETRIEVAL_POLICY.md` §3.2）：安全/披露（TaskPolicy）·
  计算预算（RetrievalDepth）· 部署开关（settings）。边界由
  `tests/test_rag/test_policy_layers.py` 锁定：本模块不接收、TaskPolicy 也不携带 depth/k/use_rerank。
"""

from __future__ import annotations

import re

from schema.task_policy import (
    ExamResources,
    LegacyPolicy,
    TaskMode,
    TaskPolicy,
)

DEFAULT_TASK_MODE: TaskMode = "learn"

# 显式信号（同句多信号时按 practice > grade > explain > verify > method）
_SIGNAL_PRIORITY: tuple[TaskMode, ...] = (
    "practice",
    "grade",
    "explain",
    "verify",
    "method",
)

_PATTERNS: tuple[tuple[TaskMode, re.Pattern[str]], ...] = (
    ("practice", re.compile(r"练习题|给我一道|出题|出几道|出一道|来一道|生成.{0,6}题|练一练")),
    (
        "grade",
        re.compile(
            r"批改|打分|评分|对不对|是否正确|学生(?:的)?答案|我的答案(?:是|为)?|我选(?:了)?|帮我改"
        ),
    ),
    (
        "explain",
        re.compile(
            r"为什么选|为什么是\s*[A-D]|这道题为什么|怎么理解这题|正确答案是|选\s*[A-D]\s*对不对"
        ),
    ),
    (
        "verify",
        re.compile(r"考过|有没有.{0,6}真题|真题.{0,6}考|哪些.{0,4}真题|是否考过|历年.{0,4}考"),
    ),
    (
        "method",
        re.compile(
            r"怎么做|怎么解|如何求|如何计算|如何还原|怎么还原|解题步骤|方法步骤|算法步骤|步骤是什么|判定|步骤"
        ),
    ),
)

# 有题目上下文 + 为什么 → explain（§4.0 显式可压过 learn）
_WHY = re.compile(r"为什么|为啥|怎么回事")
_ANSWER_LIKE = re.compile(r"我的答案|我选(?:了)?|选(?:项)?\s*[A-D]|答案是|我写的是")
_QUESTION_CTX = re.compile(
    r"(?:19|20)\d{2}\s*[-年]\s*(?:第\s*)?Q?\d+|(?:19|20)\d{2}[-年].{0,12}第\s*\d+\s*题|question:\d{4}-Q\d+|(?:19|20)\d{2}-Q\d+",
    re.I,
)

_PREFERRED: dict[TaskMode, list[str]] = {
    "learn": ["basic", "advanced"],
    "method": ["advanced", "basic"],
    "practice": ["advanced", "basic"],
    "grade": ["exams", "advanced"],
    "explain": ["exams", "advanced", "basic"],
    "verify": ["exams", "advanced"],
}

# legacy（无 kb_depth 旧讲义/题库）= **资产质量/迁移状态**，不是第四知识层。
# 入池策略（legacy_policy）：
#   exclude  = 不进证据包 —— learn/method/practice/verify（主池只认 L1/L2/L3）
#   fallback = 主池不足才补入 —— grade/explain（需要旧题库对照/讲解）
# 实验（evals/results/legacy_runtime）显示真删后层精度 0.38~0.50 → 1.00。
# 不做 downrank：调权重治不了数据治理问题。
_LEGACY_POOL: dict[TaskMode, LegacyPolicy] = {
    "learn": "exclude",
    "method": "exclude",
    "practice": "exclude",
    "grade": "fallback",
    "explain": "fallback",
    "verify": "exclude",
}


def _explicit_mode(query: str) -> TaskMode | None:
    hits: set[TaskMode] = set()
    for mode, pat in _PATTERNS:
        if pat.search(query):
            hits.add(mode)
    # 题目上下文 + 为什么 → explain
    if _QUESTION_CTX.search(query) and _WHY.search(query):
        hits.add("explain")
    for m in _SIGNAL_PRIORITY:
        if m in hits:
            return m
    return None


def classify_task_mode(
    query: str,
    default: TaskMode = DEFAULT_TASK_MODE,
    *,
    context_mode: TaskMode | None = None,
    agent_prior: str = "",
) -> TaskMode:
    """按优先级判定任务模式：会话上下文 → 显式信号 → agent 先验 → 默认。"""
    text = (query or "").strip()
    explicit = _explicit_mode(text)

    if explicit in ("practice", "grade", "explain", "verify"):
        return explicit

    if context_mode == "practice" and _ANSWER_LIKE.search(text):
        return "grade"
    if context_mode == "grade" and explicit is None:
        return "grade"

    if explicit:
        return explicit

    if context_mode in ("learn", "method", "practice", "grade", "explain", "verify"):
        return context_mode

    if agent_prior in ("learn", "method", "practice", "grade", "explain", "verify"):
        return agent_prior  # type: ignore[return-value]

    return default


def _resolve_mode_profile(mode: TaskMode) -> tuple[ExamResources, str, str, str]:
    """返回该 task_mode 的 (exam_resources, answer_policy, explanation_policy, related 策略)。"""
    if mode == "practice":
        return (
            ExamResources(question="forbidden", answer="forbidden", paper="forbidden"),
            "hidden",
            "hidden",
            "off",
        )
    if mode == "verify":
        return (
            ExamResources(question="allowed", answer="forbidden", paper="forbidden"),
            "hidden",
            "hidden",
            "weak",
        )
    if mode == "explain":
        return (
            ExamResources(question="allowed", answer="allowed", paper="allowed"),
            "released",
            "released",
            "strong",
        )
    if mode == "grade":
        return (
            ExamResources(question="allowed", answer="allowed", paper="forbidden"),
            "released",
            "verified_only",
            "weak",
        )
    return (
        ExamResources(question="forbidden", answer="forbidden", paper="forbidden"),
        "hidden",
        "hidden",
        "off",
    )


def _preferred_layers(mode: TaskMode, query: str) -> list[str]:
    """preferred 层默认取自 `_PREFERRED`；grade 再看 query 是否含题号语境决定顺序。"""
    if mode == "grade" and query:
        if _QUESTION_CTX.search(query):
            return ["exams", "advanced", "basic"]
        return ["advanced", "basic", "exams"]
    return list(_PREFERRED[mode])


def policy_for_mode(
    task_mode: TaskMode,
    *,
    layer_policy_id: str = "default",
    query: str = "",
) -> TaskPolicy:
    mode = task_mode
    exam_resources, answer_policy, explanation_policy, related = _resolve_mode_profile(mode)
    preferred = _preferred_layers(mode, query)

    return TaskPolicy(
        task_mode=mode,
        preferred_layers=preferred,  # type: ignore[arg-type]
        exam_resources=exam_resources,
        answer_policy=answer_policy,  # type: ignore[arg-type]
        explanation_policy=explanation_policy,  # type: ignore[arg-type]
        related_exam_policy=related,  # type: ignore[arg-type]
        related_exam_expansion="enabled" if related != "off" else "disabled",
        kp_expansion="enabled",
        graph_expansion="disabled",
        allow_question_id_leak=(mode in ("grade", "explain", "verify")),
        legacy_policy=_LEGACY_POOL[mode],
        layer_policy_id=layer_policy_id,
    )


def resolve_task_policy(
    query: str,
    task_mode: TaskMode | None = None,
    *,
    layer_policy_id: str = "default",
    context_mode: TaskMode | None = None,
    agent_prior: str = "",
) -> TaskPolicy:
    """入口：显式 task_mode 优先，否则按 §4.0 优先级分类。

    ★ 不接收 depth / k / use_rerank —— 算力预算是 `RetrievalDepth` 的职责，
      策略解析不得顺手改写它（边界由 `tests/test_rag/test_policy_layers.py` 锁定）。
    """
    mode = task_mode or classify_task_mode(
        query, context_mode=context_mode, agent_prior=agent_prior
    )
    return policy_for_mode(
        mode,
        layer_policy_id=layer_policy_id,
        query=query,
    )
