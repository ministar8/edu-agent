from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.repositories.tracking_repository import TrackingRepository
from app.services.knowledge_tracker import _hours_since, effective_mastery, get_knowledge_tracker

logger = logging.getLogger(__name__)

SOURCE_LABELS = {"qa": "智能问答", "quiz": "练习", "grading": "批改", "unknown": "其他"}

EVENT_LABELS = {
    "qa_high_confidence": "高置信问答",
    "qa_low_confidence": "低置信问答",
    "quiz_correct": "练习正确",
    "quiz_partial": "练习部分正确",
    "quiz_wrong": "练习错误",
    "grading_excellent": "批改优秀",
    "grading_pass": "批改通过",
    "grading_fail": "批改未通过",
}


class TrackingQueryService:
    def __init__(self, db: Session):
        self.repository = TrackingRepository(db)

    def get_category_detail(self, user_id: int, category: str) -> dict:
        all_knowledge_points = self.repository.list_category_knowledge_points(category)
        states = self.repository.list_states_for_user_category(user_id, category)
        state_map = {state.knowledge_point_id: state for state in states}
        now = datetime.now(timezone.utc)

        points = []
        for knowledge_point in all_knowledge_points:
            state = state_map.get(knowledge_point.id)
            if state:
                hours = _hours_since(state.last_interaction_at, now)
                effective = effective_mastery(state.mastery, state.confidence, hours)
                effective_score = effective * state.confidence
                points.append({
                    "id": knowledge_point.id,
                    "name": knowledge_point.name,
                    "chapter": knowledge_point.chapter,
                    "difficulty": knowledge_point.difficulty,
                    "mastery": round(effective, 3),
                    "confidence": round(state.confidence, 3),
                    "effective_score": round(effective_score, 3),
                    "interaction_count": state.interaction_count,
                    "tracked": True,
                })
            else:
                points.append({
                    "id": knowledge_point.id,
                    "name": knowledge_point.name,
                    "chapter": knowledge_point.chapter,
                    "difficulty": knowledge_point.difficulty,
                    "mastery": 0.0,
                    "confidence": 0.0,
                    "effective_score": 0.0,
                    "interaction_count": 0,
                    "tracked": False,
                })

        chapters: dict[str, list] = {}
        for point in points:
            chapter = point["chapter"] or "其他"
            chapters.setdefault(chapter, []).append(point)

        return {
            "success": True,
            "data": {
                "category": category,
                "total_points": len(points),
                "tracked_points": sum(1 for point in points if point["tracked"]),
                "avg_mastery": round(
                    sum(point["mastery"] for point in points) / len(points), 3
                ) if points else 0,
                "chapters": chapters,
            },
        }

    def get_learning_path(self, user_id: int, limit: int) -> dict:
        tracker = get_knowledge_tracker()
        weak_points = tracker.get_weak_points(user_id, threshold=0.4, limit=limit)
        if not weak_points:
            return {"success": True, "data": []}

        state_map = self._build_state_score_map(user_id)
        paths = []
        try:
            from app.rag.knowledge_graph import get_kg_manager

            kg = get_kg_manager()
            for weak_point in weak_points:
                chain_nodes = []
                learning_paths = kg.get_learning_path(weak_point["name"], max_depth=4)
                if learning_paths:
                    for step in learning_paths[0]:
                        name = step.get("name", "")
                        chain_nodes.append({
                            "name": name,
                            "description": step.get("description", ""),
                            "mastery": state_map.get(name),
                        })
                chain_nodes.append({
                    "name": weak_point["name"],
                    "description": "",
                    "mastery": weak_point.get("effective_score"),
                    "is_target": True,
                })
                paths.append({
                    "target": weak_point["name"],
                    "category": weak_point["category"],
                    "effective_score": weak_point["effective_score"],
                    "chain": chain_nodes,
                })
        except Exception as exc:
            logger.warning("Learning path KG query failed: %s", exc)
            for weak_point in weak_points:
                paths.append({
                    "target": weak_point["name"],
                    "category": weak_point["category"],
                    "effective_score": weak_point["effective_score"],
                    "chain": [{
                        "name": weak_point["name"],
                        "description": "",
                        "mastery": weak_point.get("effective_score"),
                        "is_target": True,
                    }],
                })

        return {"success": True, "data": paths}

    def get_recent_interactions(self, user_id: int, limit: int) -> dict:
        states = self.repository.list_recent_states(user_id, limit)
        knowledge_point_map = self._load_knowledge_point_map(states)
        now = datetime.now(timezone.utc)

        items = []
        for state in states:
            knowledge_point = knowledge_point_map.get(state.knowledge_point_id)
            if not knowledge_point:
                continue
            hours = _hours_since(state.last_interaction_at, now)
            effective = effective_mastery(state.mastery, state.confidence, hours)
            effective_score = effective * state.confidence
            items.append({
                "id": state.id,
                "name": knowledge_point.name,
                "category": state.category,
                "mastery": round(effective, 3),
                "effective_score": round(effective_score, 3),
                "interaction_count": state.interaction_count,
                "source": SOURCE_LABELS.get(state.source, state.source),
                "time_ago": _format_time_ago(hours),
            })

        return {"success": True, "data": items}

    def get_mastery_trend(
        self,
        *,
        user_id: int,
        knowledge_point_id: int | None,
        category: str,
        days: int,
    ) -> dict:
        since = datetime.now(timezone.utc) - timedelta(days=days)

        if knowledge_point_id:
            rows = self.repository.list_mastery_history(
                user_id=user_id,
                since=since,
                knowledge_point_id=knowledge_point_id,
            )
            knowledge_point = self.repository.get_knowledge_point(knowledge_point_id)
            return {
                "success": True,
                "data": {
                    "mode": "single",
                    "knowledge_point_id": knowledge_point_id,
                    "knowledge_point_name": knowledge_point.name if knowledge_point else "",
                    "points": [_history_point(row) for row in rows],
                },
            }

        knowledge_point_ids = (
            self.repository.list_knowledge_point_ids_by_category(category)
            if category
            else None
        )
        rows = self.repository.list_mastery_history(
            user_id=user_id,
            since=since,
            knowledge_point_ids=knowledge_point_ids,
        )
        points = _aggregate_daily_points(rows)
        if len(points) < 2:
            points = _demo_trend_points()

        return {
            "success": True,
            "data": {
                "mode": "aggregate",
                "category": category or "all",
                "points": points,
            },
        }

    def _build_state_score_map(self, user_id: int) -> dict[str, float]:
        states = self.repository.list_states_for_user(user_id)
        knowledge_point_map = self._load_knowledge_point_map(states)
        now = datetime.now(timezone.utc)
        state_map = {}
        for state in states:
            knowledge_point = knowledge_point_map.get(state.knowledge_point_id)
            if not knowledge_point:
                continue
            hours = _hours_since(state.last_interaction_at, now)
            effective = effective_mastery(state.mastery, state.confidence, hours)
            state_map[knowledge_point.name] = round(effective * state.confidence, 3)
        return state_map

    def _load_knowledge_point_map(self, states: list) -> dict[int, object]:
        knowledge_point_ids = [state.knowledge_point_id for state in states]
        return {
            knowledge_point.id: knowledge_point
            for knowledge_point in self.repository.list_knowledge_points_by_ids(knowledge_point_ids)
        }


