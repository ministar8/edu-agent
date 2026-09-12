import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

from dotenv import find_dotenv
from pydantic import BeforeValidator, HttpUrl, SecretStr, TypeAdapter, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from schema.models import (
    GATEWAY_DEFAULT_MODEL,
    Gateway,
    make_model_ref,
    model_refs_for,
    parse_model_ref,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_project_path(value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str(PROJECT_ROOT / path)


class DatabaseType(StrEnum):
    SQLITE = "sqlite"


class LogLevel(StrEnum):
    """日志级别（对齐参考项目）。"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def to_logging_level(self) -> int:
        """转换为 logging 模块的级别常量。"""
        import logging

        return {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.CRITICAL: logging.CRITICAL,
        }[self]


def check_str_is_http(x: str) -> str:
    """校验为合法 HTTP(S) URL，并去掉尾部斜杠（避免拼接路径出现 //）。"""
    http_url_adapter = TypeAdapter(HttpUrl)
    return str(http_url_adapter.validate_python(x)).rstrip("/")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=find_dotenv(),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        validate_default=False,
    )

    MODE: str | None = None
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    GRACEFUL_SHUTDOWN_TIMEOUT: int = 30
    LOG_LEVEL: LogLevel = LogLevel.INFO

    # ── LLM 网关凭证（配了哪个 key 就启用哪个网关）──────
    DASHSCOPE_API_KEY: SecretStr | None = None
    DEEPSEEK_API_KEY: SecretStr | None = None
    USE_FAKE_MODEL: bool = False

    # ── 网关端点 ──────────────────────────────
    DASHSCOPE_API_BASE: Annotated[str, BeforeValidator(check_str_is_http)] = (
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    DEEPSEEK_API_BASE: Annotated[str, BeforeValidator(check_str_is_http)] = (
        "https://api.deepseek.com"
    )

    # ── RAG 检索链使用的文本模型（格式 <gateway>:<model_id>）──────
    LLM_MODEL: str = "deepseek:deepseek-v4-flash"
    LLM_MODEL_FAST: str = "deepseek:deepseek-v4-pro"

    # 空串表示「尚未推导」；model_post_init 必定填入，否则构造期直接报错
    DEFAULT_MODEL: str = ""
    AVAILABLE_MODELS: set[str] = set()

    # ── Embedding（本地 TEI bge-m3）───────────────────
    EMBEDDING_API_KEY: SecretStr | None = None
    EMBEDDING_API_BASE: Annotated[str, BeforeValidator(check_str_is_http)] = (
        "http://localhost:11435"
    )
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_DIM: int = 1024

    # ── Reranker（本地 TEI bge-reranker-v2-m3）──────
    RERANK_ENABLED: bool = True
    RERANK_MODE: str = "local"
    RERANK_LOCAL_URL: Annotated[str, BeforeValidator(check_str_is_http)] = "http://localhost:8080"
    RERANK_MIN_SCORE: float = 0.3
    RERANK_ABSOLUTE_MIN_SCORE: float = 0.15

    # ── HyDE ──────────────────────────────────────
    HYDE_ENABLED: bool = True
    HYDE_MIN_DOCS: int = 2
    HYDE_RERANK_SCORE_THRESHOLD: float = 0.25
    HYDE_MAX_CHARS: int = 500

    # ── Semantic Cache（ChromaDB-backed）──────────
    SEMANTIC_CACHE_ENABLED: bool = True
    SEMANTIC_CACHE_SIMILARITY_THRESHOLD: float = 0.88

    # ── Token Budget ────────────────────────────────
    CONTEXT_TOKEN_BUDGET: int = 6000
    CONTEXT_TOKEN_BUDGET_SHALLOW: int = 3000
    CONTEXT_TOKEN_BUDGET_DEEP: int = 8000
    MAX_STUDENT_PROFILE_TOKENS: int = 800

    # ── 超时（seconds）─────────────────────────────
    # 只保留真正被代码引用的项。此前另有 8 个字段（GLOBAL_DEADLINE / ROUTER_TIMEOUT /
    # AGENT_PRIMARY_TIMEOUT / AGENT_RETRY_TIMEOUT / RAG_FALLBACK_TIMEOUT / STREAM_TIMEOUT /
    # QUESTION_GEN_TIMEOUT / DECOMPOSE_TIMEOUT）从未被引用 —— 看着像有保护，实际没有，
    # 已删除。要恢复某一项，请连同使用它的逻辑一起加。
    LLM_TIMEOUT: int = 90  # 单次 LLM 调用（客户端 request_timeout + RAG 链调用）
    PRE_RETRIEVAL_TIMEOUT: int = 30  # 检索前的 LLM 调用（查询分类 / 查询分解）
    TOOL_CALL_TIMEOUT: int = 30  # 检索内部各并行分支的预算
    EMBEDDING_TIMEOUT: int = 60
    RERANK_TIMEOUT: int = 30

    # ── Agent / LLM Temperature 分级（语义槽见 agents/temperature.py）──
    # TEMP_PRECISE   批改评分：可复现
    # TEMP_CREATIVE  出题：多样性
    # TEMP_DEFAULT   知识讲解 / supervisor / 检索链多数步骤
    # TEMP_SYNTHESIS 综合摘要（预留，当前无调用方）
    TEMP_PRECISE: float = 0.0
    TEMP_CREATIVE: float = 0.3
    TEMP_DEFAULT: float = 0.3
    TEMP_SYNTHESIS: float = 0.15

    # ── ChromaDB ─────────────────────────────────────
    CHROMA_PERSIST_DIR: str = str(PROJECT_ROOT / "chroma_db")
    CHROMA_HOST: str = "127.0.0.1"
    CHROMA_PORT: int = 8100

    # ── Knowledge ──────────────────────────────────
    KNOWLEDGE_DIR: str = str(PROJECT_ROOT / "knowledge")

    # ── Database（checkpointer / store）────────────
    DATABASE_TYPE: DatabaseType = DatabaseType.SQLITE
    SQLITE_DB_PATH: str = "checkpoints.db"
    SQLITE_STORE_PATH: str = "store.db"

    # ── 长期记忆写入 / weak_topics 派生 ────────────────
    MEMORY_WRITE_TIMEOUT: float = 1.5
    MEMORY_WEAK_SCORE: float = 60.0
    MEMORY_GOOD_SCORE: float = 85.0
    MEMORY_WEAK_WINDOW_DAYS: int = 30
    MEMORY_WEAK_MIN_HITS: int = 2
    MEMORY_WEAK_CLEAR_MIN_GOOD_HITS: int = 2
    MEMORY_EPISODE_SCAN_LIMIT: int = 50
    # 短期：送入 LLM 的非 system 消息条数上限；0 = 不裁剪
    MEMORY_HISTORY_MAX_MESSAGES: int = 20
    # 长期 episodes 保留：TTL 天数 / 每用户上限；0 = 关闭该项
    MEMORY_EPISODE_TTL_DAYS: int = 90
    MEMORY_EPISODE_MAX_PER_USER: int = 200

    # ── Auth（JWT）────────────────────────────────
    JWT_SECRET: SecretStr | None = None
    AUTH_COOKIE_SECURE: bool = False
    AUTH_COOKIE_SAMESITE: Literal["lax", "none", "strict"] = "lax"

    # ── 可观测性：LangSmith 追踪（对齐参考项目）─────────
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_PROJECT: str = "default"
    LANGCHAIN_ENDPOINT: Annotated[str, BeforeValidator(check_str_is_http)] = (
        "https://api.smith.langchain.com"
    )
    LANGCHAIN_API_KEY: SecretStr | None = None

    # ── CORS ─────────────────────────────────────
    # 前端（static/）由本服务在根路径挂载提供，与 API 同源，浏览器不会做跨域校验，
    # 因此默认只允许本服务自身来源。仅当把前端单独部署到其他源时才需要改这里。
    # 逗号分隔的 origin 列表，不能套 check_str_is_http（那是单 URL 校验）
    CORS_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"

    def _active_gateways(self) -> list[Gateway]:
        """已启用的网关：配了 key（或开了假模型）即视为启用。"""
        credentials = {
            Gateway.DASHSCOPE: self.DASHSCOPE_API_KEY,
            Gateway.DEEPSEEK: self.DEEPSEEK_API_KEY,
            Gateway.FAKE: self.USE_FAKE_MODEL,
        }
        return [gateway for gateway, value in credentials.items() if value]

    def model_post_init(self, __context: Any) -> None:
        """依据已启用的网关推导默认模型与可用模型清单。"""
        active = self._active_gateways()
        if not active:
            raise ValueError(
                "未配置任何 LLM 网关。请在 .env 中设置 DASHSCOPE_API_KEY 或 DEEPSEEK_API_KEY"
                "（注意旧字段 LLM_API_KEY 已废弃），或设置 USE_FAKE_MODEL=true 用于测试。"
            )

        # USE_FAKE_MODEL 必须赢过真实 key，保证测试环境不被真实模型污染
        if self.USE_FAKE_MODEL and not self.DEFAULT_MODEL:
            self.DEFAULT_MODEL = make_model_ref(Gateway.FAKE, GATEWAY_DEFAULT_MODEL[Gateway.FAKE])

        for gateway in active:
            self.AVAILABLE_MODELS |= model_refs_for(gateway)
            if not self.DEFAULT_MODEL:
                self.DEFAULT_MODEL = make_model_ref(gateway, GATEWAY_DEFAULT_MODEL[gateway])

        if self.DEFAULT_MODEL:
            self.AVAILABLE_MODELS.add(self.DEFAULT_MODEL)

    def gateway_for(self, model_ref: str) -> Gateway:
        """从 ``<gateway>:<model_id>`` 标识里解析出网关。

        未知网关直接报错，不再「猜」—— 静默走错 base 比报错难排查得多。
        """
        return parse_model_ref(model_ref)[0]

    def api_base_for_model(self, model_ref: str) -> str:
        """按标识里的网关返回对应的 API base。"""
        match self.gateway_for(model_ref):
            case Gateway.DEEPSEEK:
                return self.DEEPSEEK_API_BASE
            case Gateway.FAKE:
                return ""
            case _:
                return self.DASHSCOPE_API_BASE

    def api_key_for_model(self, model_ref: str) -> str:
        """按标识里的网关返回对应的 API key；未配置则抛出明确错误。"""
        match self.gateway_for(model_ref):
            case Gateway.DEEPSEEK:
                key, env_name = self.DEEPSEEK_API_KEY, "DEEPSEEK_API_KEY"
            case Gateway.FAKE:
                return ""
            case _:
                key, env_name = self.DASHSCOPE_API_KEY, "DASHSCOPE_API_KEY"
        if not key:
            raise RuntimeError(f"模型 {model_ref} 需要 {env_name}，但该环境变量未配置")
        return key.get_secret_value()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def BASE_URL(self) -> str:
        return f"http://{self.HOST}:{self.PORT}"

    def is_dev(self) -> bool:
        return self.MODE == "dev"

    def export_langsmith_env(self) -> bool:
        """把 LangSmith 追踪配置同步到进程环境变量，返回追踪是否启用。

        LangChain 从 os.environ 读取这些变量并在每次调用时自动埋点，因此仅声明在
        Settings 里不够，必须写进进程环境（对齐参考项目 run_service.py 的 load_dotenv 思路）。
        """
        os.environ["LANGCHAIN_TRACING_V2"] = "true" if self.LANGCHAIN_TRACING_V2 else "false"
        os.environ["LANGCHAIN_PROJECT"] = self.LANGCHAIN_PROJECT
        os.environ["LANGCHAIN_ENDPOINT"] = self.LANGCHAIN_ENDPOINT
        if self.LANGCHAIN_API_KEY:
            os.environ["LANGCHAIN_API_KEY"] = self.LANGCHAIN_API_KEY.get_secret_value()
        return self.LANGCHAIN_TRACING_V2


settings = Settings()
settings.CHROMA_PERSIST_DIR = _resolve_project_path(settings.CHROMA_PERSIST_DIR)
settings.KNOWLEDGE_DIR = _resolve_project_path(settings.KNOWLEDGE_DIR)
