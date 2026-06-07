"""多路召回构建模块

职责：查询归一化、同义词扩展、关键词提取、召回路由构建、元数据路由、集合路由

由 retriever.py 调用，不直接暴露给外部。
"""

from __future__ import annotations

import logging
import re

from app.rag.query_classifier import classify_query, QueryCategory
from app.rag.synonyms import expand_query_with_synonyms
from app.rag.rag_utils import normalize_query_text, extract_query_terms, get_bm25_stop_words

logger = logging.getLogger(__name__)

_BM25_STOP_WORDS = get_bm25_stop_words()


def _contains_collection_keyword(text: str, keyword: str) -> bool:
    key = keyword.lower()
    if not key:
        return False
    if not re.fullmatch(r"[a-z0-9_./+-]+", key):
        return key in text
    return re.search(rf"(?<![a-z0-9_]){re.escape(key)}(?![a-z0-9_])", text) is not None


def combine_filters(base_filter: dict | None, extra_filter: dict | None) -> dict | None:
    if not base_filter:
        return extra_filter
    if not extra_filter:
        return base_filter
    return {"$and": [base_filter, extra_filter]}


def _rank_terms_by_specificity(terms: list[str]) -> list[str]:
    """按领域特异性排序：只匹配1个学科的词比匹配4个学科的词更有区分度

    例如 "操作系统进程调度算法" → terms=["操作系统","进程","调度","算法"]
      "操作系统" 匹配 1 个集合 → specificity=1.0
      "进程" 匹配 2 个集合 → specificity=0.5
      → focus 应取 "操作系统 进程" 而非 "操作系统 进程"（同）
      但对 "进程调度算法" → "调度" 匹配 2 个集合 vs "算法" 匹配 0 个
      → "算法" 更通用但无集合匹配，"调度" 更有区分度
    """
    if len(terms) <= 2:
        return terms

    scores: list[tuple[str, float]] = []
    for term in terms:
        matched = sum(
            1 for kw_list in _COLLECTION_KEYWORDS.values()
            if any(term.lower() in kw.lower() for kw in kw_list)
        )
        # 匹配集合越少 → 越有区分度 → 权重越高
        # 0 个匹配 = 通用词（如"算法"），给中等权重 0.5
        specificity = 1.0 / max(matched, 1) if matched > 0 else 0.5
        scores.append((term, specificity))

    scores.sort(key=lambda x: x[1], reverse=True)
    return [t for t, _ in scores]


def build_recall_queries(
    query: str,
    cat: QueryCategory | None = None,
) -> list[tuple[str, str]]:
    """构建多路召回查询

    路由策略：
    - semantic: 完整 query 走向量语义检索
    - keyword_bm25: 关键词走 BM25 全文检索
    - focus: 核心关键词走向量检索（短词组语义聚焦）
    - expanded: 同义词扩展 query 走向量检索
    - kg_expand: 知识图谱关联扩展

    剪枝策略（按查询类型跳过低效路由）：
    - 短查询/代码查询：跳过 expanded（同义词扩展引入噪声）
    - 代码查询：保留 focus（"银行家 算法" 比全句更精准）
    """
    normalized = normalize_query_text(query)
    if cat is None:
        terms = extract_query_terms(normalized)
        cat = classify_query(query, terms)

    routes: list[tuple[str, str]] = []
    if normalized:
        routes.append(("semantic", normalized))

    keyword_terms = extract_query_terms(normalized)
    # BM25 路由传原始 query，让 _raw_search 用 jieba.cut_for_search 做多粒度分词
    # 避免双重处理（recall 预分词 → retriever 再分词）
    if normalized:
        routes.append(("keyword_bm25", normalized))
    # focus 路由：按领域特异性排序后取最有区分度的 2-3 个核心词
    if len(keyword_terms) >= 2:
        ranked_terms = _rank_terms_by_specificity(keyword_terms)
        focus_terms = ranked_terms[:min(3, len(ranked_terms))]
        routes.append(("focus", " ".join(focus_terms)))

    # expanded 路由：短查询仅在含英文缩写时启用
    if not cat.is_code:
        expanded = expand_query_with_synonyms(normalized, max_expansions=4 if cat.is_short else 6)
        if expanded != normalized and (not cat.is_short or re.search(r"[A-Za-z]", normalized)):
            routes.append(("expanded", expanded))

    deduped: list[tuple[str, str]] = []
    seen_specs: set[str] = set()
    for route_name, route_query in routes:
        # 不同路由允许相同 query（如 semantic 和 keyword_bm25 都用完整 query）
        spec_key = f"{route_name}:{route_query.lower()}"
        if not route_query or spec_key in seen_specs:
            continue
        seen_specs.add(spec_key)
        deduped.append((route_name, route_query))
    return deduped


