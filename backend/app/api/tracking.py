"""知识追踪 API

- GET  /api/tracking/profile          学生画像（各学科掌握度概览）
- GET  /api/tracking/weak-points       薄弱知识点列表
- GET  /api/tracking/recommendations   学习路径推荐
- GET  /api/tracking/category/{name}   单学科详细统计
- GET  /api/tracking/knowledge-points  所有知识点列表（含掌握度）
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.db import KnowledgePointRegistry, StudentKnowledgeState, User, get_db
from app.services.knowledge_tracker import effective_mastery, get_knowledge_tracker

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 学生画像 ─────────────────────────────────────────────────

@router.get("/profile")
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前学生的知识画像"""
    user = current_user
    tracker = get_knowledge_tracker()
    profile = tracker.get_student_profile(user.id)
    return {"success": True, "data": profile}


# ── 薄弱知识点 ───────────────────────────────────────────────

@router.get("/weak-points")
async def get_weak_points(
    threshold: float = 0.3,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前学生的薄弱知识点"""
    user = current_user
    tracker = get_knowledge_tracker()
    weak = tracker.get_weak_points(user.id, threshold=threshold, limit=limit)
    return {"success": True, "data": weak}


# ── 学习路径推荐 ─────────────────────────────────────────────

@router.get("/recommendations")
async def get_recommendations(
    limit: int = 5,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """基于薄弱点 + KG 前置知识推荐学习路径"""
    user = current_user
    tracker = get_knowledge_tracker()
    recs = tracker.get_recommendations(user.id, limit=limit)
    return {"success": True, "data": recs}


# ── 单学科详细统计 ───────────────────────────────────────────

@router.get("/category/{category}")
async def get_category_detail(
    category: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取指定学科下所有知识点的掌握详情"""
    user = current_user

    # 查询该学科所有知识点
    all_kps = db.query(KnowledgePointRegistry).filter(
        KnowledgePointRegistry.category == category,
        KnowledgePointRegistry.chapter != "",
    ).all()

    # 查询该用户在该学科的状态
    states = db.query(StudentKnowledgeState).filter(
        StudentKnowledgeState.user_id == user.id,
        StudentKnowledgeState.category == category,
    ).all()

    state_map = {s.knowledge_point_id: s for s in states}
    now = datetime.now(timezone.utc)

    points = []
    for kp in all_kps:
        s = state_map.get(kp.id)
        if s:
            hours = (now - s.last_interaction_at).total_seconds() / 3600
            eff_m = effective_mastery(s.mastery, s.confidence, hours)
            eff_score = eff_m * s.confidence
            points.append({
                "id": kp.id,
                "name": kp.name,
                "chapter": kp.chapter,
                "difficulty": kp.difficulty,
                "mastery": round(eff_m, 3),
                "confidence": round(s.confidence, 3),
                "effective_score": round(eff_score, 3),
                "interaction_count": s.interaction_count,
                "total_positive": s.total_positive,
                "total_negative": s.total_negative,
                "last_interaction_at": s.last_interaction_at.isoformat(),
                "source": s.source,
                "tracked": True,
            })
        else:
            points.append({
                "id": kp.id,
                "name": kp.name,
                "chapter": kp.chapter,
                "difficulty": kp.difficulty,
                "mastery": 0.0,
                "confidence": 0.0,
                "effective_score": 0.0,
                "interaction_count": 0,
                "total_positive": 0,
                "total_negative": 0,
                "last_interaction_at": None,
                "source": "",
                "tracked": False,
            })

    # 按章分组
    chapters: dict[str, list] = {}
    for p in points:
        ch = p["chapter"] or "其他"
        chapters.setdefault(ch, []).append(p)

    return {
        "success": True,
        "data": {
            "category": category,
            "total_points": len(points),
            "tracked_points": sum(1 for p in points if p["tracked"]),
            "avg_mastery": round(
                sum(p["mastery"] for p in points) / len(points), 3
            ) if points else 0,
            "chapters": chapters,
        },
    }


# ── 所有知识点列表 ───────────────────────────────────────────

@router.get("/knowledge-points")
async def list_knowledge_points(
    category: str = "",
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出所有已注册的知识点（可选按学科过滤）"""
    user = current_user

    query = db.query(KnowledgePointRegistry)
    if category:
        query = query.filter(KnowledgePointRegistry.category == category)
    kps = query.all()

    return {
        "success": True,
        "data": [
            {
                "id": kp.id,
                "name": kp.name,
                "category": kp.category,
                "chapter": kp.chapter,
                "heading_path": kp.heading_path,
                "difficulty": kp.difficulty,
                "kg_node": kp.kg_node,
                "source_file": kp.source_file,
            }
            for kp in kps
        ],
    }
