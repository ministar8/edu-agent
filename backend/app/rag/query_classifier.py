"""查询分类器：规则优先（零延迟），LLM 按需兜底（模糊查询）"""

import logging
import re

logger = logging.getLogger(__name__)


class QueryCategory:
    """查询分类结果，供下游路由/策略/阈值使用"""

    __slots__ = (
        "is_code", "is_exercise", "is_answer", "is_structured",
        "is_short", "is_long", "is_concept", "is_comparison",
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
        self.source = source

    def __repr__(self) -> str:
        flags = [
            k for k in (
                "code", "exercise", "answer", "structured",
                "short", "long", "concept", "comparison",
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
    "concept": ("概念", "定义", "是什么", "含义", "意思", "原理", "介绍"),
    "comparison": ("区别", "不同", "差异", "对比", "比较", "相同", "异同"),
}

_LLM_CLASSIFY_PROMPT = (
    "请判断以下学生问题的查询意图类别，只输出命中的类别标签（可多选），用逗号分隔。\n"
    "可选标签：code,exercise,answer,structured,concept,comparison,uncategorized\n\n"
    "问题：{query}\n\n类别："
)

_classify_cache: dict[str, QueryCategory] = {}
_CLASSIFY_CACHE_MAX = 256


def _classify_by_rules(normalized: str, terms: list[str]) -> QueryCategory:
    """规则分类：关键词匹配，零延迟"""
    lowered = normalized.lower()
    flags: dict[str, bool] = {}

    for category, markers in _RULE_MARKERS.items():
        if category == "code":
            flags["code"] = (
                any(m in lowered for m in markers)
                or any(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\.]{1,}", t) is not None for t in terms)
            )
        else:
            flags[category] = any(m in normalized for m in markers)

    is_short = len(terms) <= 1 and len(normalized) <= 12
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
        source="rule",
    )


def _classify_by_llm(query: str) -> QueryCategory | None:
    """LLM 分类兜底：规则无法判断时调用，有延迟"""
    try:
        from langchain_core.output_parsers import StrOutputParser
        from langchain_core.prompts import ChatPromptTemplate
        from app.rag.retriever import get_llm

        llm = get_llm()
        prompt = ChatPromptTemplate.from_template(_LLM_CLASSIFY_PROMPT)
        chain = prompt | llm | StrOutputParser()
        result = chain.invoke({"query": query}).strip().lower()
    except Exception as e:
        logger.debug("LLM classify failed: %s", e)
        return None

    tags = {t.strip() for t in result.split(",") if t.strip()}
    valid_tags = {"code", "exercise", "answer", "structured", "concept", "comparison"}
    matched = tags & valid_tags
    if not matched:
        return None

    return QueryCategory(
        is_code="code" in matched,
        is_exercise="exercise" in matched,
        is_answer="answer" in matched,
        is_structured="structured" in matched,
        is_concept="concept" in matched,
        is_comparison="comparison" in matched,
        source="llm",
    )


def _needs_llm_fallback(rule_cat: QueryCategory) -> bool:
    """判断是否需要 LLM 兜底：规则未命中任何类别且查询长度足够"""
    any_flag = any([
        rule_cat.is_code, rule_cat.is_exercise, rule_cat.is_answer,
        rule_cat.is_structured, rule_cat.is_concept, rule_cat.is_comparison,
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
    normalized = re.sub(r"\s+", " ", str(query).strip())
    if not normalized:
        return QueryCategory(source="rule")

    if terms is None:
        candidates = re.findall(r"[A-Za-z_][A-Za-z0-9_\.]{1,}|[\u4e00-\u9fff]{2,12}", normalized)
        _stop = frozenset({
            "什么", "怎么", "如何", "为什么", "请问", "一下", "有关", "关于",
            "这个", "那个", "哪些", "是否", "可以", "帮我", "讲解", "解释",
        })
        seen: set[str] = set()
        terms = []
        for c in candidates:
            cl = c.strip()
            if cl and cl.lower() not in _stop and cl not in _stop and cl.lower() not in seen:
                seen.add(cl.lower())
                terms.append(cl)
                if len(terms) >= 6:
                    break

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
        _classify_cache.clear()
    _classify_cache[cache_key] = rule_cat

    logger.debug("Query classified: %s → %s", query[:50], rule_cat)
    return rule_cat
