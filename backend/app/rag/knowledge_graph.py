from __future__ import annotations

from neo4j import GraphDatabase

from app.config import settings


class KnowledgeGraphManager:
    """Neo4j 知识图谱管理器"""

    def __init__(self) -> None:
        self._driver = None

    @property
    def driver(self):
        """懒加载 Neo4j 连接"""
        if self._driver is None:
            self._driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            )
        return self._driver

    def close(self) -> None:
        if self._driver is not None:
            self._driver.close()
            self._driver = None

    def _session(self):
        return self.driver.session()

    # ========== 知识点操作 ==========

    def add_knowledge_node(self, name: str, category: str = "general", description: str = "") -> None:
        """添加知识点节点"""
        with self._session() as s:
            s.run(
                "MERGE (k:Knowledge {name: $name}) "
                "SET k.category = $category, k.description = $description",
                name=name, category=category, description=description,
            )

    def add_prerequisite(self, from_name: str, to_name: str) -> None:
        """添加前置知识关系: from_name 是 to_name 的前置知识"""
        with self._session() as s:
            s.run(
                "MATCH (a:Knowledge {name: $from_name}) "
                "MATCH (b:Knowledge {name: $to_name}) "
                "MERGE (a)-[:PREREQUISITE_OF]->(b)",
                from_name=from_name, to_name=to_name,
            )

    def add_related(self, name_a: str, name_b: str) -> None:
        """添加相关知识关系"""
        with self._session() as s:
            s.run(
                "MATCH (a:Knowledge {name: $name_a}) "
                "MATCH (b:Knowledge {name: $name_b}) "
                "MERGE (a)-[:RELATED_TO]->(b)",
                name_a=name_a, name_b=name_b,
            )

    # ========== 学习路径查询 ==========

    def get_learning_path(self, target: str, max_depth: int = 5) -> list[dict]:
        """查询到达目标知识点需要的学习路径（反向追溯前置知识）"""
        with self._session() as s:
            result = s.run(
                f"MATCH path = (start:Knowledge)-[:PREREQUISITE_OF*1..{max_depth}]->"
                f"(target:Knowledge {{name: $target}}) "
                "RETURN [node IN nodes(path) | node.name] AS names, "
                "       [node IN nodes(path) | node.description] AS descriptions "
                "ORDER BY length(path) "
                "LIMIT 3",
                target=target,
            )
            paths = []
            for record in result:
                names = record["names"]
                descriptions = record["descriptions"]
                paths.append([
                    {"name": n, "description": d} for n, d in zip(names, descriptions)
                ])
            return paths

    def get_next_topics(self, current: str) -> list[dict]:
        """查询学完当前知识点后可以学的后续知识"""
        with self._session() as s:
            result = s.run(
                "MATCH (current:Knowledge {name: $current})-[:PREREQUISITE_OF]->(next:Knowledge) "
                "RETURN next.name AS name, next.description AS description, next.category AS category",
                current=current,
            )
            return [dict(record) for record in result]

    def get_prerequisites(self, topic: str) -> list[dict]:
        """查询某知识点的前置知识"""
        with self._session() as s:
            result = s.run(
                "MATCH (pre:Knowledge)-[:PREREQUISITE_OF]->(topic:Knowledge {name: $topic}) "
                "RETURN pre.name AS name, pre.description AS description",
                topic=topic,
            )
            return [dict(record) for record in result]

    # ========== 可视化数据 ==========

    def get_graph_data(self, category: str | None = None, limit: int = 50) -> dict:
        """获取知识图谱可视化数据（节点+边）"""
        with self._session() as s:
            node_query = (
                "MATCH (k:Knowledge) WHERE k.category = $category "
                "RETURN k.name AS id, k.category AS category, k.description AS description "
                f"LIMIT {limit}"
                if category
                else "MATCH (k:Knowledge) "
                "RETURN k.name AS id, k.category AS category, k.description AS description "
                f"LIMIT {limit}"
            )
            nodes = [dict(r) for r in s.run(node_query, category=category)]

            edge_query = (
                "MATCH (k1:Knowledge)-[r]->(k2:Knowledge) WHERE k1.category = $category "
                "RETURN k1.name AS source, k2.name AS target, type(r) AS relation "
                f"LIMIT {limit * 2}"
                if category
                else "MATCH (k1:Knowledge)-[r]->(k2:Knowledge) "
                "RETURN k1.name AS source, k2.name AS target, type(r) AS relation "
                f"LIMIT {limit * 2}"
            )
            edges = [dict(r) for r in s.run(edge_query, category=category)]

        return {"nodes": nodes, "edges": edges}

    # ========== 批量导入 ==========

    def import_from_data(self, nodes: list[dict], edges: list[dict]) -> None:
        """批量导入知识点和关系（在同一 session 中完成）"""
        with self._session() as s:
            for node in nodes:
                s.run(
                    "MERGE (k:Knowledge {name: $name}) "
                    "SET k.category = $category, k.description = $description",
                    name=node.get("name", ""),
                    category=node.get("category", "general"),
                    description=node.get("description", ""),
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
        with self._session() as s:
            s.run("MATCH (n) DETACH DELETE n")


kg_manager = KnowledgeGraphManager()
