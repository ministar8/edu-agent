# EDU-Agent · 408 考研智能教学辅导多 Agent 系统

基于 **LangGraph v1.0 + FastAPI + RAG** 的 408 考研辅导系统，支持知识问答、智能出题与答案批改。
工程骨架对齐 [agent-service-toolkit](https://github.com/JoshuaC215/agent-service-toolkit)。

## 架构

```text
用户提问 → Supervisor（create_supervisor 路由）
  ├─ knowledge_agent   知识讲解（RAG 检索）
  ├─ question_agent    出题（题库模板检索）
  └─ grading_agent     批改（标准答案检索）
        │
   RAG 检索管线: 查询归一 → 分类 → 多路召回(语义 + BM25 + 元数据 + 同义词)
                 → RRF 融合 → Reranker → HyDE → 语义缓存
```

**存储**：ChromaDB（向量检索 + 语义缓存）｜SQLite（用户 `edu_agent.db` + LangGraph checkpointer `checkpoints.db`）

**流式**：`/stream` 同时输出 token 流与 message 流（对齐 agent-service-toolkit）。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | 纯静态 HTML + CSS + JavaScript（无框架无构建） |
| 后端 | FastAPI + Uvicorn + Pydantic v2 |
| Agent | LangChain 1.x `create_agent` + LangGraph `create_supervisor` + checkpointer |
| RAG | ChromaDB + bge-m3(TEI) + BM25 + RRF + bge-reranker-v2-m3(TEI) + HyDE + 语义缓存 |
| LLM | DashScope / DeepSeek（OpenAI 兼容接口） |
| 依赖管理 | uv + pyproject.toml |
| 质量 | ruff + pyrefly + pytest + pre-commit + GitHub Actions |

## 项目结构

```text
edu-agent/
├── pyproject.toml        # uv 依赖 + ruff/pyrefly/pytest 配置
├── langgraph.json        # LangGraph Studio 配置
├── compose.yaml          # Docker 部署
├── src/
│   ├── agents/           # 多 Agent（supervisor + 3 专业 agent + 共享 RAG 工具）
│   ├── rag/              # RAG 检索（retriever/fusion/reranker/hyde/cache/ingest）
│   ├── core/             # Settings + LLM 工厂（get_model / get_llm）
│   ├── schema/           # Pydantic 协议模型
│   ├── memory/           # LangGraph checkpointer（SQLite）
│   ├── db/               # SQLAlchemy User 表
│   ├── service/          # FastAPI（service / auth / threads / utils）
│   ├── tools/            # 离线数据清洗工具
│   └── run_service.py    # 服务入口
├── static/               # 静态前端（login.html / index.html / app.js / style.css）
├── tests/                # pytest 测试
├── knowledge/            # 408 知识库（四科讲义 + 题库 + 学习路线）
├── docker/               # Dockerfile
└── scripts/              # 运维脚本（TEI 部署）
```

## 快速开始

### 1. 安装依赖

```bash
uv sync                       # 创建 .venv 并安装依赖
```

### 2. 配置

```bash
cp .env.example .env          # 必填：LLM_API_KEY、JWT_SECRET
```

### 3. 启动外部服务（Embedding / Reranker）

```bash
# Embedding (bge-m3)
docker run -d --name tei-embedding --gpus all -p 11435:80 \
  ghcr.io/huggingface/text-embeddings-inference:latest \
  --model-id BAAI/bge-m3 --dtype float16 --pooling mean

# Reranker (bge-reranker-v2-m3)
docker run -d --name tei-reranker --gpus all -p 8080:80 \
  ghcr.io/huggingface/text-embeddings-inference:latest \
  --model-id BAAI/bge-reranker-v2-m3 --dtype float16 --pooling cls
```

Windows 也可用 `scripts/tei_deploy.ps1`。

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
| GET | `/api/info` | 可用 agent 与模型 |
| POST | `/api/invoke` | 单次问答（非流式） |
| POST | `/api/stream` | 流式问答（SSE：token + message 双流） |
| POST | `/api/history` | 会话历史 |
| GET | `/api/threads` | 会话线程列表 |
| POST | `/api/questions/generate` | 出题，返回**结构化题目**（题干 / 标准答案 / 解析分开） |
| POST | `/api/questions/grade` | 批改，需传**单题**的题干 + 该题标准答案 |
| GET | `/health` | 健康检查（含各外部依赖状态） |

## 测试与质量

```bash
uv run pytest                  # 运行测试
uv run ruff check src/ tests/  # Lint
uv run ruff format src/        # 格式化
uv run pyrefly check           # 类型检查
pre-commit install             # 安装 git 钩子
```

## Docker

```bash
docker compose up --build      # 构建并启动 agent_service
```

## LangGraph Studio

```bash
langgraph dev                  # 打开 Studio 调试 agent 图
```
