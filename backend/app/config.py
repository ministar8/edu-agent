from pathlib import Path

from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """应用配置，自动从项目根目录 .env 加载"""

    # ── LLM (OpenAI 兼容接口，阿里云百炼平台) ──────
    LLM_API_KEY: str = ""
    LLM_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL: str = "glm-5"

    # ── Embedding (OpenAI 兼容接口，默认本地 Ollama) ───
    EMBEDDING_API_KEY: str = "ollama"
    EMBEDDING_API_BASE: str = "http://localhost:11434/v1"
    EMBEDDING_MODEL: str = "bge-m3"
    EMBEDDING_DIM: int = 1024  # bge-m3 向量维度

    # ── ChromaDB ─────────────────────────────────────
    CHROMA_PERSIST_DIR: str = str(PROJECT_ROOT / "chroma_db")

    # ── Neo4j ──────────────────────────────────────
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = ""

    # ── Server ─────────────────────────────────────
    BACKEND_HOST: str = "127.0.0.1"
    BACKEND_PORT: int = 8000
    BACKEND_RELOAD: bool = False

    # ── Knowledge ──────────────────────────────────
    KNOWLEDGE_DIR: str = str(PROJECT_ROOT / "knowledge")

    # ── Auth ──────────────────────────────────────
    JWT_SECRET: str = "edu-agent-jwt-secret-change-in-production"

    model_config = {"env_file": str(PROJECT_ROOT / ".env"), "extra": "ignore"}


settings = Settings()
