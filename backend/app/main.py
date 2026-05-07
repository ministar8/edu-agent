from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api import chat, knowledge, visualization, questions, auth
from app.db import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    from app.services.consistency_checker import start_periodic_check, stop_periodic_check
    start_periodic_check()
    yield
    stop_periodic_check()

app = FastAPI(
    title="智能教学辅导多Agent系统",
    description="基于 LangChain + LangGraph 的多智能体协作教学系统",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["Auth"])
app.include_router(chat.router, prefix="/api/chat", tags=["Chat"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["Knowledge"])
app.include_router(visualization.router, prefix="/api/visualization", tags=["Visualization"])
app.include_router(questions.router, prefix="/api/questions", tags=["Questions"])


@app.get("/")
async def root():
    return {"message": "智能教学辅导多Agent系统 API", "version": "1.0.0"}


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=settings.BACKEND_RELOAD,
    )
