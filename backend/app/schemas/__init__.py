"""Request / response schemas."""
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserResponse
from app.schemas.chat import ChatRequest, ChatResponse, ConversationDetail, ConversationItem, MessageItem
from app.schemas.knowledge import KGEdge, KGImportRequest, KGNode
from app.schemas.questions import GradeRequest, GradeResponse, QuestionRequest, QuestionResponse, WeakPointPracticeRequest, WrongQuestionItem

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "ConversationDetail",
    "ConversationItem",
    "GradeRequest",
    "GradeResponse",
    "KGEdge",
    "KGImportRequest",
    "KGNode",
    "LoginRequest",
    "MessageItem",
    "QuestionRequest",
    "QuestionResponse",
    "RegisterRequest",
    "TokenResponse",
    "UserResponse",
    "WeakPointPracticeRequest",
    "WrongQuestionItem",
]
