import asyncio
import logging
import random
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import QuestionRecord, User, get_db
from app.api.auth import get_current_user
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ── 请求/响应模型 ──────────────────────────────────────────────

class QuestionRequest(BaseModel):
    topic: str
    count: int = Field(default=1, ge=1, le=5)
    difficulty: str = "mixed"  # basic / medium / hard / mixed


class QuestionResponse(BaseModel):
    raw: str
    questions: list[dict] = []
    batch_id: str | None = None


class GradeRequest(BaseModel):
    user_answer: str


class GradeResponse(BaseModel):
    score: float
    feedback: str
    is_wrong: bool


class WrongQuestionItem(BaseModel):
    id: int
    question_type: str | None
    difficulty: float
    stem: str
    standard_answer: str | None
    explanation: str | None
    user_answer: str | None
    grading_score: float | None
    created_at: str


class WeakPointPracticeRequest(BaseModel):
    count: int = Field(default=3, ge=1, le=5)


# ── 出题接口 ──────────────────────────────────────────────────

@router.post("/generate", response_model=QuestionResponse)
async def generate_questions(
    req: QuestionRequest,
    current_user: User = Depends(get_current_user),
):
    """独立出题接口 — 生成 + 解析 + 质量评估 + 持久化"""
    difficulty_map = {
        "basic": "基础",
        "medium": "中等",
        "hard": "困难",
        "mixed": "基础/中等/困难混合",
    }
    diff_label = difficulty_map.get(req.difficulty, "混合")
    count = max(1, min(req.count, 5))

    prompt = "\n".join([
        f"请围绕「{req.topic}」生成 {count} 道 408 练习题，难度要求：{diff_label}。",
        "必须先检索题库模板或教材知识依据，再基于检索结果生成。",
        "如果检索不到相关依据或工具调用失败，不要兜底生成题目，直接说明无法生成的具体原因。",
        "题型只能从选择题、填空题、简答题、综合应用题中选择，不要生成编程题。",
        "每题按以下格式输出：题目X、类型、难度、题干、标准答案、解析。",
        "题干和解析必须简洁，每题解析不超过80字。",
        "不要输出寒暄、背景介绍、额外总结或 Markdown 加粗符号。",
    ])

    try:
        from app.agents.question_agent import generate_and_persist_questions

        questions = await asyncio.wait_for(
            generate_and_persist_questions(
                prompt=prompt,
                user_id=current_user.id,
                conversation_id=None,
            ),
            timeout=settings.QUESTION_GEN_TIMEOUT,
        )

        # 检查是否有错误
        if questions and questions[0].get("error"):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=questions[0]["error"],
            )

        # 兼容：如果有 raw_text（解析失败），返回原始文本
        raw_text = ""
        batch_id = None
        if questions and questions[0].get("raw_text"):
            raw_text = questions[0]["raw_text"]
        else:
            # 拼接结构化题目为可读文本
            parts = []
            for i, q in enumerate(questions, 1):
                parts.append(f"题目{i}：\n类型：{q.get('question_type', '')}\n难度：{q.get('difficulty', '')}\n题干：{q.get('stem', '')}\n标准答案：{q.get('answer', '')}\n解析：{q.get('explanation', '')}")
            raw_text = "\n\n".join(parts)
            batch_id = questions[0].get("batch_id") if questions else None

        if not raw_text:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="题目生成失败：Question Agent 返回空内容。",
            )

        return QuestionResponse(
            raw=raw_text,
            questions=[q for q in questions if not q.get("error") and not q.get("raw_text")],
            batch_id=batch_id,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="出题超时：Question Agent 未在限定时间内完成检索和生成。",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Question generation error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"题目生成失败：{e}",
        )


# ── Q4: 错题重练 ──────────────────────────────────────────────

