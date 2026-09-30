"""Retrieval Policy 契约（见 docs/RETRIEVAL_POLICY.md）。

机器可执行的检索策略：Task Classifier 产出，tools / retriever / Evidence Policy 消费。

安全边界（冻结）：
- `exam_resources` 管 eligibility（进不进候选池）
- `answer_policy` 等管 release（Evidence Pack 能给什么）
- `layer_policy_id` 只指排序 profile，**不得**改安全字段
- `allow_question_id_leak` 只约束 Evidence Pack，不删索引 metadata

禁止 import rag / agents —— 本模块是纯契约。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

TaskMode = Literal["learn", "method", "practice", "grade", "explain", "verify"]
LayerName = Literal["basic", "advanced", "exams"]
ExamResourceName = Literal["question", "answer", "paper"]
ResourceAccess = Literal["allowed", "forbidden"]
AnswerPolicy = Literal["hidden", "released"]
ExplanationPolicy = Literal["hidden", "released", "verified_only"]
RelatedExamPolicy = Literal["off", "weak", "strong"]
ExpansionToggle = Literal["enabled", "disabled"]
GraphExpansion = Literal["disabled"]
# legacy 是**资产质量/迁移状态**，不是第四知识层：
#   exclude  = 不进证据包（learn/method/practice/verify）
#   fallback = 主池不足时才补入（grade/explain，需要旧题库对照）
#   include  = 与主池同等入池（调试/特殊场景）
# 不做 downrank —— 调权重治不了数据治理问题。
LegacyPolicy = Literal["exclude", "fallback", "include"]
RetrievalDepthName = Literal["shallow", "standard", "deep", "code", "text_only"]

# 语义知识层全集（L1/L2/L3）。legacy **不在**此列。
SEMANTIC_LAYERS: tuple[str, ...] = ("basic", "advanced", "exams")

POLICY_VERSION = "1.0"
CACHE_SCOPE = "policy_v1"


def _default_preferred_layers() -> list[LayerName]:
    return ["basic", "advanced"]


class ExamResources(BaseModel):
    """L3 三种资产的候选资格（eligibility）。"""

    question: ResourceAccess = "forbidden"
    answer: ResourceAccess = "forbidden"
    paper: ResourceAccess = "forbidden"

    def allows(self, resource: ExamResourceName) -> bool:
        return getattr(self, resource) == "allowed"


class TaskPolicy(BaseModel):
    """一次检索的完整策略对象（唯一策略真源）。"""

    # —— 身份 ——
    task_mode: TaskMode = "learn"
    policy_version: str = POLICY_VERSION
    layer_policy_id: str = "default"

    # —— 知识层（soft 偏好；只含 L1/L2/L3）——
    preferred_layers: list[LayerName] = Field(default_factory=_default_preferred_layers)
    excluded_layers: list[LayerName] = Field(default_factory=list)
    # 资产质量/迁移状态（fallback 池策略），**不是**层权重
    legacy_policy: LegacyPolicy = "fallback"

    # —— L3 资源资格 ——
    exam_resources: ExamResources = Field(default_factory=ExamResources)

    # —— 披露 ——
    answer_policy: AnswerPolicy = "hidden"
    explanation_policy: ExplanationPolicy = "hidden"
    related_exam_policy: RelatedExamPolicy = "off"

    # —— 图/扩展 ——
    kp_expansion: ExpansionToggle = "enabled"
    graph_expansion: GraphExpansion = "disabled"
    related_exam_expansion: ExpansionToggle = "disabled"

    # —— 计算预算（可随 query complexity 升级，不改安全字段）——
    depth: RetrievalDepthName = "standard"
    k: int | None = None
    use_rerank: bool = True

    # —— 安全（release / 缓存）——
    allow_question_id_leak: bool = False
    cache_scope: str = CACHE_SCOPE

    @model_validator(mode="after")
    def _check_safety_invariants(self) -> TaskPolicy:
        """非法组合在构建时拒绝（见 RETRIEVAL_POLICY.md §3.3）。"""
        mode = self.task_mode
        ar = self.exam_resources

        if mode == "practice":
            if ar.question != "forbidden" or ar.answer != "forbidden" or ar.paper != "forbidden":
                raise ValueError("practice: exam_resources 必须全部 forbidden")
            if self.answer_policy != "hidden":
                raise ValueError("practice: answer_policy 必须 hidden")
            if self.explanation_policy != "hidden":
                raise ValueError("practice: explanation_policy 必须 hidden")
            if self.related_exam_policy != "off":
                raise ValueError("practice: related_exam_policy 必须 off")
            if self.allow_question_id_leak:
                raise ValueError("practice: allow_question_id_leak 必须 false")
            if self.graph_expansion != "disabled":
                raise ValueError("practice: graph_expansion 必须 disabled")

        if mode in ("learn", "method"):
            if ar.answer != "forbidden":
                raise ValueError(f"{mode}: exam_resources.answer 必须 forbidden")
            if self.answer_policy != "hidden":
                raise ValueError(f"{mode}: answer_policy 必须 hidden")

        if mode == "verify":
            if ar.question != "allowed":
                raise ValueError("verify: exam_resources.question 必须 allowed")
            if ar.answer != "forbidden":
                raise ValueError("verify: exam_resources.answer 必须 forbidden")
            if self.answer_policy != "hidden":
                raise ValueError("verify: answer_policy 必须 hidden")
            if not self.allow_question_id_leak:
                raise ValueError("verify: allow_question_id_leak 必须 true（列表题号）")

        if mode in ("explain", "grade"):
            if ar.answer != "allowed":
                raise ValueError(f"{mode}: exam_resources.answer 必须 allowed")
            if self.answer_policy != "released":
                raise ValueError(f"{mode}: answer_policy 必须 released")

        if self.graph_expansion != "disabled":
            raise ValueError("V1 graph_expansion 恒为 disabled")

        return self

    def cache_key_parts(self) -> tuple[str, ...]:
        """语义缓存 key 必含片段（安全隔离）。"""
        return (
            self.task_mode,
            self.depth,
            self.layer_policy_id,
            self.policy_version,
            self.cache_scope,
        )

    # —— 兼容属性（tools / evidence_policy）——
    @property
    def answer_released(self) -> bool:
        return self.answer_policy == "released"

    @property
    def explanation_released(self) -> bool:
        return self.explanation_policy in ("released", "verified_only")

    @property
    def eligibility_block_exam_answer(self) -> bool:
        return not self.exam_resources.allows("answer")

    @property
    def eligibility_block_exam_item(self) -> bool:
        return not self.exam_resources.allows("question")

    @property
    def eligibility_block_exam_paper(self) -> bool:
        return not self.exam_resources.allows("paper")

    @property
    def eligibility_block_question_ids(self) -> bool:
        """practice：Pack 不得出现题号。"""
        return self.task_mode == "practice"

    def eligibility_where(self) -> dict | None:
        """召回侧 Chroma where（安全前置，见 RETRIEVAL_LAYER_DESIGN §6）。

        只约束 `doc_role` / `kb_depth`；与 Evidence Policy 双保险。
        practice/learn/method 全面禁 L3 时，同时排除 `kb_depth=exams`，
        避免旧 `questions/` 无 doc_role  chunk 钻空。
        """
        ne: list[dict] = []
        if not self.exam_resources.allows("answer"):
            ne.append({"doc_role": {"$ne": "exam_answer"}})
        if not self.exam_resources.allows("question"):
            ne.append({"doc_role": {"$ne": "exam_item"}})
        if not self.exam_resources.allows("paper"):
            ne.append({"doc_role": {"$ne": "exam_paper"}})
        # 三种 L3 资源全禁时，整体不要 kb_depth=exams（含旧无 doc_role 题库）
        if all(not self.exam_resources.allows(r) for r in ("question", "answer", "paper")):
            ne.append({"kb_depth": {"$ne": "exams"}})
        if not ne:
            return None
        if len(ne) == 1:
            return ne[0]
        return {"$and": ne}


def merge_where_filters(*filters: dict | None) -> dict | None:
    """合并多个 Chroma where；全空返回 None。"""
    parts = [f for f in filters if f]
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return {"$and": parts}


class LayerWeightProfile(BaseModel):
    """排序权重 profile（layer_policy_id 指向的实验表）。

    ★ 白名单：只允许排序/计算相关字段；安全字段出现即拒绝。
    ★ layer_weights 的键**只能是语义层**（basic/advanced/exams）——
      legacy 是资产质量/迁移状态，用 `legacy_policy` 管，不进权重表。
    """

    name: str = "default"
    layer_weights: dict[str, float] = Field(
        default_factory=lambda: {"basic": 1.0, "advanced": 1.0, "exams": 1.0}
    )
    rerank_coefficient: float = 1.0
    top_k: int | None = None
    kp_expansion_weight: float = 0.5

    @model_validator(mode="after")
    def _reject_security_fields(self) -> LayerWeightProfile:
        forbidden = {
            "answer_policy",
            "explanation_policy",
            "related_exam_policy",
            "exam_resources",
            "allow_question_id_leak",
            "allow_exam_answer_chunk",
            "leakage_threshold",
        }
        extra = forbidden.intersection(self.model_fields_set)
        # model_fields_set 只含本模型字段；用 dump 检查未知键由 extra=forbid 保证
        if extra:
            raise ValueError(f"layer_policy profile 不得包含安全字段: {sorted(extra)}")
        return self

    @model_validator(mode="after")
    def _reject_legacy_as_layer(self) -> LayerWeightProfile:
        bad = set(self.layer_weights) - set(SEMANTIC_LAYERS)
        if bad:
            raise ValueError(
                f"layer_weights 只含语义层 {SEMANTIC_LAYERS}，不得包含 {sorted(bad)}"
                "（legacy 是资产质量，用 legacy_policy 管）"
            )
        return self

    model_config = {"extra": "forbid"}