def build_metadata_routes(
    query: str,
    base_filter: dict | None = None,
    cat: QueryCategory | None = None,
    terms: list[str] | None = None,
) -> list[tuple[str, str, dict | None]]:
    """构建元数据过滤路由

    去重原则：同 query + 同 filter 只搜一次，避免浪费 Chroma 调用。
    粒度补充：formula/table 类型有独立检索价值。
    剪枝：短查询跳过 formula/table 粒度路由（大概率空结果）。
    """
    normalized = normalize_query_text(query)
    if terms is None:
        terms = extract_query_terms(normalized)
    # focus_query 用特异性排序，取最有区分度的词
    ranked = _rank_terms_by_specificity(terms) if terms else []
    focus_query = " ".join(ranked[:2]) if len(ranked) >= 2 else (ranked[0] if ranked else normalized)
    metadata_routes: list[tuple[str, str, dict | None]] = []

    if cat is None:
        cat = classify_query(query, terms)

    # ── 按查询类型生成不重复的 metadata 路由 ──

    if cat.is_code:
        metadata_routes.append(
            ("code_meta", focus_query, combine_filters(base_filter, {"content_type": "code_mixed"}))
        )

    if cat.is_exercise:
        metadata_routes.append(
            ("exercise_meta", normalized, combine_filters(base_filter, {"content_type": "exercise"}))
        )

    if cat.is_answer:
        metadata_routes.append(
            ("answer_meta", normalized, combine_filters(base_filter, {"content_type": "answer"}))
        )

    # concept + comparison 合并为一条 section 路由（filter 相同，避免重复）
    if cat.is_concept or cat.is_comparison:
        metadata_routes.append(
            ("concept_meta", focus_query, combine_filters(base_filter, {"content_type": "section"}))
        )

    if cat.is_structured:
        metadata_routes.append(
            ("structured_meta", focus_query, combine_filters(base_filter, {"is_structured": True}))
        )

    # 通用 section 路由：仅当 concept/comparison 未覆盖时添加
    if terms and not cat.is_exercise and not cat.is_answer and not cat.is_concept and not cat.is_comparison:
        metadata_routes.append(
            ("section_meta", focus_query, combine_filters(base_filter, {"content_type": "section"}))
        )

    # ── 粒度补充：formula / table / merged_qa ──
    # 结构化/概念查询可能涉及公式或表格，补充精准路由
    # 短查询跳过 formula/table（命中率极低，浪费 Chroma 调用）
    if (cat.is_structured or cat.is_concept) and not cat.is_short:
        metadata_routes.append(
            ("formula_meta", focus_query, combine_filters(base_filter, {"content_type": "formula"}))
        )
        metadata_routes.append(
            ("table_meta", focus_query, combine_filters(base_filter, {"content_type": "table"}))
        )

    # 习题/答案查询补充 merged_qa 路由（真题 Q&A 合并块）
    if cat.is_exercise or cat.is_answer:
        metadata_routes.append(
            ("merged_qa_meta", normalized, combine_filters(base_filter, {"content_type": "merged_qa"}))
        )

    # 去重：同 query + 同 filter 只保留一条
    deduped: list[tuple[str, str, dict | None]] = []
    seen_specs: set[str] = set()
    import json
    for route_name, route_query, route_filter in metadata_routes:
        filter_key = json.dumps(route_filter, sort_keys=True, ensure_ascii=False) if route_filter else ""
        spec_key = f"{route_query.lower()}::{filter_key}"
        if not route_query or spec_key in seen_specs:
            continue
        seen_specs.add(spec_key)
        deduped.append((route_name, route_query, route_filter))
    return deduped


# ── 路由权重表（加权 RRF） ──────────────────────────────────
# 不同路由对不同查询类型的可靠性不同，用规则引擎替代等权 RRF。
# (route_name, query_flag) → weight
_ROUTE_WEIGHTS: dict[tuple[str, str], float] = {
    # semantic：概念/对比查询语义强，代码查询偏弱
    ("semantic", "concept"):     2.0,
    ("semantic", "comparison"):  2.0,
    ("semantic", "default"):     1.5,
    # keyword_bm25：代码/习题关键词精准，概念查询偏弱
    ("keyword_bm25", "code"):       2.0,
    ("keyword_bm25", "exercise"):   1.5,
    ("keyword_bm25", "answer"):     1.5,
    ("keyword_bm25", "default"):    1.0,
    # focus：聚焦路由普遍有效
    ("focus", "default"):        1.5,
    # expanded：同义词扩展可能引入噪声，概念查询有增量
    ("expanded", "concept"):     0.8,
    ("expanded", "default"):     0.6,
    # metadata 精准过滤路由：命中率极高，高权重
    ("code_meta", "code"):              2.5,
    ("exercise_meta", "exercise"):      2.5,
    ("answer_meta", "answer"):          2.5,
    ("concept_meta", "concept"):        1.5,
    ("concept_meta", "comparison"):      1.5,
    ("structured_meta", "structured"):   2.0,
    ("section_meta", "default"):         1.2,
    ("formula_meta", "concept"):         1.8,
    ("formula_meta", "structured"):      1.8,
    ("table_meta", "concept"):           1.5,
    ("table_meta", "structured"):        1.5,
    ("merged_qa_meta", "exercise"):      2.0,
    ("merged_qa_meta", "answer"):        2.0,
}

