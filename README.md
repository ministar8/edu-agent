# EDU-Agent · 408 考研智能教学辅导多 Agent 系统

基于 **LangGraph v1.0 + FastAPI + RAG** 的 408 考研辅导系统，支持知识问答、智能出题与答案批改。
工程骨架对齐 [agent-service-toolkit](https://github.com/JoshuaC215/agent-service-toolkit)。

## 架构

```text
用户提问 → teaching_graph（工作记忆 → 消息窗口裁剪）
              └─ supervisor（create_supervisor 路由）
                    ├─ knowledge_agent   知识讲解（RAG 检索）
                    ├─ question_agent    出题（结构化真源 + 对话修饰）
                    └─ grading_agent     批改（结构化打分 + 对话修饰）

RAG 检索管线: 查询归一 → 分类 → 多路召回(语义 + BM25 + 元数据 + 同义词)
              → RRF 融合 → Reranker → HyDE → 语义缓存
```

**存储**：ChromaDB（向量 + 语义缓存）｜SQLite：用户 `edu_agent.db`、会话 `checkpoints.db`、长期记忆 `store.db`

**流式**：`/stream` 输出 token + message 双流，并支持 custom 事件。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | 纯静态 HTML + CSS + JavaScript（无框架无构建） |
| 后端 | FastAPI + Uvicorn + Pydantic v2 |
| Agent | LangChain 1.x `create_agent` + LangGraph `create_supervisor` + 运行时模型覆盖中间件 |
| RAG | ChromaDB + bge-m3(TEI) + BM25 + RRF + bge-reranker-v2-m3(TEI) + HyDE + 语义缓存 |
| 记忆 | 短期 checkpointer + 消息窗口；长期 Store（画像 / episodes / weak_topics / 向量检索） |
| 评测 | RAGAS Layer-1（faithfulness / context_precision / context_recall / answer_relevancy） |
| LLM | DashScope / DeepSeek（OpenAI 兼容接口） |
| 依赖管理 | uv + pyproject.toml |
| 质量 | ruff + pyrefly + pre-commit（提交前钩子）+ 检索质量门禁（三路由比基线） |

## 项目结构

```text
edu-agent/
├── pyproject.toml        # uv 依赖 + ruff/pyrefly/pytest 配置
├── langgraph.json        # LangGraph Studio 入口（teaching_graph）
├── compose.yaml          # Docker 部署（Dockerfile 见 docker/）
├── src/
│   ├── agents/           # 编排与业务图：supervisor / teaching_graph / factory / tools / *_core
│   ├── rag/              # 检索流水线（retriever / fusion / reranker / hyde / cache / ingest）
│   ├── core/             # Settings + LLM 工厂（get_model / get_llm）
│   ├── prompts/          # 系统提示词与模板（import 期校验 + PROMPT_SET_VERSION）
│   ├── schema/           # 协议/领域模型（questions / grading / evidence / auth …）
│   ├── memory/           # 短期窗口 + 长期 Store 业务封装
│   ├── evaluation/       # 评测：RAGAS（dataset / adapters / ragas_eval / cli）
│   │                     #      + 检索质量门禁（retrieval_gate，三路由比基线）
│   ├── db/               # SQLAlchemy User 表
│   ├── service/          # FastAPI（service / auth / threads / errors / health）
│   ├── tools/            # 离线数据清洗（ingest 使用，不参与运行时问答）
│   └── run_service.py    # 服务入口
├── static/               # 静态前端（login.html / index.html / app.js / api.js / auth.js / theme.js / style.css）
├── evals/                # 评测样本（sample_408.jsonl）+ 三份检索基线（retrieval_baseline*.json）
├── data/                 # 运行时指标输出（gitignore）
├── knowledge/            # 408 知识库（四科讲义 + 题库 + 学习路线）
├── docker/               # Dockerfile.service
├── scripts/              # tei_deploy.ps1（本机 TEI 容器部署）
└── docs/                 # 工程文档（ARCHITECTURE / RETRIEVAL_ROADMAP / DOCKER / ENGINEERING_COMPARISON）
```

### 评测与门禁入口

| 入口 | 用途 |
|---|---|
| `PYTHONPATH=src uv run python -m evaluation.cli` | RAGAS 评测（faithfulness / context_precision / context_recall / answer_relevancy） |
| `PYTHONPATH=src uv run python -m evaluation.retrieval_gate` | 检索质量门禁：**九项指标**对基线（含章级 `kp_hit@k` / `kp_mrr`），**每条路由各一份基线** |
| `scripts/tei_deploy.ps1` | 本机 TEI 容器部署（embedding + reranker） |

> 检索门的真实口径按 `(embedding, rerank)` 组合区分：默认（假 embedding / 重排 `off`）、
> `GATE_RERANK_MODE=on`（假重排）、`GATE_RERANK_MODE=disabled`（**要求重排但部署关掉**
> —— 生产 `RERANK_ENABLED=false` 的实际口径）、`GATE_USE_REAL_EMBEDDING=1`（真实 TEI，
> **只有这条能回答语义质量问题**）。未登记的组合与跨口径比对都会被拒绝（退出码 2）。
> `GATE_USE_RERANK=1` 是 `GATE_RERANK_MODE=on` 的兼容别名。细节见 `docs/ARCHITECTURE.md`。

## 快速开始

### 1. 安装依赖

```bash
uv sync                       # 创建 .venv 并安装依赖
uv sync --group eval          # 可选：RAGAS 评测依赖
```

### 2. 配置

```bash
cp .env.example .env          # 必填：DASHSCOPE_API_KEY 或 DEEPSEEK_API_KEY、JWT_SECRET
```

### 3. 启动外部服务（Embedding / Reranker）

```bash
# Embedding (bge-m3) → 端口 11435
docker run -d --name tei-embedding --gpus all -p 11435:80 \
  ghcr.io/huggingface/text-embeddings-inference:89-1.7 \
  --model-id BAAI/bge-m3 --dtype float16 --pooling mean

# Reranker (bge-reranker-v2-m3) → 端口 11436
docker run -d --name tei-reranker --gpus all -p 11436:80 \
  ghcr.io/huggingface/text-embeddings-inference:89-1.7 \
  --model-id BAAI/bge-reranker-v2-m3 --dtype float16 --pooling cls
```

Windows 下推荐用 `scripts/tei_deploy.ps1`（容器已存在时用 `docker start`，勿 `docker run` 重建）。

> 启动后模型加载约需 50 秒。**校验请用真实推理请求**，`/health` 返回 200 不代表模型已就绪。
> 端口须与 `.env` 的 `EMBEDDING_API_BASE` / `RERANK_LOCAL_URL` 一致（默认 11435 / 11436）。

### 4. 构建知识库

```bash
uv run python -m rag.ingest            # 增量入库
uv run python -m rag.ingest --rebuild  # 全量重建
```

> 需 `PYTHONPATH=src` 或在 `src/` 目录下运行。

### 5. 启动服务

```bash
uv run python src/run_service.py       # http://127.0.0.1:8000
```

浏览器访问 `http://127.0.0.1:8000/`（静态前端由 FastAPI 提供服务）。

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/register` `/login` `/logout` | 注册 / 登录（JWT）/ 退出 |
| GET | `/api/auth/me` | 当前用户 |
| GET | `/api/info` | 可用 agent 与模型（**需登录**） |
| POST | `/api/invoke` 或 `/api/{agent_id}/invoke` | 单次问答（非流式） |
| POST | `/api/stream` 或 `/api/{agent_id}/stream` | 流式问答（SSE：token + message） |
| POST | `/api/history` 或 `/api/{agent_id}/history` | 会话历史 |
| GET | `/api/threads` 或 `/api/{agent_id}/threads` | 会话线程列表 |
| POST | `/api/questions/generate` | 结构化出题（题干 / 标准答案 / 解析分字段） |
| POST | `/api/questions/grade` | 单题批改（题干 + 学生作答 + 可选标准答案） |
| GET | `/health` | 健康检查（外部依赖状态） |

请求体可选 `model`：形如 `dashscope:qwen3.8-max` / `deepseek:deepseek-v4-flash`，经运行时中间件生效。

## RAGAS 评测

```bash
uv sync --group eval
# 需 TEI embedding + 知识库 + LLM 配置
PYTHONPATH=src uv run python -m evaluation.cli --dataset evals/sample_408.jsonl --limit 40
```

报告输出到 `evals/results/ragas_*.json`。

## 代码质量

```bash
uv run ruff check src/         # Lint
uv run ruff format src/        # 格式化
uv run pyrefly check           # 类型检查（须 0 错误）
pre-commit install             # 安装 git 钩子（一次性；此后每次 commit 自动跑）
```

钩子包含：YAML 校验、文件尾换行、行尾空白、ruff（`--fix`）、ruff-format、pyrefly。
`evals/` 为门禁基线输入，已豁免空白类改写。

> 说明：本工作区不含测试套件与 CI，有效检查范围是 `src/`。移出的内容见
> `../edu-agent-engineering-archive/ARCHIVE_INDEX.md`（含清单与取回方式）。

## Docker

```bash
docker compose up --build      # 构建并启动 agent_service（http://127.0.0.1:8000）
```

镜像用 `uv sync --frozen --no-dev` 安装依赖，只 COPY `src/` `static/` `knowledge/`。
`chroma_db` 与 SQLite 库通过 volume 挂载，不打进镜像。

开发热同步：`docker compose watch`。

> 完整说明（构建要点、卷挂载、容器访问宿主 TEI 的地址问题、常见问题排查）见
> **[docs/DOCKER.md](docs/DOCKER.md)**。

## LangGraph Studio

```bash
langgraph dev                  # 打开 Studio 调试 agent 图（teaching_graph）
```
