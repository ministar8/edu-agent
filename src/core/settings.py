import os
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

from dotenv import find_dotenv
from pydantic import BeforeValidator, HttpUrl, SecretStr, TypeAdapter, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from schema.models import (
    GATEWAY_DEFAULT_MODEL,
    GATEWAY_MODELS,
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
    # 测试用：以确定性哈希向量替代 TEI embedding，使检索链无需外部服务即可运行。
    # 与 USE_FAKE_MODEL 同一模式（见 core.llm.FakeToolModel）。
    USE_FAKE_EMBEDDING: bool = False
    # 测试用：以确定性本地打分替代 TEI ``/rerank``，使**重排链路**（预筛选 / top_k 截断 /
    # 双重阈值过滤 / rerank_score 写入）在无 TEI 环境下也能被门禁覆盖。
    # 同样与 USE_FAKE_MODEL 同一模式（实现见 rag.reranker._fake_rerank）。
    #
    # ⚠️ 它只让**管线**可跑，不复制 bge-reranker 的分数分布 —— 生产里的绝对阈值
    # （RERANK_ABSOLUTE_MIN_SCORE 等）是按真实模型分布标定的。所以假重排路由上的
    # 指标**不能**与生产对比，只能自己和自己比（与基线同环境）。
    USE_FAKE_RERANK: bool = False

    # ── 网关端点 ──────────────────────────────
    DASHSCOPE_API_BASE: Annotated[str, BeforeValidator(check_str_is_http)] = (
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    DEEPSEEK_API_BASE: Annotated[str, BeforeValidator(check_str_is_http)] = (
        "https://api.deepseek.com"
    )

    # ── RAG 检索链使用的文本模型（格式 <gateway>:<model_id>）──────
    LLM_MODEL: str = "deepseek:deepseek-v4-flash"
    # with_structured_output 策略：DashScope/DeepSeek 兼容端上 function_calling 最稳
    STRUCTURED_OUTPUT_METHOD: Literal["function_calling", "json_mode", "json_schema"] = (
        "function_calling"
    )

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
    RERANK_LOCAL_URL: Annotated[str, BeforeValidator(check_str_is_http)] = "http://localhost:8080"
    RERANK_MIN_SCORE: float = 0.3
    RERANK_ABSOLUTE_MIN_SCORE: float = 0.15

    # ── HyDE ──────────────────────────────────────
    HYDE_ENABLED: bool = True
    HYDE_MIN_DOCS: int = 2
    HYDE_RERANK_SCORE_THRESHOLD: float = 0.25
    HYDE_MAX_CHARS: int = 500

    # ── 检索阈值（可经 `.env` 覆盖）─────────────────
    # 这几项此前硬编码在 `retriever.py` 里，注释写着「基于采样校准」。
    # 硬编码的问题不是"不好看"，而是：**调参必须改代码** ——
    # 于是调参变成"在代码里试数"，试完容易忘记清理，或试了没记下原因。
    # 提到 settings 后调参只改 `.env`，代码保持干净。
    #
    # ⚠️ **改这些值会改变检索质量** —— 改完必须重跑检索质量门禁
    #    （`python -m evaluation.retrieval_gate`）确认没有退化。
    RETRIEVAL_SCORE_THRESHOLD: float = 0.06
    """RRF 融合分数阈值。0.06 ≈「至少 1 路前 7」或「2 路前 15」，
    过滤掉排名 #8+ 的单路噪声。注意这是 **RRF 融合分**，不是余弦距离。"""

    RERANK_EXPAND_FACTOR: int = 5
    """重排前的候选池倍数（`coarse_k = min(k * factor, 50)`）。
    知识库扩充后需要更大候选池 —— 调大可提召回，代价是重排耗时。"""

    RRF_BASELINE_WEIGHT: float = 1.5
    """权重校准基准（semantic 的 default 权重）。
    实际阈值 = 基础阈值 × `max_w / RRF_BASELINE_WEIGHT`。"""

    # ── BM25 候选池（backlog #34）────────────────────
    # 词面命中的候选集截断：`limit = max(k * FACTOR, FLOOR)`。
    # ★ 现状（3 / 0）实测确实在触发截断 —— 某词命中 178 篇只取 15 篇。
    #   **但放宽的收益是假 embedding 的伪影**：09-23 复测（四条配置对照）显示，
    #   假路由上 `hit@1` +5pp，**真实 embedding 路由上收益为零**（逐位相同）。
    #   → 默认值**刻意保持现状**；这里提成配置只是为了让它可测、可调，**不改行为**。
    BM25_CANDIDATE_FACTOR: int = 3
    """候选池 = `k × FACTOR`。"""

    BM25_CANDIDATE_FLOOR: int = 0
    """候选池下限（0 = 不设下限）。★ 别按直觉设成 300 —— 见上面 #34 的复测结论。"""

    # ── Semantic Cache（ChromaDB-backed）──────────
    SEMANTIC_CACHE_ENABLED: bool = True
    SEMANTIC_CACHE_SIMILARITY_THRESHOLD: float = 0.88

    # ── Token Budget ────────────────────────────────
    CONTEXT_TOKEN_BUDGET: int = 6000

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

    # ── 图执行上界 ──────────────────────────────────
    # supervisor 图层若因模型异常（反复分派同一专家）进入循环，需要一道显式护栏。
    # 不设置时 LangGraph 用的是 DEFAULT_RECURSION_LIMIT = 10007 —— 每次都至少一次
    # supervisor + 一次专家 LLM 调用，1 万步意味着上万次调用、还可能触发模型费用事故，
    # 表现为「请求长时间不返回」而非快速失败。
    #
    # 取值依据（合成场景实测，专家每轮工具调用约耗 2-3 step，且子图与外层共享预算）：
    #   专家 ≤20 轮工具调用 → 60 步够用；≥30 轮 → 会被截断。
    # 真实 408 辅导场景专家通常 1-3 次工具调用（最多 5-8 次），80 步留了 4 倍以上余量，
    # 同时仍比默认值早约 125 倍终止异常循环。
    AGENT_RECURSION_LIMIT: int = 80

    # ── Agent / LLM Temperature 分级（语义槽见 agents/temperature.py）──
    # TEMP_PRECISE   批改评分：可复现
    # TEMP_CREATIVE  出题：多样性
    # TEMP_DEFAULT   知识讲解 / supervisor / 检索链多数步骤
    TEMP_PRECISE: float = 0.0
    TEMP_CREATIVE: float = 0.3
    TEMP_DEFAULT: float = 0.3

    # ── ChromaDB ─────────────────────────────────────
    CHROMA_PERSIST_DIR: str = str(PROJECT_ROOT / "chroma_db")
    CHROMA_HOST: str = "127.0.0.1"
    CHROMA_PORT: int = 8100
    # 入库后等 HNSW 落盘的就绪屏障参数。Chroma 的 PersistentClient 在 add_documents
    # 返回后段文件可能尚未落盘，此时查询会抛 "Nothing found on disk"（间歇性）。
    INGEST_READY_RETRIES: int = 8
    INGEST_READY_DELAY: float = 0.5
    # 预热成功率低于此值即视为异常并告警。预热全落空通常意味着索引未就绪或检索链故障，
    # 但旧代码只打印一行 INFO，导致问题无声无息。
    WARMUP_MIN_SUCCESS_RATE: float = 0.8

    # ── Knowledge ──────────────────────────────────
    KNOWLEDGE_DIR: str = str(PROJECT_ROOT / "knowledge")

    # ── Database（checkpointer / store）────────────
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
    # Store 向量索引（复用 RAG TEI）；测试可关以免依赖 TEI
    MEMORY_STORE_VECTOR_ENABLED: bool = True
    MEMORY_PRIVACY_REDACT: bool = True

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
        """推导默认模型与可用清单，并校验会实际用到的模型引用。"""
        active = self._active_gateways()
        if not active:
            raise ValueError(
                "未配置任何 LLM 网关。请在 .env 中设置 DASHSCOPE_API_KEY 或 DEEPSEEK_API_KEY"
                "（注意旧字段 LLM_API_KEY 已废弃），或设置 USE_FAKE_MODEL=true 用于测试。"
            )

        # ── USE_FAKE_MODEL：必须赢过 .env 里的真实引用，且必须在**任何校验之前**覆盖 ──
        # 顺序是关键：下面的 _validate_model_ref 会拒绝"网关未启用"的引用，而 .env 里
        # 常常显式配了 DEFAULT_MODEL / LLM_MODEL 指向真实网关。若把覆盖放到校验之后，
        # 无 key 环境（CI）会在覆盖生效之前就先抛错 —— 实测确实如此。
        #
        # 两个引用都要拉回假网关：
        #   * DEFAULT_MODEL 供 agent 层 get_model() 使用
        #   * LLM_MODEL     供 RAG 检索链 get_llm() 使用，且其**默认值本身就是真实模型**
        #     （deepseek:deepseek-v4-flash）
        # 此前只在 DEFAULT_MODEL 为空时填假值，于是 .env 一旦显式配了这两个字段，
        # USE_FAKE_MODEL=true 就形同虚设：
        #   本地（有 key）→ 测试真的调用线上模型（检索链温度 0.3，基线不可复现且产生费用）
        #   CI（无 key）  → openai.OpenAIError: Missing credentials
        # 实测后者让 40 条检索门禁 query 里的 6 条直接崩溃。
        if self.USE_FAKE_MODEL:
            fake_ref = make_model_ref(Gateway.FAKE, GATEWAY_DEFAULT_MODEL[Gateway.FAKE])
            self.DEFAULT_MODEL = fake_ref
            self.LLM_MODEL = fake_ref

        if self.DEFAULT_MODEL:
            self._validate_model_ref(self.DEFAULT_MODEL, field="DEFAULT_MODEL", active=active)

        for gateway in active:
            self.AVAILABLE_MODELS |= model_refs_for(gateway)
            if not self.DEFAULT_MODEL:
                self.DEFAULT_MODEL = make_model_ref(gateway, GATEWAY_DEFAULT_MODEL[gateway])

        if self.DEFAULT_MODEL:
            self.AVAILABLE_MODELS.add(self.DEFAULT_MODEL)

        self._validate_model_ref(self.LLM_MODEL, field="LLM_MODEL", active=active)

    def _validate_model_ref(self, model_ref: str, *, field: str, active: list[Gateway]) -> None:
        """校验模型引用：可解析、网关已启用、model_id 在该网关清单内。"""
        try:
            gateway, model_id = parse_model_ref(model_ref)
        except ValueError as exc:
            raise ValueError(f"{field}={model_ref!r} 无效：{exc}") from exc
        if gateway not in active:
            raise ValueError(
                f"{field}={model_ref!r} 需要网关 {gateway}，但该网关未启用"
                f"（请配置对应 API key，或改用已启用网关上的模型）"
            )
        if model_id not in GATEWAY_MODELS[gateway]:
            raise ValueError(
                f"{field}={model_ref!r} 中的 model_id {model_id!r} 不在网关 {gateway} 的清单中；"
                f"可用: {sorted(GATEWAY_MODELS[gateway])}"
            )

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
settings.SQLITE_DB_PATH = _resolve_project_path(settings.SQLITE_DB_PATH)
settings.SQLITE_STORE_PATH = _resolve_project_path(settings.SQLITE_STORE_PATH)
