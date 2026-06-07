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

    # ========== 可视化数据 ==========

    def get_graph_data(self, category: str | None = None, limit: int = 50) -> dict:
        """获取知识图谱可视化数据（节点+边）"""
        limit = max(1, min(int(limit), 100))
        with self._session() as s:
            if category:
                node_query = (
                    "MATCH (k:Knowledge) WHERE k.category = $category "
                    "RETURN k.name AS id, k.category AS category, k.description AS description "
                    "LIMIT $limit"
                )
                edge_query = (
                    "MATCH (k1:Knowledge)-[r]->(k2:Knowledge) WHERE k1.category = $category "
                    "RETURN k1.name AS source, k2.name AS target, type(r) AS relation "
                    "LIMIT $edge_limit"
                )
                nodes = self._collect_records(self._run(s, node_query, category=category, limit=limit), limit=limit)
                edges = self._collect_records(self._run(s, edge_query, category=category, edge_limit=limit * 2), limit=limit * 2)
            else:
                node_query = (
                    "MATCH (k:Knowledge) "
                    "RETURN k.name AS id, k.category AS category, k.description AS description "
                    "LIMIT $limit"
                )
                edge_query = (
                    "MATCH (k1:Knowledge)-[r]->(k2:Knowledge) "
                    "RETURN k1.name AS source, k2.name AS target, type(r) AS relation "
                    "LIMIT $edge_limit"
                )
                nodes = self._collect_records(self._run(s, node_query, limit=limit), limit=limit)
                edges = self._collect_records(self._run(s, edge_query, edge_limit=limit * 2), limit=limit * 2)

        return {"nodes": nodes, "edges": edges}

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

