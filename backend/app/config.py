import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from pathlib import Path

from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_project_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str(PROJECT_ROOT / path)

class Settings(BaseSettings):
    """应用配置，自动从项目根目录 .env 加载"""

    # ── LLM (OpenAI 兼容接口，DashScope 代理 / DeepSeek 官方) ──────
    LLM_API_KEY: str = ""
    LLM_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL: str = "qwen3.7-max"
    LLM_MODEL_FAST: str = "qwen3.6-27b"  # 分类/路由/简单任务用

    # ── Embedding (TEI bge-m3，本地 Docker 部署) ───
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_API_BASE: str = "http://localhost:11435"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIM: int = 1024  # bge-m3 向量维度

    # ── Reranker (本地 TEI bge-reranker-v2-m3) ──────
    RERANK_ENABLED: bool = True
    RERANK_MODE: str = "local"
    RERANK_LOCAL_URL: str = "http://localhost:8080"  # 本地 TEI reranker 地址
    RERANK_MIN_SCORE: float = 0.3  # rerank 最低可信分数比例（相对阈值：top_score * 此值）
    RERANK_ABSOLUTE_MIN_SCORE: float = 0.15  # rerank 绝对最低分数（低于此值直接丢弃，兜底保留 top-2）

    HYDE_ENABLED: bool = True
    HYDE_MIN_DOCS: int = 2
    HYDE_RERANK_SCORE_THRESHOLD: float = 0.25
    HYDE_MAX_CHARS: int = 500

    # ── Semantic Cache (ChromaDB-backed) ──────────────
    SEMANTIC_CACHE_ENABLED: bool = True
    SEMANTIC_CACHE_SIMILARITY_THRESHOLD: float = 0.88

    # ── Evaluation (RAGAS) ──────────────────────────
    # RAGAS 裁判模型配置（独立于 LLM_MODEL，支持不同 API 供应商）
    EVAL_JUDGE_MODEL: str = "qwen3.6-plus"    # 裁判模型（.env 可覆盖）
    EVAL_JUDGE_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # 百炼 OpenAI 兼容 API
    EVAL_JUDGE_API_KEY: str = ""                    # 空=跟随 LLM_API_KEY
    # RAGAS 答案生成模型配置（独立于 LLM_MODEL）
    EVAL_ANSWER_MODEL: str = "qwen3.7-plus"    # 阿里云百炼答案生成模型（额度999K，每样本仅1次调用）
    EVAL_ANSWER_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"  # 百炼 OpenAI 兼容 API
    EVAL_ANSWER_API_KEY: str = ""                   # 空=跟随 LLM_API_KEY

    # ── Token Budget ────────────────────────────────
    CONTEXT_TOKEN_BUDGET: int = 6000
    CONTEXT_TOKEN_BUDGET_SHALLOW: int = 3000  # 浅层查询 token 预算
    CONTEXT_TOKEN_BUDGET_DEEP: int = 8000     # 深层查询 token 预算
    MAX_STUDENT_PROFILE_TOKENS: int = 500

    # ── Agent Timeout (seconds) ──────────────────────
    GLOBAL_DEADLINE: int = 150         # 全局最大响应时间
    LLM_TIMEOUT: int = 90             # LLM HTTP 请求超时（秒）
    ROUTER_TIMEOUT: int = 8           # Supervisor 路由 LLM
    AGENT_PRIMARY_TIMEOUT: int = 90   # Agent 首次 invoke
    AGENT_RETRY_TIMEOUT: int = 45     # Agent 重试 A/B
    RAG_FALLBACK_TIMEOUT: int = 30    # RAG fallback LLM
    PRE_RETRIEVAL_TIMEOUT: int = 30   # 预检索（跳过 ReAct 第1轮）
    TOOL_CALL_TIMEOUT: int = 30       # 单次工具调用
    STREAM_TIMEOUT: int = 120         # SSE 流式整体超时
    QUESTION_GEN_TIMEOUT: int = 120   # 出题 Agent 超时
    EMBEDDING_TIMEOUT: int = 60       # Embedding API 请求超时
    RERANK_TIMEOUT: int = 30          # Rerank API 请求超时
    DECOMPOSE_TIMEOUT: float = 10.0   # 查询分解 LLM 超时

    # ── Agent Temperature 分级 ──────────────────────
    TEMP_PRECISE: float = 0.0         # 分类/判断/批改等确定性任务
    TEMP_CREATIVE: float = 0.3        # 生成/出题等需要多样性的任务
    TEMP_DEFAULT: float = 0.3         # 默认
    TEMP_SYNTHESIS: float = 0.15       # 综合/合成（准确但允许自然表达）

    # ── ChromaDB ─────────────────────────────────────
    CHROMA_PERSIST_DIR: str = str(PROJECT_ROOT / "chroma_db")
    CHROMA_HOST: str = "127.0.0.1"
    CHROMA_PORT: int = 8100

    # ── Neo4j ──────────────────────────────────────
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = ""

    # ── Server ─────────────────────────────────────
    BACKEND_HOST: str = "127.0.0.1"
    BACKEND_PORT: int = 8000
    BACKEND_RELOAD: bool = False
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ── Knowledge ──────────────────────────────────
    KNOWLEDGE_DIR: str = str(PROJECT_ROOT / "knowledge")

    # ── Auth ──────────────────────────────────────
    JWT_SECRET: str = ""
    AUTH_COOKIE_SECURE: bool = False
    AUTH_COOKIE_SAMESITE: str = "lax"

    model_config = {
        "env_file": str(PROJECT_ROOT / ".env"),
        "extra": "ignore",
        "env_file_encoding": "utf-8",
    }

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        return init_settings, dotenv_settings, env_settings, file_secret_settings


settings = Settings()
settings.CHROMA_PERSIST_DIR = _resolve_project_path(settings.CHROMA_PERSIST_DIR)
settings.KNOWLEDGE_DIR = _resolve_project_path(settings.KNOWLEDGE_DIR)
