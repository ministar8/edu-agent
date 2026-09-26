"""多路召回构建模块

职责：查询归一化、同义词扩展、关键词提取、召回路由构建、元数据路由、集合路由

由 retriever.py 调用，不直接暴露给外部。
"""

from __future__ import annotations

import logging
import re

from rag.query_classifier import QueryCategory, classify_query
from rag.rag_utils import extract_query_terms, get_bm25_stop_words, normalize_query_text
from rag.synonyms import expand_query_with_synonyms

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
            1
            for kw_list in _COLLECTION_KEYWORDS.values()
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
        focus_terms = ranked_terms[: min(3, len(ranked_terms))]
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
    focus_query = (
        " ".join(ranked[:2]) if len(ranked) >= 2 else (ranked[0] if ranked else normalized)
    )
    metadata_routes: list[tuple[str, str, dict | None]] = []

    if cat is None:
        cat = classify_query(query, terms)

    # ── 按查询类型生成不重复的 metadata 路由 ──

    if cat.is_code:
        metadata_routes.append(
            ("code_meta", focus_query, combine_filters(base_filter, {"content_type": "code_mixed"}))
        )

    # ★ 这两条曾按 `content_type` 过滤，但那个字段**从不产出 exercise / answer**：
    # `detect_content_type` 把这两条规则排在通用形状规则（# 标题 / 列表）之后，
    # 被提前返回吃掉 —— 实测 406 个「题」候选全部落到 list/text/section，路由恒返回空。
    # 现改用 splitter 写入的**语义标志**（`is_exercise_content` / `has_answer_marker`）：
    # 与形状解耦，且**不改 content_type 的判定顺序** → chunk 尺寸与 chunk_id 都不变。
    if cat.is_exercise:
        metadata_routes.append(
            (
                "exercise_meta",
                normalized,
                combine_filters(base_filter, {"is_exercise_content": True}),
            )
        )

    if cat.is_answer:
        metadata_routes.append(
            ("answer_meta", normalized, combine_filters(base_filter, {"has_answer_marker": True}))
        )

    # concept 查询走 section 路由；comparison 查询额外走 table 路由（对比表多为 table 类型）
    if cat.is_concept:
        metadata_routes.append(
            ("concept_meta", focus_query, combine_filters(base_filter, {"content_type": "section"}))
        )
    if cat.is_comparison:
        metadata_routes.append(
            ("concept_meta", focus_query, combine_filters(base_filter, {"content_type": "section"}))
        )
        # 对比查询的核心内容多为对比表，补充 table 路由
        metadata_routes.append(
            (
                "comparison_meta",
                focus_query,
                combine_filters(base_filter, {"content_type": "table"}),
            )
        )

    if cat.is_structured:
        metadata_routes.append(
            ("structured_meta", focus_query, combine_filters(base_filter, {"is_structured": True}))
        )

    # 通用 section 路由：仅当 concept/comparison 未覆盖时添加
    if (
        terms
        and not cat.is_exercise
        and not cat.is_answer
        and not cat.is_concept
        and not cat.is_comparison
    ):
        metadata_routes.append(
            ("section_meta", focus_query, combine_filters(base_filter, {"content_type": "section"}))
        )

    # ── 粒度补充：formula / table / merged_qa ──
    # 结构化/概念查询可能涉及公式或表格，补充精准路由
    # 短查询跳过 formula/table（命中率极低，浪费 Chroma 调用）
    # 对比查询已通过 comparison_meta 覆盖 table，此处不再重复
    if (cat.is_structured or cat.is_concept) and not cat.is_short and not cat.is_comparison:
        metadata_routes.append(
            ("formula_meta", focus_query, combine_filters(base_filter, {"content_type": "formula"}))
        )
        metadata_routes.append(
            ("table_meta", focus_query, combine_filters(base_filter, {"content_type": "table"}))
        )

    # ── `merged_qa_meta` 路由：两轮实测均为净负 → 不加（2026-09-24 定案）──
    # 这条路由曾被删除（backlog #8），理由是「`content_type=merged_qa` 恒不存在 → 路由永远
    # 返回空」：splitter 的 Q&A 检测链断在 `_ANSWER_RE` 认不出真题写法（选项行尾 ✅ +
    # `**解析**：`），于是 `questions/` 一个 merged_qa chunk 都产不出来，旧路由带着一个
    # **从未被校准过的 2.0**。当时留的恢复条件：**先修好生产端，再用门禁重新校准权重**。
    #
    # 【第一轮（问题 4 修复前）】按约定重新引入，触发 exercise/answer、权重 1.5，
    # 用**真实 embedding 路由**校准。路由确实按预期工作（generate 的 merged_qa 占比
    # 65.4% → 79.4%、grade 17.0% → 46.7%），但全部门禁指标退化：
    #   `cat@k` 0.8590 → 0.8205、`kp@k` 0.7821 → **0.7179（−0.064，超容差 3 倍）**、
    #   `kp_mrr` 0.6107 → 0.5661。
    # 当时判定根因是度量口径：真题来自 `questions/`，它不是学科类目 → 「返回真题」被判
    # 「学科未命中」。于是先去修了那个口径（见 `retrieval_gate.load_golden_queries`）。
    #
    # 【第二轮（问题 4 修复后）——**这次纠正了上一轮的诊断**】
    #   `cat@k` 0.8205 → **0.9359**、`cat@1` 0.6731 → **0.8782**  ← 退化大幅缓解，
    #     符合「上一轮 cat@* 的退化是度量口径导致」的预期（generate 的 `cat@1` 已达 1.0000）。
    #   但 `kp@k` **0.7179 → 0.7179 纹丝不动**，仍退化 −0.0642。
    #
    # ★ **这说明 `kp@*` 的退化不是度量口径导致的，而是真实损失**：推高 merged_qa 占比，
    # 就是把**与考点直接对应的讲义章节挤出 top-5**（`grade` 的 `kp@k` 0.7812 → 0.5938，
    # 降幅最大）。而这与 `questions` 类目那种「合法替代来源」**性质不同** ——
    # `20XX_408_exam` 作为「知识点」说不出是哪个考点，若放宽它等于让任意真题命中任意考点，
    # 指标会失去意义。**故不能靠再放宽一次指标来让这条路由"好看"。**
    #
    # 结论：**不加**。收益本就边际（不加时 generate 已有 65.4% 是 merged_qa），
    # 代价是真实的考点覆盖损失。
    #
    # ★ 另一个必须记住的事实：**不加这条路由，merged_qa 也已经被大量召回了** ——
    # generate 类的 top-5 里本就有 65.4% 是 merged_qa（经 `semantic`/`keyword_bm25`/`focus`
    # 等基础路由）。所以「merged_qa 无路由使用」这个描述在 1.2 之后**已不准确**。

    # 去重：同 query + 同 filter 只保留一条
    deduped: list[tuple[str, str, dict | None]] = []
    seen_specs: set[str] = set()
    import json

    for route_name, route_query, route_filter in metadata_routes:
        filter_key = (
            json.dumps(route_filter, sort_keys=True, ensure_ascii=False) if route_filter else ""
        )
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
    ("semantic", "concept"): 2.0,
    ("semantic", "comparison"): 2.0,
    ("semantic", "default"): 1.5,
    # keyword_bm25：代码/习题关键词精准，概念查询偏弱
    ("keyword_bm25", "code"): 2.0,
    ("keyword_bm25", "exercise"): 1.5,
    ("keyword_bm25", "answer"): 1.5,
    ("keyword_bm25", "default"): 1.0,
    # focus：聚焦路由普遍有效
    ("focus", "default"): 1.5,
    # expanded：同义词扩展可能引入噪声，概念查询有增量
    ("expanded", "concept"): 0.8,
    ("expanded", "default"): 0.6,
    # metadata 精准过滤路由：命中率极高，高权重
    ("code_meta", "code"): 2.5,
    ("exercise_meta", "exercise"): 2.5,
    ("answer_meta", "answer"): 2.5,
    ("concept_meta", "concept"): 1.5,
    ("concept_meta", "comparison"): 1.5,
    ("comparison_meta", "comparison"): 2.0,  # 对比表精准路由
    ("structured_meta", "structured"): 2.0,
    ("section_meta", "default"): 1.2,
    ("formula_meta", "concept"): 1.8,
    ("formula_meta", "structured"): 1.8,
    ("table_meta", "concept"): 1.5,
    ("table_meta", "structured"): 1.5,
    # 注：`merged_qa_meta` 的权重曾在此登记（1.5，2026-09-24 校准）。
    # 该路由实测净负（见 `build_metadata_routes` 末尾的说明），已撤销，故此处一并移除。
}

