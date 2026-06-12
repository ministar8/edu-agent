"""Neo4j 知识图谱管理器

支持分层模糊匹配（Tier 0-3）、节点溯源（source_file）、
删除同步、孤儿检测与一致性健康检查。
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from neo4j import GraphDatabase, Query

from app.config import settings
from app.rag.synonyms import expand_synonyms_for_kg

logger = logging.getLogger(__name__)

# ── 模糊匹配辅助函数 ──────────────────────────────────────────────


def _char_jaccard(a: str, b: str) -> float:
    """字符级 Jaccard 相似度，用于 Tier 2 子串匹配的泛化约束"""
    set_a, set_b = set(a), set(b)
    union = set_a | set_b
    return len(set_a & set_b) / len(union) if union else 0.0


def _safe_depth(value: int, default: int = 2, max_depth: int = 5) -> int:
    try:
        depth = int(value)
    except (TypeError, ValueError):
        depth = default
    return max(1, min(depth, max_depth))


_KG_QUERY_TIMEOUT = 3.0
_KG_MAX_RECORDS = 50


class KnowledgeGraphManager:
    """Neo4j 知识图谱管理器"""

    # TTL 缓存配置（秒）
    _CACHE_TTL = 300  # 5 分钟
    _CACHE_MAX_SIZE = 200

    def __init__(self) -> None:
        self._driver = None
        self._cache: dict[str, tuple[float, Any]] = {}  # key → (expire_at, value)

    @property
    def driver(self):
        """懒加载 Neo4j 连接"""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                connection_timeout=1.0,
                connection_acquisition_timeout=3.0,
                max_connection_pool_size=20,
                max_transaction_retry_time=3.0,
            )
        return self._driver

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def _session(self):
        return self.driver.session(fetch_size=50)

    def _run(self, session, query: str, **params):
        return session.run(Query(query, timeout=_KG_QUERY_TIMEOUT), **params)

    def _collect_records(self, result, limit: int = _KG_MAX_RECORDS) -> list[dict]:
        rows: list[dict] = []
        for record in result:
            rows.append(dict(record))
            if len(rows) >= limit:
                break
        return rows

    # ========== 缓存辅助 ==========

    def _cache_get(self, key: str) -> Any | None:
        """获取缓存值，过期或不存在返回 None"""
        entry = self._cache.get(key)
        if entry is None:
            return None
        expire_at, value = entry
        if time.time() > expire_at:
            del self._cache[key]
            return None
        return value

    def _cache_set(self, key: str, value: Any) -> None:
        """设置缓存值，超限时淘汰最旧的 20%"""
        if len(self._cache) >= self._CACHE_MAX_SIZE:
            # 淘汰最旧的 20%
            sorted_keys = sorted(self._cache, key=lambda k: self._cache[k][0])
            for k in sorted_keys[:self._CACHE_MAX_SIZE // 5]:
                del self._cache[k]
        self._cache[key] = (time.time() + self._CACHE_TTL, value)

    def _cache_key(self, prefix: str, *args: str) -> str:
        """构建缓存键"""
        return f"{prefix}::{'|'.join(args)}"

    # ========== 分层模糊匹配 ==========

    def fuzzy_find_node(self, topic: str, category: str = "") -> list[dict]:
        """分层模糊匹配知识点节点，每层有退出条件和防泛化约束

        Tier 0: 精确匹配          → 命中即返回，不降级
        Tier 1: 同义词精确匹配     → SYNONYM_MAP 映射后精确查
        Tier 2: 子串包含匹配       → CONTAINS + Jaccard ≥ 0.4 + 最小长度约束
        Tier 3: 全文索引匹配       → Neo4j full-text index（仅 Tier 0-2 全空时触发）

        Args:
            topic: 查询知识点名称
            category: 限定分类（空字符串表示不限）

        Returns:
            匹配到的节点列表 [{"name", "category", "description", "_score", "_tier"}]
        """
        # Tier 0: 精确匹配
        exact = self._find_exact(topic, category)
        if exact:
            for n in exact:
                n["_tier"] = 0
                n["_score"] = 1.0
            return exact

        # Tier 1: 同义词精确匹配
        for synonym in expand_synonyms_for_kg(topic):
            syn_match = self._find_exact(synonym, category)
            if syn_match:
                for n in syn_match:
                    n["_tier"] = 1
                    n["_score"] = 0.9
                return syn_match

        # Tier 2: 子串包含匹配（带防泛化约束）
        candidates: list[dict] = []
        # 最小长度约束：中文 ≥ 2字，英文 ≥ 3字符
        cn_chars = len(re.findall(r"[\u4e00-\u9fff]", topic))
        en_chars = len(re.findall(r"[A-Za-z]", topic))
        if cn_chars >= 2 or en_chars >= 3:
            contains_hits = self._find_contains(topic, category, limit=10)
            for hit in contains_hits:
                jaccard = _char_jaccard(topic, hit["name"])
                if jaccard >= 0.4:
                    hit["_score"] = jaccard
                    hit["_tier"] = 2
                    candidates.append(hit)
        if candidates:
            candidates.sort(key=lambda x: -x["_score"])
            return candidates[:5]

        # Tier 3: 全文索引匹配（Tier 0-2 全空时才触发）
        ft_hits = self._find_fulltext(topic, category, limit=3, min_score=0.3)
        for n in ft_hits:
            n["_tier"] = 3
        return ft_hits

    def _find_exact(self, name: str, category: str = "") -> list[dict]:
        """Tier 0/1: 精确匹配"""
        with self._session() as s:
            if category:
                result = self._run(
                    s,
                    "MATCH (k:Knowledge {name: $name}) WHERE k.category = $category "
                    "RETURN k.name AS name, k.category AS category, k.description AS description",
                    name=name, category=category,
                )
            else:
                result = self._run(
                    s,
                    "MATCH (k:Knowledge {name: $name}) "
                    "RETURN k.name AS name, k.category AS category, k.description AS description",
                    name=name,
                )
            return self._collect_records(result, limit=10)

    def _find_contains(self, topic: str, category: str = "", limit: int = 10) -> list[dict]:
        """Tier 2: 子串包含匹配（CONTAINS）"""
        with self._session() as s:
            if category:
                query = (
                    "MATCH (k:Knowledge) WHERE k.name CONTAINS $topic AND k.category = $category "
                    "RETURN k.name AS name, k.category AS category, k.description AS description "
                    "LIMIT $limit"
                )
                result = self._run(s, query, topic=topic, category=category, limit=min(limit, 20))
            else:
                query = (
                    "MATCH (k:Knowledge) WHERE k.name CONTAINS $topic "
                    "RETURN k.name AS name, k.category AS category, k.description AS description "
                    "LIMIT $limit"
                )
                result = self._run(s, query, topic=topic, limit=min(limit, 20))
            return self._collect_records(result, limit=min(limit, 20))

    def _find_fulltext(self, topic: str, category: str = "", limit: int = 3,
                       min_score: float = 0.3) -> list[dict]:
        """Tier 3: 全文索引匹配

        依赖 Neo4j full-text index 'knowledge_name_index'。
        若索引不存在则自动创建（仅首次）。
        """
        with self._session() as s:
            # 确保全文本索引存在
            try:
                self._run(s, "CALL db.indexes() YIELD name WHERE name = 'knowledge_name_index' RETURN name")
            except Exception:
                try:
                    self._run(s, "CREATE FULLTEXT INDEX knowledge_name_index IF NOT EXISTS "
                              "FOR (k:Knowledge) ON EACH [k.name, k.description]")
                except Exception as e:
                    logger.warning("Failed to create fulltext index: %s", e)

            try:
                if category:
                    query = (
                        "CALL db.index.fulltext.queryNodes('knowledge_name_index', $topic) "
                        "YIELD node, score "
                        "WHERE node.category = $category AND score >= $min_score "
                        "RETURN node.name AS name, node.category AS category, "
                        "       node.description AS description, score AS _score "
                        "LIMIT $limit"
                    )
                    result = self._run(s, query, topic=topic, category=category,
                                       min_score=min_score, limit=min(limit, 10))
                else:
                    query = (
                        "CALL db.index.fulltext.queryNodes('knowledge_name_index', $topic) "
                        "YIELD node, score "
                        "WHERE score >= $min_score "
                        "RETURN node.name AS name, node.category AS category, "
                        "       node.description AS description, score AS _score "
                        "LIMIT $limit"
                    )
                    result = self._run(s, query, topic=topic, min_score=min_score, limit=min(limit, 10))
                return self._collect_records(result, limit=min(limit, 10))
            except Exception as e:
                logger.warning("Fulltext search failed: %s", e)
                return []

    # ========== 知识点操作 ==========

    def add_knowledge_node(self, name: str, category: str = "data_structure",
                           description: str = "", source_file: str = "") -> None:
        """添加知识点节点

        Args:
            name: 知识点名称
            category: 知识点分类
            description: 简短描述
            source_file: 来源文件名（用于溯源和一致性管理）
        """
        self._cache.clear()
        with self._session() as s:
            s.run(
                "MERGE (k:Knowledge {name: $name}) "
                "SET k.category = $category, k.description = $description, "
                "    k.source_file = $source_file",
                name=name, category=category, description=description,
                source_file=source_file,
            )

    def add_prerequisite(self, from_name: str, to_name: str, category: str = "") -> None:
        """添加前置知识关系: from_name 是 to_name 的前置知识

        使用 MERGE 确保端点节点存在（避免 MATCH 找不到节点时边被静默丢弃）。
        ON CREATE SET 为自动创建的节点补上 category，避免孤立无分类节点。
        """
        self._cache.clear()
        with self._session() as s:
            s.run(
                "MERGE (a:Knowledge {name: $from_name}) "
                "ON CREATE SET a.category = $category "
                "MERGE (b:Knowledge {name: $to_name}) "
                "ON CREATE SET b.category = $category "
                "MERGE (a)-[:PREREQUISITE_OF]->(b)",
                from_name=from_name, to_name=to_name, category=category,
            )

    def add_related(self, name_a: str, name_b: str, category: str = "") -> None:
        """添加相关知识关系

        使用 MERGE 确保端点节点存在（避免 MATCH 找不到节点时边被静默丢弃）。
        ON CREATE SET 为自动创建的节点补上 category，避免孤立无分类节点。
        """
        self._cache.clear()
        with self._session() as s:
            s.run(
                "MERGE (a:Knowledge {name: $name_a}) "
                "ON CREATE SET a.category = $category "
                "MERGE (b:Knowledge {name: $name_b}) "
                "ON CREATE SET b.category = $category "
                "MERGE (a)-[:RELATED_TO]->(b)",
                name_a=name_a, name_b=name_b, category=category,
            )

    # ========== 学习路径查询（集成模糊匹配） ==========

    def resolve_topic(self, topic: str, category: str = "") -> str | None:
        """将用户输入的 topic 解析为 KG 中实际存在的节点名

        优先精确匹配，失败后走模糊匹配，返回最佳匹配节点名。
        若无匹配则返回 None。结果会缓存 5 分钟。
        """
        cache_key = self._cache_key("resolve", topic, category)
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        matches = self.fuzzy_find_node(topic, category=category)
        result = matches[0]["name"] if matches else None
        # 缓存结果（包括 None，避免重复查空）
        self._cache_set(cache_key, result)
        return result

    def get_learning_path(self, target: str, max_depth: int = 5) -> list[dict]:
        """查询到达目标知识点需要的学习路径（反向追溯前置知识）

        自动将 target 通过模糊匹配解析为 KG 中实际节点名。
        结果会缓存 5 分钟。
        """
        max_depth = _safe_depth(max_depth, default=5)
        resolved = self.resolve_topic(target)
        if not resolved:
            return []
        cache_key = self._cache_key("path", resolved, str(max_depth))
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        with self._session() as s:
            query = (
                f"MATCH path = (start:Knowledge)-[:PREREQUISITE_OF*1..{max_depth}]->"
                "(target:Knowledge {name: $target}) "
                "RETURN [node IN nodes(path) | node.name] AS names, "
                "       [node IN nodes(path) | node.description] AS descriptions "
                "ORDER BY length(path) "
                "LIMIT 3"
            )
            result = self._run(s, query, target=resolved)
            paths = []
            for record in self._collect_records(result, limit=3):
                names = record["names"]
                descriptions = record["descriptions"]
                paths.append([
                    {"name": n, "description": d} for n, d in zip(names, descriptions)
                ])
            self._cache_set(cache_key, paths)
            return paths

    def get_next_topics(self, current: str, depth: int = 1) -> list[dict]:
        """查询学完当前知识点后可以学的后续知识（支持 n-hop）

        自动将 current 通过模糊匹配解析为 KG 中实际节点名。
        结果会缓存 5 分钟。

        Args:
            current: 当前知识点名称
            depth: 跳数（1=直接后续，2=后续的后续，依此类推）
        """
        depth = _safe_depth(depth, default=1)
        resolved = self.resolve_topic(current)
        if not resolved:
            return []
        cache_key = self._cache_key("next", resolved, str(depth))
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        if depth <= 1:
            with self._session() as s:
                result = self._run(
                    s,
                    "MATCH (current:Knowledge {name: $current})-[:PREREQUISITE_OF]->(next:Knowledge) "
                    "RETURN next.name AS name, next.description AS description, next.category AS category",
                    current=resolved,
                )
                result_list = self._collect_records(result, limit=20)
        else:
            with self._session() as s:
                result = self._run(
                    s,
                    f"MATCH (current:Knowledge {{name: $current}})-[:PREREQUISITE_OF*1..{depth}]->(next:Knowledge) "
                    "RETURN DISTINCT next.name AS name, next.description AS description, next.category AS category "
                    "LIMIT 20",
                    current=resolved,
                )
                result_list = self._collect_records(result, limit=20)
        self._cache_set(cache_key, result_list)
        return result_list

    def get_prerequisites(self, topic: str, depth: int = 1) -> list[dict]:
        """查询某知识点的前置知识（支持 n-hop）

        自动将 topic 通过模糊匹配解析为 KG 中实际节点名。
        结果会缓存 5 分钟。

        Args:
            topic: 知识点名称
            depth: 跳数（1=直接前置，2=前置的前置，依此类推）
        """
        depth = _safe_depth(depth, default=1)
        resolved = self.resolve_topic(topic)
        if not resolved:
            return []
        cache_key = self._cache_key("prereq", resolved, str(depth))
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        if depth <= 1:
            with self._session() as s:
                result = self._run(
                    s,
                    "MATCH (pre:Knowledge)-[:PREREQUISITE_OF]->(topic:Knowledge {name: $topic}) "
                    "RETURN pre.name AS name, pre.description AS description",
                    topic=resolved,
                )
                result_list = self._collect_records(result, limit=20)
        else:
            with self._session() as s:
                result = self._run(
                    s,
                    f"MATCH (pre:Knowledge)-[:PREREQUISITE_OF*1..{depth}]->(topic:Knowledge {{name: $topic}}) "
                    "RETURN DISTINCT pre.name AS name, pre.description AS description "
                    "LIMIT 20",
                    topic=resolved,
                )
                result_list = self._collect_records(result, limit=20)
        self._cache_set(cache_key, result_list)
        return result_list

    def get_subgraph(self, topic: str, depth: int = 2) -> dict:
        """获取以 topic 为中心的子图（n-hop 双向展开）

        返回 topic 的前置链（深度 depth）和后续链（深度 depth），
        以及这些节点之间的 PREREQUISITE_OF 边。

        Args:
            topic: 中心知识点名称
            depth: 展开跳数（默认 2-hop）

        Returns:
            {"nodes": [...], "edges": [...], "center": str}
        """
        depth = _safe_depth(depth, default=2)
        resolved = self.resolve_topic(topic)
        if not resolved:
            return {"nodes": [], "edges": [], "center": topic}
        cache_key = self._cache_key("subgraph", resolved, str(depth))
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached
        with self._session() as s:
            # 获取 n-hop 范围内所有节点
            result = self._run(
                s,
                f"MATCH path = (pre:Knowledge)-[:PREREQUISITE_OF*1..{depth}]->(center:Knowledge {{name: $center}})"
                f"-[:PREREQUISITE_OF*1..{depth}]->(post:Knowledge) "
                "WITH DISTINCT pre, center, post "
                "RETURN pre.name AS name, pre.description AS description, pre.category AS category "
                "UNION "
                f"MATCH path = (center:Knowledge {{name: $center}})-[:PREREQUISITE_OF*1..{depth}]->(post:Knowledge) "
                "RETURN post.name AS name, post.description AS description, post.category AS category "
                "UNION "
                f"MATCH path = (pre:Knowledge)-[:PREREQUISITE_OF*1..{depth}]->(center:Knowledge {{name: $center}}) "
                "RETURN pre.name AS name, pre.description AS description, pre.category AS category "
                "LIMIT 30",
                center=resolved,
            )
            nodes = self._collect_records(result, limit=30)
            # 获取范围内的边
            result = self._run(
                s,
                f"MATCH (a:Knowledge)-[r:PREREQUISITE_OF]->(b:Knowledge) "
                f"WHERE EXISTS {{ MATCH (a)-[:PREREQUISITE_OF*0..{depth}]-(:Knowledge {{name: $center}}) }} "
                f"  AND EXISTS {{ MATCH (b)-[:PREREQUISITE_OF*0..{depth}]-(:Knowledge {{name: $center}}) }} "
                "RETURN a.name AS source, b.name AS target, type(r) AS relation "
                "LIMIT 40",
                center=resolved,
            )
            edges = self._collect_records(result, limit=40)
        subgraph = {"nodes": nodes, "edges": edges, "center": resolved}
        self._cache_set(cache_key, subgraph)
        return subgraph

    # ========== 层级聚合可视化 ==========

    def get_hierarchical_graph_data(self, category: str | None = None, levels: int = 3) -> dict:
        """获取层级聚合的知识图谱可视化数据

        三层结构：学科(root) → 章(level1) → 知识点(level2)
        levels=2 时仅展示 root + level1，不展示 level2
        聚合策略：
          - root: 每个 category 一个节点（仅4大核心学科）
          - level1: 按 chapter 分组，每学科最多展示 8 个章
          - level2: 具体知识点（最多展示每个 chapter 下 4 个）
        边：
          - root → level1: 包含关系
          - level1 → level2: 包含关系
          - level1 → level1: 跨章前置关系（从 Neo4j PREREQUISITE_OF 聚合）
        """
        from app.db.models import KnowledgePointRegistry
        from app.db.session import SessionLocal

        # 仅展示4大核心学科
        _CORE_CATEGORIES = {"data_structure", "computer_organization", "operating_system", "computer_network"}

        # 章节名称规范化映射：将数据中的杂乱名称映射为标准教材章节名
        _CHAPTER_NORMALIZE: dict[str, dict[str, str]] = {
            "data_structure": {
                "线性表": "线性表",
                "顺序表": "线性表",
                "链表": "线性表",
                "栈": "栈和队列",
                "队列": "栈和队列",
                "串": "串",
                "KMP": "串",
                "模式匹配": "串",
                "树": "树与二叉树",
                "二叉树": "树与二叉树",
                "遍历": "树与二叉树",
                "线索": "树与二叉树",
                "森林": "树与二叉树",
                "哈夫曼": "树与二叉树",
                "红黑树": "树与二叉树",
                "并查集": "树与二叉树",
                "多路查找": "树与二叉树",
                "图": "图",
                "最短路径": "图",
                "最小生成树": "图",
                "关键路径": "图",
                "拓扑": "图",
                "查找": "查找",
                "散列": "查找",
                "排序": "排序",
                "插入排序": "排序",
                "冒泡": "排序",
                "选择排序": "排序",
                "归并": "排序",
                "堆排序": "排序",
                "基数排序": "排序",
                "希尔": "排序",
                "快速排序": "排序",
                "数组": "数组与广义表",
                "广义表": "数组与广义表",
                "定义": "基本概念",
                "数据结构三要素": "基本概念",
                "算法": "基本概念",
                "数据运算": "基本概念",
                "递归": "基本概念",
                "删除": "线性表",
                "存储结构": "线性表",
                "插入": "排序",
            },
            "computer_network": {
                "物理层": "物理层",
                "传输媒体": "物理层",
                "编码": "物理层",
                "调制": "物理层",
                "信道": "物理层",
                "复用": "物理层",
                "数据链路层": "数据链路层",
                "链路": "数据链路层",
                "差错": "数据链路层",
                "流量控制": "数据链路层",
                "可靠传输": "数据链路层",
                "CSMA": "数据链路层",
                "PPP": "数据链路层",
                "以太网": "数据链路层",
                "MAC": "数据链路层",
                "VLAN": "数据链路层",
                "媒体接入": "数据链路层",
                "介质访问": "数据链路层",
                "网络层": "网络层",
                "IP": "网络层",
                "IPv4": "网络层",
                "路由": "网络层",
                "ICMP": "网络层",
                "VPN": "网络层",
                "NAT": "网络层",
                "ARP": "网络层",
                "传输层": "传输层",
                "TCP": "传输层",
                "UDP": "传输层",
                "传输控制": "传输层",
                "应用层": "应用层",
                "HTTP": "应用层",
                "DNS": "应用层",
                "FTP": "应用层",
                "电子邮件": "应用层",
                "万维网": "应用层",
                "WWW": "应用层",
                "域名": "应用层",
                "DHCP": "应用层",
                "动态主机": "应用层",
                "网际控制": "网络层",
                "网际协议": "网络层",
                "传输方式": "物理层",
                "网络应用模型": "应用层",
                "文件传送": "应用层",
                "专用术语": "网络体系结构",
                "补充": "网络体系结构",
                "章节总结": "网络体系结构",
                "透明传输": "数据链路层",
                "基本概念": "网络体系结构",
                "接口特性": "物理层",
                "IEEE": "数据链路层",
                "分层的必要性": "网络体系结构",
                "分层模型": "网络体系结构",
                "体系结构": "网络体系结构",
                "性能指标": "网络体系结构",
            },
            "operating_system": {
                "进程": "进程管理",
                "处理机": "进程管理",
                "调度": "进程管理",
                "同步": "进程管理",
                "互斥": "进程管理",
                "死锁": "进程管理",
                "信号量": "进程管理",
                "管程": "进程管理",
                "线程": "进程管理",
                "进程控制": "进程管理",
                "上下文": "进程管理",
                "通信": "进程管理",
                "消费者": "进程管理",
                "哲学家": "进程管理",
                "读者": "进程管理",
                "写者": "进程管理",
                "银行家": "进程管理",
                "内存": "内存管理",
                "虚拟存储": "内存管理",
                "页面": "内存管理",
                "页面置换": "内存管理",
                "分配策略": "内存管理",
                "驻留集": "内存管理",
                "内存映射": "内存管理",
                "常规存储": "内存管理",
                "地址转换": "内存管理",
                "文件": "文件管理",
                "磁盘": "文件管理",
                "目录": "文件管理",
                "文件共享": "文件管理",
                "文件保护": "文件管理",
                "存储空间": "文件管理",
                "逻辑结构": "文件管理",
                "物理结构": "文件管理",
                "I/O": "输入输出管理",
                "输入输出": "输入输出管理",
                "IO": "输入输出管理",
                "接口": "输入输出管理",
                "设备": "输入输出管理",
                "控制方式": "输入输出管理",
                "控制层": "输入输出管理",
                "SPOOLing": "输入输出管理",
                "减少延迟": "文件管理",
                "延迟时间": "文件管理",
                "处理方式": "操作系统概述",
                "平均存取": "文件管理",
                "组成": "操作系统概述",
                "运行机制": "操作系统概述",
                "特征": "操作系统概述",
                "层次": "操作系统概述",
                "分配": "内存管理",
                "回收": "内存管理",
                "临界": "进程管理",
                "定义": "操作系统概述",
                "概念": "操作系统概述",
                "批处理": "操作系统概述",
                "提供的功": "操作系统概述",
                "分时": "操作系统概述",
                "实时": "操作系统概述",
                "并发": "进程管理",
                "共享": "操作系统概述",
                "虚拟": "内存管理",
                "中断": "操作系统概述",
                "异常": "操作系统概述",
                "体系结构": "操作系统概述",
                "大内核": "操作系统概述",
                "微内核": "操作系统概述",
                "库函数": "操作系统概述",
                "系统调用": "操作系统概述",
                "分层结构": "操作系统概述",
                "模块化": "操作系统概述",
                "外核": "操作系统概述",
            },
            "computer_organization": {
                "概述": "计算机系统概述",
                "发展": "计算机系统概述",
                "性能": "计算机系统概述",
                "分类": "计算机系统概述",
                "层次结构": "计算机系统概述",
                "数据表示": "数据的表示和运算",
                "运算": "数据的表示和运算",
                "定点": "数据的表示和运算",
                "浮点": "数据的表示和运算",
                "补码": "数据的表示和运算",
                "十进制": "数据的表示和运算",
                "检错": "数据的表示和运算",
                "存储器": "存储系统",
                "存储": "存储系统",
                "Cache": "存储系统",
                "高速缓冲": "存储系统",
                "RAM": "存储系统",
                "ROM": "存储系统",
                "虚拟存储": "存储系统",
                "页式": "存储系统",
                "磁盘": "存储系统",
                "指令": "指令系统",
                "寻址": "指令系统",
                "CISC": "指令系统",
                "RISC": "指令系统",
                "汇编": "指令系统",
                "指令格式": "指令系统",
                "CPU": "中央处理器",
                "处理器": "中央处理器",
                "数据通路": "中央处理器",
                "控制器": "中央处理器",
                "流水线": "中央处理器",
                "多处理器": "中央处理器",
                "功能": "中央处理器",
                "结构": "中央处理器",
                "总线": "总线",
                "仲裁": "总线",
                "总线标准": "总线",
                "输入输出": "输入输出系统",
                "I/O": "输入输出系统",
                "外部设备": "输入输出系统",
                "接口": "输入输出系统",
                "定时": "输入输出系统",
                "操作": "输入输出系统",
                "补充": "计算机系统概述",
                "术语": "计算机系统概述",
                "二进制": "数据的表示和运算",
                "对照": "数据的表示和运算",
                "模4": "数据的表示和运算",
                "真值": "数据的表示和运算",
                "机器数": "数据的表示和运算",
                "BCD": "数据的表示和运算",
                "ASCII": "数据的表示和运算",
                "汉字": "数据的表示和运算",
                "UTF": "数据的表示和运算",
            },
        }

        def _normalize_chapter(cat: str, raw_ch: str) -> str:
            """将杂乱的章节名映射为标准教材章节名"""
            # 先清理 markdown 标记和特殊符号
            clean = raw_ch.replace("**", "").replace("❗", "").replace("【考点】", "").replace("【大题❗考点】", "").replace("【题】", "")
            clean = clean.strip()

            # 查找映射
            mapping = _CHAPTER_NORMALIZE.get(cat, {})
            for keyword, standard_name in mapping.items():
                if keyword in clean:
                    return standard_name

            # 兜底：未匹配到的杂项归入"其他"
            return "其他"

        # 1. 从 Registry 获取知识点层级
        with SessionLocal() as db:
            query = db.query(KnowledgePointRegistry)
            if category:
                query = query.filter(KnowledgePointRegistry.category == category)
            all_kps = query.all()

        if not all_kps:
            return {"nodes": [], "edges": [], "stats": {"root_count": 0, "chapter_count": 0, "kp_count": 0}}

        # 2. 按学科→章→知识点 聚合（使用规范化后的章节名）
        subject_map: dict[str, dict[str, list]] = {}  # category → {chapter → [kp_names]}
        for kp in all_kps:
            cat = kp.category or "unknown"
            if cat not in _CORE_CATEGORIES:
                continue
            raw_ch = kp.chapter or kp.name
            ch = _normalize_chapter(cat, raw_ch)
            subject_map.setdefault(cat, {}).setdefault(ch, []).append(kp.name)

        # 3. 构建 Neo4j 跨章关系映射
        prereq_records = []
        cross_cat_records = []
        try:
            with self._session() as s:
                # 同科跨章 PREREQUISITE_OF
                cypher = (
                    "MATCH (k1:Knowledge)-[r:PREREQUISITE_OF]->(k2:Knowledge) "
                    "WHERE k1.category = k2.category "
                    "RETURN k1.name AS source, k2.name AS target, k1.category AS category"
                )
                params = {}
                if category:
                    cypher = (
                        "MATCH (k1:Knowledge)-[r:PREREQUISITE_OF]->(k2:Knowledge) "
                        "WHERE k1.category = $category AND k2.category = $category "
                        "RETURN k1.name AS source, k2.name AS target, k1.category AS category"
                    )
                    params = {"category": category}
                prereq_records = self._collect_records(self._run(s, cypher, **params), limit=2000)

                # 跨学科 RELATED_TO（用于 root 之间连线）
                if not category:
                    cypher2 = (
                        "MATCH (k1:Knowledge)-[r:RELATED_TO]->(k2:Knowledge) "
                        "WHERE k1.category <> k2.category "
                        "RETURN k1.category AS src_cat, k2.category AS tgt_cat, count(r) AS cnt "
                        "ORDER BY cnt DESC LIMIT 20"
                    )
                    cross_cat_records = self._collect_records(self._run(s, cypher2), limit=20)
        except Exception as e:
            logger.debug("Failed to fetch cross-chapter edges: %s", e)

        # 4. 构建可视化节点和边
        nodes = []
        edges = []

        cat_labels = {
            "data_structure": "数据结构",
            "computer_organization": "计算机组成原理",
            "operating_system": "操作系统",
            "computer_network": "计算机网络",
        }

        total_chapters = 0
        total_kps = sum(len(v) for chapters in subject_map.values() for v in chapters.values())

        for cat, chapters in subject_map.items():
            cat_label = cat_labels.get(cat, cat)
            root_id = f"root:{cat}"
            total_in_cat = sum(len(v) for v in chapters.values())
            nodes.append({
                "id": root_id,
                "name": cat_label,
                "category": cat,
                "kind": "root",
                "description": f"{cat_label}：共 {total_in_cat} 个知识点",
            })

            # 按 chapter 中知识点数量排序（归一化后章节数已合理，无需截断）
            sorted_chapters = sorted(chapters.items(), key=lambda x: len(x[1]), reverse=True)

            for ch_name, kp_names in sorted_chapters:
                total_chapters += 1
                ch_id = f"level1:{cat}:{ch_name}"

                nodes.append({
                    "id": ch_id,
                    "name": ch_name,
                    "category": cat,
                    "kind": "level1",
                    "description": f"共 {len(kp_names)} 个知识点",
                    "child_count": len(kp_names),
                })
                edges.append({"source": root_id, "target": ch_id, "relation": "CONTAINS"})

                if levels >= 3:
                    for kp_name in kp_names:
                        kp_id = f"level2:{cat}:{ch_name}:{kp_name}"
                        nodes.append({
                            "id": kp_id,
                            "name": kp_name,
                            "category": cat,
                            "kind": "level2",
                            "description": "",
                        })
                        edges.append({"source": ch_id, "target": kp_id, "relation": "CONTAINS"})


        # 5. 从 PREREQUISITE_OF 聚合跨章关系
        kp_chapter_map: dict[str, str] = {}
        for cat, chapters in subject_map.items():
            for ch_name, kp_names in chapters.items():
                for kp_name in kp_names:
                    kp_chapter_map[f"{cat}:{kp_name}"] = f"level1:{cat}:{ch_name}"

        seen_cross = set()
        for rec in prereq_records:
            src_key = f"{rec.get('category', '')}:{rec.get('source', '')}"
            tgt_key = f"{rec.get('category', '')}:{rec.get('target', '')}"
            src_ch = kp_chapter_map.get(src_key)
            tgt_ch = kp_chapter_map.get(tgt_key)
            if src_ch and tgt_ch and src_ch != tgt_ch:
                edge_key = f"{src_ch}->{tgt_ch}"
                if edge_key not in seen_cross:
                    seen_cross.add(edge_key)
                    edges.append({"source": src_ch, "target": tgt_ch, "relation": "PREREQUISITE_OF"})

        # 6. 跨学科 RELATED_TO（root 之间连线）
        seen_cross_cat = set()
        for rec in cross_cat_records:
            src_cat = rec.get("src_cat", "")
            tgt_cat = rec.get("tgt_cat", "")
            if src_cat in _CORE_CATEGORIES and tgt_cat in _CORE_CATEGORIES:
                edge_key = f"root:{src_cat}->root:{tgt_cat}"
                rev_key = f"root:{tgt_cat}->root:{src_cat}"
                if edge_key not in seen_cross_cat and rev_key not in seen_cross_cat:
                    seen_cross_cat.add(edge_key)
                    edges.append({
                        "source": f"root:{src_cat}",
                        "target": f"root:{tgt_cat}",
                        "relation": "RELATED_TO",
                        "weight": rec.get("cnt", 1),
                    })

        return {
            "nodes": nodes,
            "edges": edges,
            "stats": {
                "root_count": len(subject_map),
                "chapter_count": total_chapters,
                "kp_count": total_kps,
            },
        }

    # ========== 删除同步 ==========

    def delete_by_source(self, source_file: str) -> int:
        """删除指定来源文件的所有节点和关系

        Args:
            source_file: 来源文件名

        Returns:
            删除的节点数
        """
        self._cache.clear()
        with self._session() as s:
            result = s.run(
                "MATCH (n:Knowledge {source_file: $source_file}) "
                "DETACH DELETE n RETURN count(n) AS deleted",
                source_file=source_file,
            )
            record = result.single()
            return record["deleted"] if record else 0

    def delete_by_category(self, category: str) -> int:
        """删除指定分类的所有节点和关系

        Args:
            category: 知识点分类

        Returns:
            删除的节点数
        """
        self._cache.clear()
        with self._session() as s:
            result = s.run(
                "MATCH (n:Knowledge {category: $category}) "
                "DETACH DELETE n RETURN count(n) AS deleted",
                category=category,
            )
            record = result.single()
            return record["deleted"] if record else 0

    def delete_node(self, name: str, category: str = "") -> bool:
        """删除指定名称的知识节点及其关系

        Args:
            name: 节点名称
            category: 限定分类（空字符串表示不限）

        Returns:
            是否成功删除
        """
        self._cache.clear()
        with self._session() as s:
            if category:
                result = s.run(
                    "MATCH (n:Knowledge {name: $name, category: $category}) "
                    "DETACH DELETE n RETURN count(n) AS deleted",
                    name=name, category=category,
                )
            else:
                result = s.run(
                    "MATCH (n:Knowledge {name: $name}) "
                    "DETACH DELETE n RETURN count(n) AS deleted",
                    name=name,
                )
            record = result.single()
            deleted = record["deleted"] if record else 0
            return deleted > 0

    # ========== 孤儿检测与一致性健康检查 ==========

    def find_orphan_nodes(self, indexed_files: set[str],
                          category: str = "") -> list[dict]:
        """查找 KG 中 source_file 不在向量库索引文件列表中的孤儿节点

        Args:
            indexed_files: 向量库中已索引的文件名集合
            category: 限定分类（空字符串表示不限）

        Returns:
            孤儿节点列表 [{"name", "source_file", "category"}]
        """
        with self._session() as s:
            if category:
                query = (
                    "MATCH (k:Knowledge) WHERE k.category = $category AND k.source_file <> '' "
                    "RETURN k.name AS name, k.source_file AS source_file, k.category AS category "
                    "LIMIT $limit"
                )
                result = self._run(s, query, category=category, limit=_KG_MAX_RECORDS)
            else:
                query = (
                    "MATCH (k:Knowledge) WHERE k.source_file <> '' "
                    "RETURN k.name AS name, k.source_file AS source_file, k.category AS category "
                    "LIMIT $limit"
                )
                result = self._run(s, query, limit=_KG_MAX_RECORDS)
            orphans = []
            for record in self._collect_records(result, limit=_KG_MAX_RECORDS):
                if record["source_file"] not in indexed_files:
                    orphans.append(record)
            return orphans

    def health_check(self, indexed_files: set[str],
                     category: str = "") -> dict[str, Any]:
        """一致性健康检查

        Args:
            indexed_files: 向量库中已索引的文件名集合
            category: 限定分类

        Returns:
            {"total_nodes", "orphan_nodes", "consistency_ratio", "orphans"}
        """
        with self._session() as s:
            if category:
                count_result = self._run(
                    s,
                    "MATCH (k:Knowledge) WHERE k.category = $category RETURN count(k) AS total",
                    category=category,
                )
            else:
                count_result = self._run(s, "MATCH (k:Knowledge) RETURN count(k) AS total")
            record = count_result.single()
            total_nodes = record["total"] if record else 0

        orphans = self.find_orphan_nodes(indexed_files, category=category)
        consistency_ratio = 1 - (len(orphans) / max(total_nodes, 1))

        return {
            "total_nodes": total_nodes,
            "orphan_nodes": len(orphans),
            "consistency_ratio": round(consistency_ratio, 4),
            "orphans": orphans[:20],  # 最多返回 20 条详情
        }

    # ========== 批量导入 ==========

    def import_from_data(self, nodes: list[dict], edges: list[dict],
                         source_file: str = "") -> None:
        """批量导入知识点和关系（在同一 session 中完成）

        Args:
            nodes: 节点列表 [{"name", "category", "description"}]
            edges: 边列表 [{"source", "target", "relation"}]
            source_file: 来源文件名（用于溯源）
        """
        self._cache.clear()
        with self._session() as s:
            for node in nodes:
                s.run(
                    "MERGE (k:Knowledge {name: $name}) "
                    "SET k.category = $category, k.description = $description, "
                    "    k.source_file = $source_file",
                    name=node.get("name", ""),
                    category=node.get("category", "data_structure"),
                    description=node.get("description", ""),
                    source_file=source_file,
                )
            for edge in edges:
                rel_type = edge.get("relation", "RELATED_TO")
                if rel_type == "PREREQUISITE_OF":
                    s.run(
                        "MATCH (a:Knowledge {name: $from_name}) "
                        "MATCH (b:Knowledge {name: $to_name}) "
                        "MERGE (a)-[:PREREQUISITE_OF]->(b)",
                        from_name=edge["source"], to_name=edge["target"],
                    )
                else:
                    s.run(
                        "MATCH (a:Knowledge {name: $name_a}) "
                        "MATCH (b:Knowledge {name: $name_b}) "
                        "MERGE (a)-[:RELATED_TO]->(b)",
                        name_a=edge["source"], name_b=edge["target"],
                    )

    def clear_all(self) -> None:
        """清空知识图谱"""
        self._cache.clear()
        with self._session() as s:
            s.run("MATCH (n) DETACH DELETE n")


_kg_manager: KnowledgeGraphManager | None = None


def get_kg_manager() -> KnowledgeGraphManager:
    """懒加载知识图谱管理器（单例）"""
    global _kg_manager
    if _kg_manager is None:
        _kg_manager = KnowledgeGraphManager()
    return _kg_manager