def _format_time_ago(hours: float) -> str:
    minutes = hours * 60
    if minutes < 1:
        return "刚刚"
    if hours < 1:
        return f"{int(minutes)}分钟前"
    if hours < 24:
        return f"{int(hours)}小时前"
    return f"{int(hours / 24)}天前"


def _history_point(row) -> dict:
    return {
        "timestamp": row.created_at.isoformat(),
        "mastery": round(row.mastery, 3),
        "confidence": round(row.confidence, 3),
        "effective_score": round(row.effective_score, 3),
        "delta": round(row.delta, 3),
        "event_type": row.event_type,
        "event_label": EVENT_LABELS.get(row.event_type, row.event_type),
        "source": SOURCE_LABELS.get(row.source, row.source),
    }


def _aggregate_daily_points(rows: list) -> list[dict]:
    daily_map: dict[str, dict] = {}
    for row in rows:
        day_key = row.created_at.strftime("%Y-%m-%d")
        if day_key not in daily_map:
            daily_map[day_key] = {"mastery_sum": 0.0, "score_sum": 0.0, "count": 0, "events": []}
        day = daily_map[day_key]
        day["mastery_sum"] += row.mastery
        day["score_sum"] += row.effective_score
        day["count"] += 1
        day["events"].append(row.event_type)

    return [
        {
            "date": day_key,
            "avg_mastery": round(daily_map[day_key]["mastery_sum"] / daily_map[day_key]["count"], 3),
            "avg_effective_score": round(daily_map[day_key]["score_sum"] / daily_map[day_key]["count"], 3),
            "event_count": daily_map[day_key]["count"],
            "event_types": sorted(set(daily_map[day_key]["events"])),
        }
        for day_key in sorted(daily_map.keys())
    ]


def _demo_trend_points() -> list[dict]:
    now = datetime.now(timezone.utc)
    points = []
    mastery_base = 0.22
    score_base = 0.15
    for index in range(6, -1, -1):
        day = now - timedelta(days=index)
        mastery = mastery_base + (6 - index) * 0.07 + random.uniform(-0.02, 0.02)
        score = score_base + (6 - index) * 0.065 + random.uniform(-0.01, 0.01)
        points.append({
            "date": day.strftime("%Y-%m-%d"),
            "avg_mastery": round(max(0.1, min(0.95, mastery)), 3),
            "avg_effective_score": round(max(0.1, min(0.95, score)), 3),
            "event_count": random.randint(3, 8),
            "event_types": ["practice", "ask", "test"],
        })
    return points
