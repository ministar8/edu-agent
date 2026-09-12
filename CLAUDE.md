# CLAUDE.md

本文件为 Claude Code / 贡献者提供本仓库的工作指引。

## 项目定位

**EDU-Agent** —— 408 考研智能教学辅导多 Agent 系统。基于 LangGraph + FastAPI + RAG，
支持知识问答、智能出题与答案批改。工程骨架对齐 [agent-service-toolkit](https://github.com/JoshuaC215/agent-service-toolkit)。

## 架构

```
用户提问 → Supervisor（langgraph-supervisor create_supervisor 路由）
  ├─ knowledge_agent   知识讲解（RAG 检索）
  ├─ question_agent    出题（题库模板检索）
  └─ grading_agent     批改（标准答案检索）
        │
   RAG 检索管线：查询归一 → 分类 → 多路召回(语义 + BM25 + 元数据 + 同义词)
                 → RRF 融合 → Reranker → HyDE → 语义缓存
```

**存储**：ChromaDB（向量检索 + 语义缓存）｜SQLite（用户 `edu_agent.db` + LangGraph checkpointer `checkpoints.db`）

## 目录职责

| 路径 | 职责 |
|---|---|
| `src/agents/` | `supervisor.py` + 专业 agent（`factory.build_agent`）+ `tools.py` + 出题/批改真源 `*_core.py` + `temperature.py` |
| `src/rag/` | 检索流水线：`retriever.py`（门面）、`postprocess.py`（RRF）、`fusion.py`（证据融合）、`reranker.py`、`hyde.py`、`semantic_cache.py`、`ingest.py` |
| `src/core/` | `settings.py`（配置单例）、`llm.py`（`get_model` / `get_llm` 工厂） |
| `src/service/` | FastAPI：`service.py`（路由 + SSE）、`auth.py`（JWT）、`threads.py`（会话列表）、`utils.py` |
| `src/client/` | `AgentClient` SDK：路径根为 `/api`，JWT 登录/注入，invoke/stream/history/threads/出题批改 |
| `src/schema/` | Pydantic 协议/领域模型（`schema.py` / `models.py` / `auth.py` / `questions.py` / `grading.py` / `evidence.py` 检索对外契约）；`rag/schemas.py` 只放检索链内部 LLM 输出 |
| `src/memory/` | 短期 checkpointer + 消息窗口 `window.trim_conversation` + 长期 Store（工厂/schema/topic/weak_topics/记忆卡） |
| `src/db/` | SQLAlchemy User 表与建表逻辑 |
| `src/tools/` | 离线数据清洗工具（**不参与运行时**） |
| `static/` | 静态前端（login.html / index.html / app.js / auth.js / style.css） |
| `knowledge/` | 408 知识库（四科讲义 + 题库 + 学习路线） |

## 常用命令

```bash
uv sync                                  # 安装依赖
uv run python src/run_service.py         # 启动服务 → http://127.0.0.1:8000
uv run python -m rag.ingest              # 知识库增量入库
uv run python -m rag.ingest --rebuild    # 知识库全量重建

uv run pytest                            # 测试
uv run ruff check src/ tests/            # Lint
uv run ruff format src/                  # 格式化
uv run pyrefly check                     # 类型检查
langgraph dev                            # LangGraph Studio 调试

docker compose up --build                # 容器化启动
```

## 开发约定

- **配置一律走 `core.settings.settings` 单例**，不要散落读 `os.environ`。新增配置项加到 `Settings` 并同步 `.env.example`。
- **LLM 只通过工厂获取**：agent 层用 `get_model(model_name, temperature)`（按枚举名 + 温度缓存），
  RAG 层用 `get_llm(streaming, temperature, use_fast)`（按 `settings.LLM_MODEL` 取）。
- **模型标识 = `<gateway>:<model_id>`**，如 `dashscope:qwen3.7-max`、`deepseek:deepseek-v4-flash`。
  **网关**（走哪家：决定 base_url + api_key）与**模型 ID**（哪个模型）是两个概念，
  同一模型 ID 可显式选择走不同网关（如 `dashscope:deepseek-v4-flash`），**不按模型名猜**。
  配了哪个网关的 key 就启用哪个网关；模型清单与各网关提供的模型见 `schema/models.py`
  的 `GATEWAY_MODELS`。相关入口：`settings.gateway_for` / `api_base_for_model` / `api_key_for_model`。
- **注册新 agent 需同步三处**：`src/agents/agents.py` 的 import、`agents` 字典条目、`langgraph.json` 的 `graphs`。
  注册后可通过 `/api/{agent_id}/invoke|stream|history|threads` 直接寻址；未知 agent 返回 404。
- **密钥字段用 `SecretStr`**，取值需 `.get_secret_value()`。
- **LangSmith 追踪**：`LANGCHAIN_*` 由 `Settings.export_langsmith_env()` 在 lifespan 中写入
  `os.environ`（LangChain 只从进程环境读取并自动埋点，放 Settings 里无效）。
  开追踪只需在 `.env` 设 `LANGCHAIN_TRACING_V2=true` 与 `LANGCHAIN_API_KEY`，不需要改代码。
- 关键逻辑与复杂函数写中文注释。

## 注意事项

- 检索依赖两个本地 TEI 服务：Embedding（`localhost:11435`）与 Reranker（`localhost:8080`），
  用 `scripts/tei_deploy.ps1` 或 README 中的 docker 命令启动，否则检索类请求会失败。
- Windows 下 `run_service.py` 会把事件循环切到 `WindowsSelectorEventLoopPolicy`（异步 DB 驱动不兼容 Proactor）。
- `src/rag/` 与 `src/tools/` 的类型注解尚不严格，`pyproject.toml` 中对这两个目录放宽了 pyrefly 检查（技术债）。