@router.get("/wrong", response_model=list[WrongQuestionItem])
async def get_wrong_questions(
    limit: int = 10,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前学生的错题列表（quality_score >= 0.5 的才返回）"""
    records = (
        db.query(QuestionRecord)
        .filter(
            QuestionRecord.user_id == current_user.id,
            QuestionRecord.is_wrong == True,  # noqa: E712
        )
        .order_by(QuestionRecord.created_at.desc())
        .limit(limit)
        .all()
    )

    # 过滤低质量题目
    result = []
    for r in records:
        if r.quality_score is not None and r.quality_score < 0.5:
            continue
        result.append(WrongQuestionItem(
            id=r.id,
            question_type=r.question_type,
            difficulty=r.difficulty,
            stem=r.stem,
            standard_answer=r.standard_answer,
            explanation=r.explanation,
            user_answer=r.user_answer,
            grading_score=r.grading_score,
            created_at=r.created_at.isoformat() if r.created_at else "",
        ))

    return result


# ── Q4: 薄弱专项练习 ──────────────────────────────────────────

_FALLBACK_TOPICS = [
    ("线性表", "数据结构"),
    ("进程同步", "操作系统"),
    ("Cache映射", "计算机组成原理"),
    ("TCP协议", "计算机网络"),
    ("二叉树", "数据结构"),
    ("死锁", "操作系统"),
    ("指令流水线", "计算机组成原理"),
    ("IP地址", "计算机网络"),
]


@router.post("/weak-point-practice", response_model=QuestionResponse)
async def weak_point_practice(
    req: WeakPointPracticeRequest,
    current_user: User = Depends(get_current_user),
):
    """根据学生薄弱知识点针对性出题，无数据时降级为随机常见知识点"""
    from app.services.knowledge_tracker import get_knowledge_tracker

    tracker = get_knowledge_tracker()
    weak_points = tracker.get_weak_points(current_user.id, threshold=0.4, limit=5)

    if not weak_points:
        # 降级：随机选常见知识点
        chosen = random.sample(_FALLBACK_TOPICS, min(req.count, len(_FALLBACK_TOPICS)))
        topics = [f"{t}（{cat}）" for t, cat in chosen]
        prompt_parts = [
            f"请围绕以下知识点生成 {req.count} 道 408 练习题，混合难度：",
            "、".join(topics),
            "必须先检索题库模板或教材知识依据，再基于检索结果生成。",
            "题型只能从选择题、填空题、简答题、综合应用题中选择。",
            "每题按以下格式输出：题目X、类型、难度、题干、标准答案、解析。",
            "题干和解析必须简洁，每题解析不超过80字。",
        ]
    else:
        topics = [wp["name"] for wp in weak_points]
        difficulties = []
        for wp in weak_points:
            pct = max(0, min(100, round(wp["effective_score"] * 100)))
            if pct < 30:
                difficulties.append("基础")
            elif pct < 50:
                difficulties.append("中等")
            else:
                difficulties.append("较难")

        prompt_parts = [
            f"请围绕以下薄弱知识点生成 {req.count} 道 408 练习题：",
            "、".join(topics),
            f"难度要求：{'/'.join(difficulties)}。",
            "必须先检索题库模板或教材知识依据，再基于检索结果生成。",
            "题型只能从选择题、填空题、简答题、综合应用题中选择。",
            "每题按以下格式输出：题目X、类型、难度、题干、标准答案、解析。",
            "题干和解析必须简洁，每题解析不超过80字。",
        ]

    prompt = "\n".join(prompt_parts)

    try:
        from app.agents.question_agent import generate_and_persist_questions

        questions = await asyncio.wait_for(
            generate_and_persist_questions(
                prompt=prompt,
                user_id=current_user.id,
                conversation_id=None,
            ),
            timeout=settings.QUESTION_GEN_TIMEOUT,
        )

        if questions and questions[0].get("error"):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=questions[0]["error"],
            )

        raw_text = ""
        batch_id = None
        if questions and questions[0].get("raw_text"):
            raw_text = questions[0]["raw_text"]
        else:
            parts = []
            for i, q in enumerate(questions, 1):
                parts.append(f"题目{i}：\n类型：{q.get('question_type', '')}\n难度：{q.get('difficulty', '')}\n题干：{q.get('stem', '')}\n标准答案：{q.get('answer', '')}\n解析：{q.get('explanation', '')}")
            raw_text = "\n\n".join(parts)
            batch_id = questions[0].get("batch_id") if questions else None

        return QuestionResponse(
            raw=raw_text or "无法生成练习题。",
            questions=[q for q in questions if not q.get("error") and not q.get("raw_text")],
            batch_id=batch_id,
        )
    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="出题超时。",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Weak-point practice error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"练习题生成失败：{e}",
        )


# ── Q5: 批改接口 ──────────────────────────────────────────────

@router.post("/{question_id}/grade", response_model=GradeResponse)
async def grade_question(
    question_id: int,
    req: GradeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """批改单道题目 — 调 grading_agent，同时更新 QuestionRecord"""
    record = db.query(QuestionRecord).filter(
        QuestionRecord.id == question_id,
        QuestionRecord.user_id == current_user.id,
    ).first()

    if not record:
        raise HTTPException(status_code=404, detail="题目不存在")

    try:
        from app.agents.grading_agent import grade_single_question

        result = await asyncio.wait_for(
            grade_single_question(
                stem=record.stem,
                standard_answer=record.standard_answer or "",
                user_answer=req.user_answer,
            ),
            timeout=settings.AGENT_RETRY_TIMEOUT,
        )
        score = result["score"]
        feedback = result["feedback"]
        is_wrong = result["is_wrong"]

        # 更新 QuestionRecord
        record.user_answer = req.user_answer
        record.grading_score = score
        record.is_wrong = is_wrong
        db.commit()

        # 发出追踪事件，更新 StudentKnowledgeState
        try:
            from app.events import TrackingEvent, emit
            if record.knowledge_point_id:
                if score >= 80:
                    event_type = "grading_excellent"
                    outcome = 1.0
                elif score >= 60:
                    event_type = "grading_pass"
                    outcome = 0.5
                else:
                    event_type = "grading_fail"
                    outcome = 0.0
                event = TrackingEvent(
                    user_id=current_user.id,
                    knowledge_point_ids=[record.knowledge_point_id],
                    event_type=event_type,
                    difficulty=record.difficulty,
                    outcome=outcome,
                )
                await emit(event)
        except Exception as evt_err:
            logger.warning("Failed to publish grading event: %s", evt_err)

        return GradeResponse(score=score, feedback=feedback, is_wrong=is_wrong)

    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="批改超时：Grading Agent 未在限定时间内完成。",
        )
    except Exception as e:
        logger.error("Grading error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批改失败：{e}",
        )