# 查询类型优先级：精确匹配 > default 回退
_CATEGORY_FLAGS = ("code", "exercise", "answer", "concept", "comparison", "structured")


# 全部路由名（**单一真源**，backlog #14）。
#
# 从权重表的键推导，而不是在别处再抄一份名单 ——
# 抄漏会导致某个路由的权重不参与阈值校准，抄多会引入不存在的路由名，
# 两种错误都**不会报错**，只会让阈值静默偏掉。
#
# 需要遍历路由的地方（如 `retriever` 的阈值权重校准）都应从这里取。
ALL_ROUTES: tuple[str, ...] = tuple(dict.fromkeys(route for route, _cat in _ROUTE_WEIGHTS))


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


SUBJECT_COLLECTIONS = [
    "data_structure",
    "computer_organization",
    "operating_system",
    "computer_network",
]

_COLLECTION_KEYWORDS = {
    "data_structure": (
        "数据结构",
        "线性表",
        "顺序表",
        "链表",
        "栈",
        "队列",
        "数组",
        "矩阵",
        "串",
        "kmp",
        "树",
        "二叉树",
        "森林",
        "哈夫曼",
        "图",
        "查找",
        "散列",
        "哈希",
        "排序",
        "avl",
        "红黑树",
        "b树",
        "b+树",
        "最短路径",
        "最小生成树",
        "拓扑排序",
        "关键路径",
        "迪杰斯特拉",
        "弗洛伊德",
        "普里姆",
        "克鲁斯卡尔",
        "bst",
        "rbt",
        "mst",
        "dijkstra",
        "floyd",
        "prim",
        "kruskal",
        "bfs",
        "dfs",
    ),
    "computer_organization": (
        "计组",
        "组成原理",
        "计算机组成",
        "cpu",
        "中央处理器",
        "指令系统",
        "指令周期",
        "指令执行",
        "总线",
        "存储器",
        "cache",
        "高速缓存",
        "主存",
        "磁盘",
        "运算器",
        "控制器",
        "流水线",
        "io系统",
        "输入输出",
        "指令流水线",
        "微程序",
        "中断",
        "dma",
        "寻址方式",
        "浮点数",
        "补码",
        "alu",
        "tlb",
        "快表",
        "页表",
        "段表",
        # 段页式在知识库里**两科都有**（CO 的「存储系统」讲段页式虚拟存储器，
        # OS 的「内存管理」讲段页式存储管理），所以两边都收录 —— 不收窄到单科，
        # 但至少不让它退化成"全 4 科检索"。
        "段页式",
        "虚拟存储器",
        "存储层次",
        "co",
        "i/o",
        "io",
    ),
    "operating_system": (
        "操作系统",
        "进程",
        "线程",
        "进程调度",
        "死锁",
        "同步",
        "互斥",
        "信号量",
        "pv操作",
        "内存管理",
        "分页",
        "分段",
        "段页式",
        "虚拟内存",
        "虚拟存储器",
        "文件管理",
        "文件系统",
        "设备管理",
        "进程通信",
        "管道",
        "共享内存",
        "银行家算法",
        "页面置换",
        "lru",
        "磁盘调度",
        "作业调度",
        "进程状态",
        "就绪",
        "阻塞",
        "时间片",
        "os",
        "pv",
        "p/v",
        "管程",
        "monitor",
        "spooling",
        "spooling技术",
        "fcfs",
        "sjf",
        "rr",
    ),
    "computer_network": (
        "计网",
        "计算机网络",
        "物理层",
        "数据链路层",
        "网络层",
        "传输层",
        "应用层",
        "tcp",
        "udp",
        "ip地址",
        "http",
        "dns",
        "拥塞控制",
        "以太网",
        "三次握手",
        "四次挥手",
        "滑动窗口",
        "子网掩码",
        "mac地址",
        "arp",
        "csma",
        "路由协议",
        "ospf",
        "rip",
        "bgp",
        "nat",
        "dhcp",
        "icmp",
        "曼彻斯特",
        "波特率",
        "带宽",
        "时延",
        "吞吐量",
        "cidr",
        "无类域间路由",
        "tcp/ip",
        "ipv4",
        "ipv6",
        "mtu",
        "mss",
        "rtt",
        "crc",
        "hdlc",
        "ppp",
        "gbn",
        "sr",
    ),
}


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
    for collection, keywords in _COLLECTION_KEYWORDS.items():
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
        collections.append("questions")
    # ★ 原先这里要求 `cat.is_structured and 含路径类词` —— **条件过严**：
    # 纯学习路径查询（如「408 应该怎么学」）`is_learning_path=True` 但 `is_structured=False`，
    # 于是拿不到 `learning_paths` 集合（24 chunk 对这类查询**完全不可达**）。
    # 正确的信号是 `cat.is_learning_path`（由 `_RULE_MARKERS["learning_path"]` 判定）；
    # 额外保留「路径 / 路线 / 学习计划」三个标记，是为了覆盖规则表未收录的写法（不丢原有覆盖面）。
    if cat.is_learning_path or any(marker in normalized for marker in ("路径", "路线", "学习计划")):
        collections.append("learning_paths")

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
