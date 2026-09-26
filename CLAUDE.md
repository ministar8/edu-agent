# CLAUDE.md

本文件为 Claude Code / 贡献者提供本仓库的工作指引。

## 项目定位

**EDU-Agent** —— 408 考研智能教学辅导多 Agent 系统。基于 LangGraph + FastAPI + RAG，
支持知识问答、智能出题与答案批改。工程骨架对齐 [agent-service-toolkit](https://github.com/JoshuaC215/agent-service-toolkit)。

## 架构

```
用户提问 → Supervisor（langgraph-supervisor create_supervisor 路由）
  ├─ knowledge_agent   知识讲解（RAG 检索）
  ├─ question_agent    出题（结构化真源 + 对话修饰）
  └─ grading_agent     批改（结构化打分 + 对话修饰）
        │
   RAG 检索管线：查询归一 → 分类 → 多路召回(语义 + BM25 + 元数据 + 同义词)
                 → RRF 融合 → Reranker → HyDE → 语义缓存
```

**存储**：ChromaDB（向量检索 + 语义缓存）｜SQLite（用户 `edu_agent.db` + 会话 `checkpoints.db` + 长期记忆 `store.db`）

## 目录职责

| 路径 | 职责 |
|---|---|
| `src/agents/` | `supervisor.py` + 专业 agent（`factory.build_agent`）+ `tools.py` + 出题/批改真源 `*_core.py` + `temperature.py` |
| `src/rag/` | 检索流水线：`retriever.py`（门面）、`postprocess.py`（RRF）、`fusion.py`（证据融合）、`reranker.py`、`hyde.py`、`semantic_cache.py`、`ingest.py` |
| `src/core/` | `settings.py`（配置单例）、`llm.py`（`get_model` / `get_llm` 工厂） |
| `src/prompts/` | 提示词集中管理（agents 的 system prompt / supervisor 分派 / rag 单轮模板 / service 出题批改模板），import 期校验变量与花括号 |
| `src/service/` | FastAPI：`service.py`（路由 + SSE）、`auth.py`（JWT）、`threads.py`（会话列表）、`utils.py` |
| `src/schema/` | Pydantic 协议/领域模型（`schema.py` / `models.py` / `auth.py` / `questions.py` / `grading.py` / `evidence.py` 检索对外契约）；`rag/schemas.py` 只放检索链内部 LLM 输出 |
| `src/memory/` | 短期 checkpointer + 消息窗口 `window.trim_conversation` + 长期 Store（工厂/schema/topic/weak_topics/记忆卡） |
| `src/db/` | SQLAlchemy User 表与建表逻辑 |
| `src/tools/` | 离线数据清洗工具（**不参与运行时**） |
| `static/` | 静态前端（login.html / index.html / app.js / api.js / auth.js / theme.js / style.css） |
| `knowledge/` | 408 知识库（四科讲义 + 题库 + 学习路线） |
| `src/evaluation/` | 评测：RAGAS Layer-1（dataset/adapters/ragas_eval/cli）+ 检索质量门禁（retrieval_gate）+ `evals/` 样本 |
| `docs/` | **工程文档**（见 `docs/README.md` 索引）。现行：`ARCHITECTURE.md` 架构 / `DOCKER.md` 容器 + TEI 端点契约 / **`RETRIEVAL_PLAN.md` 当前执行方案** / `RETRIEVAL_ROADMAP.md` 路线与**「不做清单」** / `L1L2L3_RETRIEVAL_REVIEW.md` 分级评审 / `RERANK_SWITCH_ANALYSIS.md` 重排开关分析。历史版本在 `docs/archive/` |

## 常用命令

```bash
uv sync                                  # 安装依赖
uv sync --group eval                     # RAGAS 评测依赖（可选）
PYTHONPATH=src uv run python -m evaluation.cli --dataset evals/sample_408.jsonl --limit 5
uv run python src/run_service.py         # 启动服务 → http://127.0.0.1:8000
uv run python -m rag.ingest              # 知识库增量入库
uv run python -m rag.ingest --rebuild    # 知识库全量重建

uv run ruff check src/                   # Lint
uv run ruff format src/                  # 格式化
uv run pyrefly check                     # 类型检查
langgraph dev                            # LangGraph Studio 调试

docker compose up --build                # 容器化启动
```

## 开发约定

- **配置一律走 `core.settings.settings` 单例**，不要散落读 `os.environ`。新增配置项加到 `Settings` 并同步 `.env.example`。
- **LLM 只通过工厂获取**：agent 层用 `get_model(model_ref, temperature)`（网关+模型+温度缓存），
  RAG 层用 `get_llm(streaming, temperature)`（按 `settings.LLM_MODEL` 取）。
- **模型标识 = `<gateway>:<model_id>`**，如 `dashscope:qwen3.8-max`、`deepseek:deepseek-v4-flash`。
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
- **规模红线**：单文件 ≤600 行、单函数 ≤60 行（人工遵守，本工作区无自动门禁）。
- 关键逻辑与复杂函数写中文注释。

## 工作区边界

本仓库是**运行时 + 论文核心**的裁剪版：

- **不含**测试套件、CI 工作流、代码覆盖率与结构规模棘轮门禁 —— 已移出到
  `../edu-agent-engineering-archive/`（其 `ARCHIVE_INDEX.md` 记录清单与取回方式）。
- **保留**的自研门禁：`evaluation.retrieval_gate`（检索质量）与 `pre-commit`（ruff / pyrefly / 空白检查）。
- 源码中的质量约束靠**人工遵守**，本工作区没有 CI 强制。

## 注意事项

- 检索依赖两个本地 TEI 服务：Embedding（`localhost:11435`）与 Reranker（`localhost:11436`），
  用 `scripts/tei_deploy.ps1` 或 README 中的 docker 命令启动，否则检索类请求会失败。
- **假 embedding 模式**：`pyproject.toml` 的 `[tool.pytest_env]` 设 `USE_FAKE_EMBEDDING=true` 后，
  `get_embeddings()` 返回本地确定性哈希实现（`rag.embeddings.HashingEmbeddings`）——
  **检索质量门禁靠它在无 TEI 时做确定性比对**。该实现**只保留词汇重叠信号、
  没有语义泛化能力，严禁用于生产**。
  注意：`semantic_cache._DATA_DIR` / `_JSONL_FILE` 是**模块级常量（import 期固化）**，
  临时重定向须用 `monkeypatch` 指向临时目录，否则会写坏真实的 `chroma_db/semantic_cache/`。
- Windows 下 `run_service.py` 会把事件循环切到 `WindowsSelectorEventLoopPolicy`（异步 DB 驱动不兼容 Proactor）。
- `src/rag/` 与 `src/tools/` 的类型注解尚不严格，`pyproject.toml` 中对这两个目录放宽了 pyrefly 检查（技术债）。
- **`splitter.py` 的 Q&A 原子机制在真实语料上未激活**（已知缺陷，勿误判为"已实现"）：
  `_ANSWER_RE` 只识别 `答案：/解答：/正确答案：`，而 408 真题用的是「选项行尾 `✅` + `**解析**：`」，
  因此 `content_type` 永远不会成为 `merged_qa`，`qa.question/answer/answer_key` 字段恒为空，
  依赖它的 `recall.py` `merged_qa_meta` 路由已按 backlog #8 删除。
- **检索质量门禁**：改动检索链（阈值、RRF 权重、切分策略、去重、集合路由）后，必须跑
  `PYTHONPATH=src uv run python -m evaluation.retrieval_gate`。
  它用确定性哈希 embedding + 临时索引跑 40 条黄金集 query，与 `evals/retrieval_baseline.json`
  对比，任一指标退化即失败。**它衡量的是检索管线是否退化，不是语义质量**（语义质量用
  `evals/cli.py` 的 RAGAS）。改动导致指标变化时，用 `--update-baseline` 重录，
  但**必须在 PR 里说明为什么这个变化是可接受的**。
- **门禁里的索引就绪屏障**：ChromaDB `add_documents` 之后立即查询会**间歇性**抛
  `Error creating hnsw segment reader: Nothing found on disk` —— 每次命中的集合不同，
  命中后该集合整轮不可查询（检索结果全错但不报错），会被误报成"检索退化"。
  在临时索引上跑检索前，务必先调 `evaluation.retrieval_gate.wait_for_index_ready()`
  （`repair=True` 会对不可查询的集合只重建它自己后重试）。
- **这个故障进程内无法恢复**（实测结论，别再试了）：丢弃 `_stores` 缓存句柄无效、
  重开 `chromadb.PersistentClient` 无效，**只有 `delete_collection` + 重新入库有效**。
  `VectorStoreManager.wait_until_ready` 因此是**检测器而非修复器** ——
  它把静默错误变成入库期显式失败，并在错误信息里给出补救命令。
  生产路径不要自动重建（删集合 = 真实数据丢失），必须人工确认。
