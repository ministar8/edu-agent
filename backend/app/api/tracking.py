"""知识追踪 API

- GET  /api/tracking/profile          学生画像（各学科掌握度概览）
- GET  /api/tracking/weak-points       薄弱知识点列表
- GET  /api/tracking/recommendations   学习路径推荐
- GET  /api/tracking/learning-path     学习路径可视化（前置知识链）
- GET  /api/tracking/category/{name}   单学科详细统计
- GET  /api/tracking/recent            最近交互记录
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.auth import get_current_user
from app.core.dependencies import get_tracking_query_service
from app.db import User
from app.services.knowledge_tracker import get_knowledge_tracker
from app.services.tracking_query_service import TrackingQueryService

router = APIRouter()


# ── 学生画像 ─────────────────────────────────────────────────

@router.get("/profile")
async def get_profile(
    current_user: User = Depends(get_current_user),
):
    """获取当前学生的知识画像"""
    tracker = get_knowledge_tracker()
    profile = tracker.get_student_profile(current_user.id)
    return {"success": True, "data": profile}


# ── 薄弱知识点 ───────────────────────────────────────────────

@router.get("/weak-points")
async def get_weak_points(
    threshold: float = 0.3,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
):
    """获取当前学生的薄弱知识点"""
    tracker = get_knowledge_tracker()
    weak = tracker.get_weak_points(current_user.id, threshold=threshold, limit=limit)
    return {"success": True, "data": weak}


# ── 学习路径推荐 ─────────────────────────────────────────────

@router.get("/recommendations")
async def get_recommendations(
    limit: int = 5,
    current_user: User = Depends(get_current_user),
):
    """基于薄弱点 + KG 前置知识推荐学习路径"""
    tracker = get_knowledge_tracker()
    recs = tracker.get_recommendations(current_user.id, limit=limit)
    return {"success": True, "data": recs}


# ── 单学科详细统计 ───────────────────────────────────────────

@router.get("/category/{category}")
async def get_category_detail(
    category: str,
    current_user: User = Depends(get_current_user),
    service: TrackingQueryService = Depends(get_tracking_query_service),
):
    """获取指定学科下所有知识点的掌握详情"""
    return service.get_category_detail(current_user.id, category)


# ── 学习路径可视化 ──────────────────────────────────────────────

@router.get("/learning-path")
async def get_learning_path(
    limit: int = 5,
    current_user: User = Depends(get_current_user),
    service: TrackingQueryService = Depends(get_tracking_query_service),
):
    """获取薄弱知识点的学习路径（前置知识链 + 掌握度）"""
    return service.get_learning_path(current_user.id, limit)


@router.get("/recent")
async def get_recent_interactions(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    service: TrackingQueryService = Depends(get_tracking_query_service),
):
    """获取当前学生最近的交互记录（按时间倒序）"""
    return service.get_recent_interactions(current_user.id, limit)


@router.get("/mastery-trend")
async def get_mastery_trend(
    knowledge_point_id: int | None = None,
    category: str = "",
    days: int = 30,
    current_user: User = Depends(get_current_user),
    service: TrackingQueryService = Depends(get_tracking_query_service),
):
    """获取掌握度变化趋势

    支持两种模式：
    1. 指定 knowledge_point_id → 单个知识点趋势
    2. 指定 category → 该学科下所有被追踪知识点的平均趋势
    3. 无参数 → 全部被追踪知识点的平均趋势
    """
    return service.get_mastery_trend(
        user_id=current_user.id,
        knowledge_point_id=knowledge_point_id,
        category=category,
        days=days,
    )
