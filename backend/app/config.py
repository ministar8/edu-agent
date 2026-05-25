import os
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from pathlib import Path
from typing import get_args, get_origin

from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_project_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str(PROJECT_ROOT / path)


def _coerce_env_value(field_type: object, value: str):
    origin = get_origin(field_type)
    args = get_args(field_type)
    target_type = args[0] if origin is not None and args else field_type

    if target_type is bool:
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if target_type is int:
        return int(value)
    if target_type is float:
        return float(value)
    return value


class Settings(BaseSettings):
    """应用配置，自动从项目根目录 .env 加载"""

    # ── LLM (OpenAI 兼容接口，DashScope 代理 / DeepSeek 官方) ──────
    LLM_API_KEY: str = ""
    LLM_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    LLM_MODEL: str = "deepseek-v4-pro"

    # ── Embedding (OpenAI 兼容接口，默认本地 Ollama) ───
    EMBEDDING_API_KEY: str = "ollama"
    EMBEDDING_API_BASE: str = "http://localhost:11434/v1"
    EMBEDDING_MODEL: str = "bge-m3"
    EMBEDDING_DIM: int = 1024  # bge-m3 向量维度

    # ── Reranker (阿里云百炼 qwen3-rerank API) ──────
    RERANK_ENABLED: bool = True
    RERANK_MODEL: str = "qwen3-rerank"
    RERANK_API_BASE: str = "https://dashscope.aliyuncs.com/compatible-api/v1"
    RERANK_MIN_SCORE: float = 0.4  # rerank 最低可信分数比例（0.3→0.4：严格过滤低置信度文档）

    HYDE_ENABLED: bool = True
    HYDE_MIN_DOCS: int = 2
    HYDE_RERANK_SCORE_THRESHOLD: float = 0.25
    HYDE_MAX_CHARS: int = 500

    # ── CRAG Context Compressor ──────────────────────
    CRAG_COMPRESS_ENABLED: bool = True
    CRAG_USE_LLM: bool = True
    CRAG_MAX_EVAL_BATCH: int = 8
    CRAG_SCORE_THRESHOLD: float = 0.15

    # ── Evaluation (RAGAS) ──────────────────────────
    # RAGAS 裁判模型配置（独立于 LLM_MODEL，支持不同 API 供应商）
    EVAL_JUDGE_MODEL: str = "deepseek-v4-flash"    # DeepSeek 官网裁判模型
    EVAL_JUDGE_API_BASE: str = "https://api.deepseek.com/v1"  # DeepSeek 官方 API
    EVAL_JUDGE_API_KEY: str = ""                    # 空=跟随 LLM_API_KEY
    # RAGAS 答案生成模型配置（独立于 LLM_MODEL）
    EVAL_ANSWER_MODEL: str = "deepseek-v4-flash"    # DeepSeek 官网答案生成模型
    EVAL_ANSWER_API_BASE: str = "https://api.deepseek.com/v1"  # DeepSeek 官方 API
    EVAL_ANSWER_API_KEY: str = ""                   # 空=跟随 LLM_API_KEY

    # ── Token Budget ────────────────────────────────
    CONTEXT_TOKEN_BUDGET: int = 6000
    MAX_STUDENT_PROFILE_TOKENS: int = 500

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
    JWT_SECRET: str = ""

    model_config = {
        "env_file": str(PROJECT_ROOT / ".env"),
        "extra": "ignore",
        # .env 文件优先级高于环境变量，防止 IDE 注入的 LLM_API_KEY 等覆盖项目配置
        "env_file_encoding": "utf-8",
    }


settings = Settings()

# ── 强制用 .env 值覆盖环境变量注入的配置 ──
# Windsurf 等 IDE 会在终端注入 LLM_API_KEY / LLM_MODEL 等环境变量，
# pydantic-settings 默认环境变量优先于 .env，导致项目配置被覆盖。
# 此处从 .env 文件重新读取所有字段并强制覆盖 settings 和 os.environ。
_env_file = PROJECT_ROOT / ".env"
if _env_file.exists():
    _overrides: dict[str, str] = {}
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if "=" in _line and not _line.startswith("#"):
            _k, _, _v = _line.partition("=")
            _k = _k.strip()
            _v = _v.strip()
            if _k and _v and hasattr(settings, _k):
                _overrides[_k] = _v
    if _overrides:
        import os as _os
        for _k, _v in _overrides.items():
            _field_type = Settings.model_fields[_k].annotation
            _typed_value = _coerce_env_value(_field_type, _v)
            if getattr(settings, _k, "") != _typed_value:
                setattr(settings, _k, _typed_value)
                _os.environ[_k] = _v
settings.CHROMA_PERSIST_DIR = _resolve_project_path(settings.CHROMA_PERSIST_DIR)
settings.KNOWLEDGE_DIR = _resolve_project_path(settings.KNOWLEDGE_DIR)