# 查询类型优先级：精确匹配 > default 回退
_CATEGORY_FLAGS = ("code", "exercise", "answer", "concept", "comparison", "structured")


def get_route_weight(route_name: str, cat: QueryCategory | None = None) -> float:
    """根据路由名和查询分类获取 RRF 权重

    route_name 可能是复合格式 "collection:route"（如 "os:concept_meta"），
    自动提取纯路由名部分进行权重匹配。
    """
    # 提取纯路由名（去掉集合前缀）
    pure_route = route_name.rsplit(":", 1)[-1] if ":" in route_name else route_name
    if cat is None:
        return _ROUTE_WEIGHTS.get((pure_route, "default"), 1.0)
    # 先精确匹配 (route, category)，再回退 (route, default)
    for flag in _CATEGORY_FLAGS:
        if getattr(cat, f"is_{flag}", False):
            key = (pure_route, flag)
            if key in _ROUTE_WEIGHTS:
                return _ROUTE_WEIGHTS[key]
    return _ROUTE_WEIGHTS.get((pure_route, "default"), 1.0)


SUBJECT_COLLECTIONS = ["data_structure", "computer_organization", "operating_system", "computer_network"]

_COLLECTION_KEYWORDS = {
    "data_structure": (
        "数据结构", "线性表", "顺序表", "链表", "栈", "队列", "数组", "矩阵", "串", "kmp",
        "树", "二叉树", "森林", "哈夫曼", "图", "查找", "散列", "哈希", "排序",
        "avl", "红黑树", "b树", "b+树", "最短路径", "最小生成树", "拓扑排序",
        "关键路径", "迪杰斯特拉", "弗洛伊德", "普里姆", "克鲁斯卡尔",
        "bst", "rbt", "mst", "dijkstra", "floyd", "prim", "kruskal", "bfs", "dfs",
    ),
    "computer_organization": (
        "计组", "组成原理", "计算机组成", "cpu", "中央处理器", "指令系统", "总线", "存储器",
        "cache", "高速缓存", "主存", "磁盘", "运算器", "控制器", "流水线", "io系统", "输入输出",
        "指令流水线", "微程序", "中断", "dma", "寻址方式", "浮点数", "补码", "alu",
        "tlb", "快表", "页表", "段表", "虚拟存储器", "存储层次", "co", "i/o", "io",
    ),
    "operating_system": (
        "操作系统", "进程", "线程", "进程调度", "死锁", "同步", "互斥", "信号量", "pv操作",
        "内存管理", "分页", "分段", "虚拟内存", "虚拟存储器", "文件管理", "文件系统", "设备管理",
        "进程通信", "管道", "共享内存", "银行家算法", "页面置换", "lru", "磁盘调度",
        "作业调度", "进程状态", "就绪", "阻塞", "时间片",
        "os", "pv", "p/v", "管程", "monitor", "spooling", "spooling技术", "fcfs", "sjf", "rr",
    ),
    "computer_network": (
        "计网", "计算机网络", "物理层", "数据链路层", "网络层", "传输层",
        "应用层", "tcp", "udp", "ip地址", "http", "dns", "拥塞控制", "以太网",
        "三次握手", "四次挥手", "滑动窗口", "子网掩码", "mac地址", "arp",
        "csma", "路由协议", "ospf", "rip", "bgp", "nat", "dhcp", "icmp",
        "曼彻斯特", "波特率", "带宽", "时延", "吞吐量",
        "cidr", "无类域间路由", "tcp/ip", "ipv4", "ipv6", "mtu", "mss", "rtt", "crc",
        "hdlc", "ppp", "gbn", "sr",
    ),
}


def _infer_subject_collections(query: str) -> list[str]:
    normalized = normalize_query_text(query).lower()
    expanded = expand_query_with_synonyms(normalized, max_expansions=6).lower()
    matched: list[str] = []
    for collection, keywords in _COLLECTION_KEYWORDS.items():
        if any(_contains_collection_keyword(normalized, keyword) or _contains_collection_keyword(expanded, keyword) for keyword in keywords):
            matched.append(collection)
    return matched


def resolve_collection_routes(query: str, collection_name: str,
                             cat: QueryCategory | None = None) -> list[str]:
    if collection_name:
        return [collection_name]

    # 默认：优先根据学科关键词缩小集合范围，避免每次跨 4 科全量多路召回
    normalized = normalize_query_text(query)
    terms = extract_query_terms(normalized)
    if cat is None:
        cat = classify_query(query, terms)
    collections = _infer_subject_collections(normalized) or list(SUBJECT_COLLECTIONS)

    if cat.is_answer:
        collections.append("answers")
    if cat.is_exercise:
        collections.append("questions")
    if cat.is_structured and any(marker in normalized for marker in ("路径", "路线", "怎么学", "学习计划", "学习路径")):
        collections.append("learning_paths")
    if cat.is_code:
        collections.append("answers")

    deduped: list[str] = []
    seen: set[str] = set()
    for name in collections:
        if name in seen:
            continue
        seen.add(name)
        deduped.append(name)
    return deduped
