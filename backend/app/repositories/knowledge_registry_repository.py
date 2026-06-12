from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.db.models import KnowledgePointRegistry
from app.db.session import SessionLocal


class KnowledgeRegistryRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_id(self, knowledge_point_id: int) -> KnowledgePointRegistry | None:
        return self.db.get(KnowledgePointRegistry, knowledge_point_id)

    def find_by_name(self, name: str) -> KnowledgePointRegistry | None:
        return (
            self.db.query(KnowledgePointRegistry)
            .filter(KnowledgePointRegistry.name == name)
            .first()
        )

    def find_first_by_category(self, category: str) -> KnowledgePointRegistry | None:
        return (
            self.db.query(KnowledgePointRegistry)
            .filter(KnowledgePointRegistry.category == category)
            .first()
        )

    def lookup_difficulty(self, knowledge_point_name: str) -> float | None:
        registry = self.find_by_name(knowledge_point_name)
        if registry and registry.difficulty_source == "manual":
            return registry.difficulty
        if registry and _has_difficulty_keyword(registry.heading_path or ""):
            return registry.difficulty
        return None

    def resolve_knowledge_point_id(
        self,
        *,
        evidences: Iterable[object],
        topic: str,
    ) -> int | None:
        evidence_list = list(evidences)

        for evidence in evidence_list:
            for name in getattr(evidence, "knowledge_points", []) or []:
                if not name:
                    continue
                registry = self.find_by_name(name)
                if registry:
                    return registry.id

            section_path = getattr(evidence, "section_path", "") or ""
            if section_path:
                heading = section_path.split(">")[-1].strip()
                if heading:
                    registry = self.find_by_name(heading)
                    if registry:
                        return registry.id

        collections = {
            getattr(evidence, "collection", "")
            for evidence in evidence_list
            if getattr(evidence, "collection", "")
        }
        for collection in collections:
            if collection in {
                "data_structure",
                "computer_organization",
                "operating_system",
                "computer_network",
            }:
                registry = self.find_first_by_category(collection)
                if registry:
                    return registry.id

        if topic:
            registry = self.find_by_name(topic)
            if registry:
                return registry.id

        return None

    @staticmethod
    def lookup_difficulty_with_managed_session(knowledge_point_name: str) -> float | None:
        try:
            with SessionLocal() as db:
                return KnowledgeRegistryRepository(db).lookup_difficulty(knowledge_point_name)
        except Exception:
            return None


def _has_difficulty_keyword(heading_path: str) -> bool:
    keywords = {
        "基础",
        "入门",
        "概述",
        "概念",
        "基本",
        "初识",
        "理解",
        "掌握",
        "原理",
        "特征",
        "性质",
        "定义",
        "综合",
        "应用",
        "分析",
        "设计",
        "实现",
        "计算",
        "创新",
        "优化",
        "拓展",
        "高级",
        "深入",
        "探究",
    }
    return any(keyword in heading_path for keyword in keywords)
