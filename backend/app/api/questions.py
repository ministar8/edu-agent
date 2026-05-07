import asyncio
import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


class QuestionRequest(BaseModel):
    topic: str
    count: int = Field(default=1, ge=1, le=5)
    difficulty: str = "mixed"  # basic / medium / hard / mixed


class QuestionResponse(BaseModel):
    raw: str


@router.post("/generate", response_model=QuestionResponse)
async def generate_questions(req: QuestionRequest):
    """独立出题接口"""
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
        from app.agents.question_agent import generate_questions_with_retrieval

        raw = await asyncio.wait_for(
            generate_questions_with_retrieval(prompt),
            timeout=120,
        )

        if not isinstance(raw, str):
            raw = str(raw)
        raw = raw.strip()
        if not raw:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="题目生成失败：Question Agent 返回空内容。",
            )
        return QuestionResponse(raw=raw)
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
