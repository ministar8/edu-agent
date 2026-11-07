"""集合路由：学科关键词推断与集合路由解析（从 recall.py 拆出，行为等价）。"""

from __future__ import annotations

import re

from rag.common.rag_utils import extract_query_terms, normalize_query_text
from rag.common.synonyms import expand_query_with_synonyms
from rag.retrieval.collections import CODE_COLLECTION, COLLECTION_KEYWORDS, SUBJECT_COLLECTIONS
from rag.retrieval.query_classifier import QueryCategory, classify_query


def _contains_collection_keyword(text: str, keyword: str) -> bool:
    key = keyword.lower()
    if not key:
        return False
    if not re.fullmatch(r"[a-z0-9_./+-]+", key):
        return key in text
    return re.search(rf"(?<![a-z0-9_]){re.escape(key)}(?![a-z0-9_])", text) is not None


def _infer_subject_collections(query: str) -> list[str]:
    normalized = normalize_query_text(query).lower()
    expanded = expand_query_with_synonyms(normalized, max_expansions=6).lower()
    # 空格是**排版差异**、不是语义差异：关键词表里写的是 `ip地址` / `mac地址`，
    # 而查询常写成 `IP 地址` / `MAC 地址`。不做这一步，这类写法**一个关键词都匹配不上**
    # （实测 `'ip地址' in 'ip 地址与 mac 地址有什么区别？'` → False），
    # `resolve_collection_routes` 于是退化成「全 4 科检索」—— 学科收窄机制直接失效，
    # 错学科的文档得以挤进首条。去掉空格再匹配一次即可。
    compact = normalized.replace(" ", "")
    matched: list[str] = []
    for collection, keywords in COLLECTION_KEYWORDS.items():
        if any(
            _contains_collection_keyword(normalized, keyword)
            or _contains_collection_keyword(expanded, keyword)
            or _contains_collection_keyword(compact, keyword)
            for keyword in keywords
        ):
            matched.append(collection)
    return matched


def resolve_collection_routes(
    query: str, collection_name: str, cat: QueryCategory | None = None
) -> list[str]:
    if collection_name:
        return [collection_name]

    # 默认：优先根据学科关键词缩小集合范围，避免每次跨 4 科全量多路召回
    normalized = normalize_query_text(query)
    terms = extract_query_terms(normalized)
    if cat is None:
        cat = classify_query(query, terms)
    collections = _infer_subject_collections(normalized) or list(SUBJECT_COLLECTIONS)

    if cat.is_exercise:
        collections.append("exams")
    # ★ 原先这里要求 `cat.is_structured and 含路径类词` —— **条件过严**：
    # 纯学习路径查询（如「408 应该怎么学」）`is_learning_path=True` 但 `is_structured=False`，
    # 于是拿不到 `learning_paths` 集合（24 chunk 对这类查询**完全不可达**）。
    # 正确的信号是 `cat.is_learning_path`（由 `_RULE_MARKERS["learning_path"]` 判定）；
    # 额外保留「路径 / 路线 / 学习计划」三个标记，是为了覆盖规则表未收录的写法（不丢原有覆盖面）。
    if cat.is_learning_path or any(marker in normalized for marker in ("路径", "路线", "学习计划")):
        collections.append("learning_paths")

    # 代码类查询：额外命中代码库（`code_<科>`），与四科讲义并列召回。
    # （原 `is_code` 曾指向从未创建的 `answers` 集合，见下方注释；现改为指向 code 库。）
    if getattr(cat, "is_code", False):
        for col in list(collections):
            code_col = CODE_COLLECTION.get(col)
            if code_col:
                collections.append(code_col)

    # ⚠️ 这里曾有两条对 `answers` 集合的引用（`is_answer` 与 `is_code` 时追加），
    # 但**该集合从未被创建**：`knowledge/` 下无 `answers/` 目录，
    # `ingest.DEFAULT_CATEGORIES` 也不含它。实测每次命中都抛
    # `Collection [answers] does not exist` —— 白花一次 Chroma 往返，
    # 且这条 WARNING 与「真实集合故障」长得**一模一样**，会掩盖真信号。
    # 2026-09-24 移除。若将来真要建 `answers` 集合（存标准答案供批改），
    # 需连同入库配置一起加回，不要只改这里。
    # 注：`is_code` 原本也指向 `answers` —— 语义上本就不通（代码内容在 4 科集合的
    # `code_mixed` chunk 里），一并去掉。

    deduped: list[str] = []
    seen: set[str] = set()
    for name in collections:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return deduped
