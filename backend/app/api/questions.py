import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.agents.question_agent import create_question_agent
from app.rag.retriever import get_llm

logger = logging.getLogger(__name__)

router = APIRouter()


class QuestionRequest(BaseModel):
    topic: str
    count: int = 3
    difficulty: str = "mixed"  # basic / medium / hard / mixed


class QuestionItem(BaseModel):
    question: str
    answer: str
    explanation: str
    difficulty: str = "medium"


class QuestionResponse(BaseModel):
    questions: list[QuestionItem] = []
    raw: str = ""


@router.post("/generate", response_model=QuestionResponse)
async def generate_questions(req: QuestionRequest):
    """独立出题接口，直接调用 question_agent"""
    difficulty_map = {
        "basic": "基础",
        "medium": "中等",
        "hard": "困难",
        "mixed": "基础/中等/困难混合",
    }
    diff_label = difficulty_map.get(req.difficulty, "混合")

    prompt = (
        f"请围绕「{req.topic}」生成 {req.count} 道练习题，"
        f"难度要求：{diff_label}。\n"
        "每道题包含：题目、标准答案、详细解析、难度等级。"
    )

    try:
        agent = create_question_agent()
        result = agent.invoke(
            {"messages": [{"role": "user", "content": prompt}]},
        )
        # 提取最终回答
        raw = result["messages"][-1].content
        return QuestionResponse(raw=raw)
    except Exception as e:
        logger.error("Question generation error: %s", e)
        return QuestionResponse(raw=f"出题失败: {e}")
