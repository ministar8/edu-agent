"""查询分类器：规则优先（零延迟），LLM 按需兜底（模糊查询）"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════
#  Adaptive Depth：查询复杂度 → 检索深度
# ════════════════════════════════════════════════════════

@dataclass(frozen=True)
class RetrievalDepth:
    """检索深度配置：由查询分类自动决定

    depth 级别：
    - shallow:  简单概念查询，k=3，跳过 BM25/KG/分解/HyDE，无元数据路由
    - standard: 一般查询，k=5，限 2 条元数据路由（去冗余）
    - deep:     复杂/对比/长查询，k=8，启用分解+KG 扩展，限 3 条元数据路由
    - code:     代码相关，k=6，code_meta 路由优先，跳过 HyDE，限 2 条元数据路由
    """
    depth: str = "standard"            # shallow / standard / deep / code
    k: int = 5                         # 目标返回文档数
    skip_bm25: bool = False            # 跳过 BM25 路由
    skip_kg: bool = False              # 跳过 KG 补充
    skip_decompose: bool = False       # 跳过查询分解
    skip_hyde: bool = False            # 跳过 HyDE fallback
    skip_metadata_routes: bool = False # 跳过元数据路由（concept_meta 等）
    skip_rerank: bool = False          # 跳过 rerank 重排序（shallow 查询省延迟）
    max_metadata_routes: int = 10      # 元数据路由上限（0=不限制，配合 skip_metadata_routes 使用）
    extra_k_for_deep: int = 0          # deep 模式额外 k 增量

    def __repr__(self) -> str:
        skips = [s for s in ("bm25", "kg", "decompose", "hyde", "meta", "rerank")
                 if getattr(self, f"skip_{s}" if s != "meta" else "skip_metadata_routes")]
        skip_str = f" skip={'+'.join(skips)}" if skips else ""
        meta_cap = f" meta_cap={self.max_metadata_routes}" if self.max_metadata_routes < 10 else ""
        return f"RetrievalDepth({self.depth} k={self.k}{skip_str}{meta_cap})"


# 预定义深度配置
SHALLOW_DEPTH = RetrievalDepth(
    depth="shallow", k=3,
    skip_bm25=True, skip_kg=True, skip_decompose=True, skip_hyde=True,
    skip_metadata_routes=True, max_metadata_routes=0,
    skip_rerank=True,
)
STANDARD_DEPTH = RetrievalDepth(
    depth="standard", k=5,
    max_metadata_routes=2,
)
DEEP_DEPTH = RetrievalDepth(
    depth="deep", k=8,
    skip_bm25=False, skip_kg=False, skip_decompose=False, skip_hyde=False,
    skip_metadata_routes=False, max_metadata_routes=3, extra_k_for_deep=3,
)
CODE_DEPTH = RetrievalDepth(
    depth="code", k=6,
    skip_bm25=False, skip_kg=False, skip_decompose=False, skip_hyde=True,
    skip_metadata_routes=False, max_metadata_routes=2,
)
TEXT_ONLY_DEPTH = RetrievalDepth(
    depth="text_only", k=5,
    skip_kg=True,                          # 跳过 KG 补充，纯文本检索
    skip_bm25=False, skip_decompose=False, skip_hyde=False,
    skip_metadata_routes=False, max_metadata_routes=2,
)


def resolve_retrieval_depth(cat: QueryCategory) -> RetrievalDepth:
    """根据查询分类自动选择检索深度

    规则优先级：
    1. 短查询 + 概念查询 → shallow（省延迟 ~200ms）
    2. 对比查询 / 长查询 → deep（多角度覆盖）
    3. 代码查询 → code（code_meta 优先，不用 HyDE）
    4. 其余 → standard（完整管线）
    """
    if cat.is_learning_path:
        return DEEP_DEPTH if cat.is_long else STANDARD_DEPTH

    if cat.is_short and cat.is_concept:
        return SHALLOW_DEPTH

    if cat.is_short:
        return SHALLOW_DEPTH

    if cat.is_comparison:
        return DEEP_DEPTH

    if cat.is_code:
        return CODE_DEPTH

    if cat.is_exercise or cat.is_answer:
        return STANDARD_DEPTH

    if cat.is_long and cat.is_structured:
        return DEEP_DEPTH

    if cat.is_long and cat.is_concept:
        return DEEP_DEPTH

    return STANDARD_DEPTH


class QueryCategory:
    """查询分类结果，供下游路由/策略/阈值使用"""

    __slots__ = (
        "is_code", "is_exercise", "is_answer", "is_structured",
        "is_short", "is_long", "is_concept", "is_comparison", "is_learning_path",
        "source",  # "rule" | "llm" | "rule+llm"
    )

    def __init__(
        self,
        *,
        is_code: bool = False,
        is_exercise: bool = False,
        is_answer: bool = False,
        is_structured: bool = False,
        is_short: bool = False,
        is_long: bool = False,
        is_concept: bool = False,
        is_comparison: bool = False,
        is_learning_path: bool = False,
        source: str = "rule",
    ) -> None:
        self.is_code = is_code
        self.is_exercise = is_exercise
        self.is_answer = is_answer
        self.is_structured = is_structured
        self.is_short = is_short
        self.is_long = is_long
        self.is_concept = is_concept
        self.is_comparison = is_comparison
        self.is_learning_path = is_learning_path
        self.source = source

    def __repr__(self) -> str:
        flags = [
            k for k in (
                "code", "exercise", "answer", "structured",
                "short", "long", "concept", "comparison", "learning_path",
            )
            if getattr(self, f"is_{k}")
        ]
        return f"QueryCategory([{'+'.join(flags) or 'uncategorized'}] src={self.source})"

    def to_dict(self) -> dict[str, bool | str]:
        return {
            "is_code": self.is_code,
            "is_exercise": self.is_exercise,
            "is_answer": self.is_answer,
            "is_structured": self.is_structured,
            "is_short": self.is_short,
            "is_long": self.is_long,
            "is_concept": self.is_concept,
            "is_comparison": self.is_comparison,
            "is_learning_path": self.is_learning_path,
            "source": self.source,
        }


# 规则关键词表
_RULE_MARKERS: dict[str, tuple[str, ...]] = {
    "code": (
        "代码", "示例", "实现",
        "伪代码", "算法实现",
    ),
    "exercise": ("习题", "练习", "题目", "选择题", "判断题", "填空", "简答题", "出题", "题"),
    "answer": ("答案", "解析", "批改", "评分", "得分", "为什么错", "标准答案"),
    "structured": ("步骤", "流程", "总结", "要点", "区别", "注意事项", "清单", "对比"),
    "concept": ("概念", "定义", "是什么", "什么是", "含义", "意思", "原理", "介绍", "应用", "作用", "用途"),
    "comparison": ("区别", "不同", "差异", "对比", "比较", "相同", "异同"),
    "learning_path": ("怎么学", "如何学", "学习路线", "学习路径", "复习路线", "复习路径", "前置知识", "重点章节", "应该怎么学"),
}

_LLM_CLASSIFY_PROMPT = (
    "判断以下学生问题的查询意图类别（可多选）。\n"
    "可选标签：code, exercise, answer, structured, concept, comparison, learning_path\n"
    "如果没有匹配的类别，返回 uncategorized。\n\n"
    "问题：{query}"
)

_classify_cache: dict[str, QueryCategory] = {}
_CLASSIFY_CACHE_MAX = 256


def _classify_by_rules(normalized: str, terms: list[str]) -> QueryCategory:
    """规则分类：关键词匹配，零延迟"""
    lowered = normalized.lower()
    flags: dict[str, bool] = {}

    for category, markers in _RULE_MARKERS.items():
        if category == "code":
            # 代码标识符匹配：至少 4 字符，避免误匹配 "TCP"、"IP" 等网络缩写
            # 短标识符（3字符如 KMP）由关键词 markers 覆盖
            flags["code"] = (
                any(m in lowered for m in markers)
                or any(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\.]{3,}", t) is not None for t in terms)
            )
        else:
            flags[category] = any(m in normalized for m in markers)

    is_short = len(terms) <= 2 and len(normalized) <= 15
    is_long = len(normalized) >= 40 or len(terms) >= 4

    return QueryCategory(
        is_code=flags.get("code", False),
        is_exercise=flags.get("exercise", False),
        is_answer=flags.get("answer", False),
        is_structured=flags.get("structured", False),
        is_short=is_short,
        is_long=is_long,
        is_concept=flags.get("concept", False),
        is_comparison=flags.get("comparison", False),
        is_learning_path=flags.get("learning_path", False),
        source="rule",
    )


def _classify_by_llm(query: str) -> QueryCategory | None:
    """LLM 分类兜底：规则无法判断时调用，使用 with_structured_output"""
    try:
        from app.rag.rag_utils import get_llm
        from app.rag.schemas import QueryClassifyResult

        llm = get_llm(streaming=False, temperature=0.0)
        structured_llm = llm.with_structured_output(QueryClassifyResult)
        result = structured_llm.invoke(_LLM_CLASSIFY_PROMPT.format(query=query))
    except Exception as e:
        logger.debug("LLM classify failed: %s", e)
        return None

    valid_tags = {"code", "exercise", "answer", "structured", "concept", "comparison", "learning_path"}
    matched = set(result.categories) & valid_tags
    if not matched:
        return None

    return QueryCategory(
        is_code="code" in matched,
        is_exercise="exercise" in matched,
        is_answer="answer" in matched,
        is_structured="structured" in matched,
        is_concept="concept" in matched,
        is_comparison="comparison" in matched,
        is_learning_path="learning_path" in matched,
        source="llm",
    )


def _needs_llm_fallback(rule_cat: QueryCategory) -> bool:
    """判断是否需要 LLM 兜底：规则未命中任何类别且查询长度足够"""
    any_flag = any([
        rule_cat.is_code, rule_cat.is_exercise, rule_cat.is_answer,
        rule_cat.is_structured, rule_cat.is_concept, rule_cat.is_comparison,
        rule_cat.is_learning_path,
    ])
    # 规则已命中 → 不需要 LLM
    if any_flag:
        return False
    # 极短查询（如"你好"）→ 不浪费 LLM 调用
    if rule_cat.is_short:
        return False
    # 中长查询但规则未命中 → LLM 兜底
    return True


def _merge_categories(rule_cat: QueryCategory, llm_cat: QueryCategory) -> QueryCategory:
    """合并规则和 LLM 分类结果：规则优先，LLM 补充"""
    return QueryCategory(
        is_code=rule_cat.is_code or llm_cat.is_code,
        is_exercise=rule_cat.is_exercise or llm_cat.is_exercise,
        is_answer=rule_cat.is_answer or llm_cat.is_answer,
        is_structured=rule_cat.is_structured or llm_cat.is_structured,
        is_short=rule_cat.is_short,
        is_long=rule_cat.is_long,
        is_concept=rule_cat.is_concept or llm_cat.is_concept,
        is_comparison=rule_cat.is_comparison or llm_cat.is_comparison,
        is_learning_path=rule_cat.is_learning_path or llm_cat.is_learning_path,
        source="rule+llm",
    )


def classify_query(query: str, terms: list[str] | None = None) -> QueryCategory:
    """统一查询分类入口：规则优先，LLM 按需兜底

    策略：
    1. 规则关键词匹配（零延迟）→ 命中则直接返回
    2. 规则未命中 + 查询长度足够 → LLM 兜底分类
    3. LLM 也未命中 → 返回规则结果（未分类）

    Args:
        query: 原始查询文本
        terms: 已提取的关键词列表（可选，不传则内部提取）

    Returns:
        QueryCategory 分类结果
    """
    from app.rag.rag_utils import normalize_query_text, extract_query_terms
    normalized = normalize_query_text(query)
    if not normalized:
        return QueryCategory(source="rule")

    if terms is None:
        terms = extract_query_terms(normalized)

    # 缓存检查
    cache_key = normalized
    if cache_key in _classify_cache:
        return _classify_cache[cache_key]

    # 1. 规则分类
    rule_cat = _classify_by_rules(normalized, terms)

    # 2. 判断是否需要 LLM 兜底
    if _needs_llm_fallback(rule_cat):
        llm_cat = _classify_by_llm(query)
        if llm_cat is not None:
            rule_cat = _merge_categories(rule_cat, llm_cat)

    # 缓存
    if len(_classify_cache) > _CLASSIFY_CACHE_MAX:
        # Partial eviction: delete oldest 25% to avoid cache stampede
        _evict_count = max(1, len(_classify_cache) // 4)
        for _key in list(_classify_cache.keys())[:_evict_count]:
            del _classify_cache[_key]
    _classify_cache[cache_key] = rule_cat

    logger.debug("Query classified: %s → %s", query[:50], rule_cat)
    return rule_cat
