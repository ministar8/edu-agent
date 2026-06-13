import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.auth import get_current_user
from app.core.dependencies import get_question_service
from app.core.error_responses import GENERIC_GRADING_ERROR, GENERIC_QUESTION_ERROR
from app.db import User
from app.schemas.questions import (
    GradeRequest,
    GradeResponse,
    QuestionRequest,
    QuestionResponse,
    WeakPointPracticeRequest,
    WrongQuestionItem,
)
from app.services.question_service import (
    QuestionGenerationError,
    QuestionNotFoundError,
    QuestionService,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ── 出题接口 ──────────────────────────────────────────────────

@router.post("/generate", response_model=QuestionResponse)
async def generate_questions(
    req: QuestionRequest,
    current_user: User = Depends(get_current_user),
    service: QuestionService = Depends(get_question_service),
):
    """独立出题接口 — 生成 + 解析 + 质量评估 + 持久化"""
    try:
        response = await service.generate_questions(req, current_user.id)
        if not response.raw:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="题目生成失败：Question Agent 返回空内容。",
            )
        return response
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="出题超时：Question Agent 未在限定时间内完成检索和生成。",
        )
    except QuestionGenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Question generation error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=GENERIC_QUESTION_ERROR,
        )


# ── Q4: 错题重练 ──────────────────────────────────────────────

@router.get("/wrong", response_model=list[WrongQuestionItem])
async def get_wrong_questions(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    service: QuestionService = Depends(get_question_service),
):
    """获取当前学生的错题列表（quality_score >= 0.5 的才返回）"""
    return service.list_wrong_questions(current_user.id, limit)


@router.post("/weak-point-practice", response_model=QuestionResponse)
async def weak_point_practice(
    req: WeakPointPracticeRequest,
    current_user: User = Depends(get_current_user),
    service: QuestionService = Depends(get_question_service),
):
    """根据学生薄弱知识点针对性出题，无数据时降级为随机常见知识点"""
    try:
        return await service.generate_weak_point_practice(req, current_user.id)
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="出题超时。",
        )
    except QuestionGenerationError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(e),
        ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Weak-point practice error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=GENERIC_QUESTION_ERROR,
        )


# ── Q5: 批改接口 ──────────────────────────────────────────────

@router.post("/{question_id}/grade", response_model=GradeResponse)
async def grade_question(
    question_id: int,
    req: GradeRequest,
    current_user: User = Depends(get_current_user),
    service: QuestionService = Depends(get_question_service),
):
    """批改单道题目 — 调 grading_agent，同时更新 QuestionRecord"""
    try:
        return await service.grade_question(question_id, req, current_user.id)
    except QuestionNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="批改超时：Grading Agent 未在限定时间内完成。",
        )
    except Exception as e:
        logger.error("Grading error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=GENERIC_GRADING_ERROR,
        )
