# 智能教学辅导多Agent系统

基于 LangChain + LangGraph 的多智能体协作教学辅导系统，面向 408 计算机考研课程，集成 RAG 检索增强生成与知识图谱，支持可视化展示 Agent 协作过程。

## 系统架构

```
用户提问 → Supervisor(查询分类 + 检索深度路由)
  ├─ L1 快速: 直接检索 + fast LLM → 治理          (2-7s, 缓存命中 ~800ms)
  ├─ L2 标准: 预检索 + LLM → 多级降级 fallback     (50-120s)
  └─ L3 深度: deep检索(KG+HyDE) + LLM → fallback (60-180s)
       │
  knowledge_agent / question_agent / grading_agent / path_agent
       │
  三阶段治理: 前置守卫(防幻觉) → 回答生成 → 后治理(来源校验/反思重试)
```

**RAG 检索管线**: 查询 → 分类 → 集合路由(跨4科) → 5路并行召回(语义+BM25+元数据+同义词+KG) → RRF融合 → Reranker → 语义缓存(≥0.92复用)

**存储**: ChromaDB(4科+题库, HNSW M=32) | Neo4j(知识图谱) | SQLite(用户/对话, PBKDF2认证)

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 14 + React 18 + @xyflow/react + TailwindCSS |
| 后端 | FastAPI + Pydantic Settings + Uvicorn |
| Agent | LangChain + LangGraph (StateGraph + Command) |
| RAG | ChromaDB + bge-m3 + 5路并行召回 + Reranker + 语义缓存 |
| 知识图谱 | Neo4j + Cypher |
| LLM | Qwen / DeepSeek / GLM (OpenAI 兼容接口) |
| 嵌入 | bge-m3 (1024-dim, 本地 TEI) |
| 重排序 | bge-reranker-v2-m3 (本地 TEI) |

## 项目结构

```
毕业设计/
├── .env.example          # 环境变量模板
├── knowledge/            # 知识库 Markdown（4科+题库）
├── chroma_db/            # ChromaDB 向量数据库（4科+题库，HNSW M=32）
├── edu_agent.db          # SQLite 用户/对话数据库
├── docs/                 # 论文素材
├── backend/
│   ├── app/
│   │   ├── api/          # REST API（chat/auth/knowledge/questions/tracking/visualization）
│   │   ├── agents/       # 多Agent编排（supervisor + 4专业agent + 治理/守卫/反思）
│   │   ├── rag/          # RAG 管线（retriever/fusion/reranker/verifier/hyde/cache/KG/嵌入/入库）
│   │   ├── evaluation/   # RAGAS 评估 + 诊断
│   │   ├── db/           # SQLAlchemy ORM + 会话管理
│   │   ├── schemas/      # Pydantic 请求/响应模型
│   │   ├── services/     # 认证 + 知识追踪 + 一致性检查
│   │   ├── tools/        # 离线工具（去重/规范化/异常检测/缺失值填充）
│   │   ├── main.py       # FastAPI 入口
│   │   └── config.py     # Pydantic Settings 配置
│   ├── data/             # 评估数据集 + 结果（.gitignore）
│   └── requirements.txt  # Python 依赖
└── frontend/             # Next.js 前端
    └── src/              # App Router + 组件(chat/questions/knowledge/KG/RAG/tracking)
```

## 快速启动

### 1. 环境配置

```bash
cp .env.example .env            # 必填：LLM_API_KEY、JWT_SECRET
conda create -n edu-agent python=3.12 && conda activate edu-agent
pip install -r backend/requirements.txt
cd frontend && npm install
docker run -d --name tei-embedding --gpus all -p 11435:80 ghcr.io/huggingface/text-embeddings-inference:latest --model-id BAAI/bge-m3 --dtype float16 --pooling mean  # 启动 TEI Embedding 服务
```

### 2. 启动服务

```bash
# 终端1：TEI Embedding + Reranker（Docker）
docker start tei-embedding tei-reranker  # 或 docker compose up -d

# 终端2：Neo4j（知识图谱，可选）
neo4j console

# 终端3：后端
# ChromaDB 使用嵌入式 PersistentClient，无需单独启动服务
cd backend && python -m app.main     # http://127.0.0.1:8000

# 终端4：前端
cd frontend && npm run dev           # http://localhost:3000
```

> **ChromaDB**：默认使用嵌入式 `PersistentClient`（数据存 `./chroma_db/`），无需单独启动。如需更高并发，可切换为 HTTP 模式：
> ```bash
> pip install chromadb[server]
> chroma run --host 127.0.0.1 --port 8100 --path ./chroma_db
> # 然后在 .env 中设置 CHROMA_HOST=127.0.0.1 CHROMA_PORT=8100
> ```
>
> **Neo4j**：不启动时系统自动跳过知识图谱功能，其余功能正常运行。知识库入库时加 `--no-graph` 跳过图谱构建。

### 3. 构建知识库

```bash
cd backend
python -m app.rag.ingest             # 增量入库
python -m app.rag.ingest --rebuild   # 全量重建
python -m app.rag.ingest --no-graph  # 跳过图谱构建（Neo4j未启动时推荐）
```

## 环境变量

完整配置见 `.env.example`。核心变量：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| LLM_API_KEY | LLM API 密钥（**必填**） | — |
| LLM_API_BASE | LLM API 地址 | DashScope 兼容接口 |
| LLM_MODEL | LLM 主模型名 | qwen3.7-max-preview |
| EMBEDDING_API_BASE | Embedding API 地址 | http://localhost:11435 |
| EMBEDDING_MODEL | Embedding 模型名 | BAAI/bge-m3 |
| RERANK_LOCAL_URL | 本地 TEI Reranker 地址 | http://localhost:8080 |
| HYDE_ENABLED | HyDE 假设文档嵌入开关 | true |
| RERANK_ABSOLUTE_MIN_SCORE | Rerank 绝对最低分数 | 0.1 |
| SEMANTIC_CACHE_ENABLED | 语义缓存开关 | true |
| NEO4J_URI / NEO4J_PASSWORD | Neo4j 连接 | bolt://localhost:7687 |
| JWT_SECRET | JWT 签名密钥（**必填**） | — |

LLM 和 Embedding 均使用 OpenAI 兼容接口，更换服务商只需修改 `LLM_API_BASE` 和 `LLM_MODEL`。

## 评估

```bash
python run_full_eval.py              # 完整评估（RAGAS 4指标）
python run_full_eval.py --quick      # 快速验证 (10条)
python run_ablation.py --quick       # 消融实验 (5组条件)
```

## 性能优化

| 优化项 | 效果 |
|--------|------|
| L1/L2/L3 检索策略分层 | 简单查询 2-7s，复杂查询 60-120s |
| 简单问答绕过 LangGraph | 省去 Agent 编排开销 |
| 语义缓存 (ChromaDB) | 冷启动 3-5s → 缓存命中 ~800ms (2.7-4.4x) |
| HyDE 按需触发 | 避免不必要的 LLM 调用 |
| Fast LLM 模型 | 简单问答生成延迟降低 30-50% |
| Chroma 读写锁 (RWLock) | 8路并行召回读查询真正并发，检索延迟 -30~50% |
| Negative Sampling 软降级 | Window 噪声 chunk 排到末尾，Context Precision +0.08~0.15 |
| L2/L3 no-rerank 降级 | TIMEOUT 率 15% → 0% |
| Agent 检索查询提取 | COV_FAIL → 100% 覆盖 |

## 量化数据

- Golden Set 通过率: 88/88 (100%)，4科全覆盖
- 知识图谱: 4科全覆盖 (数据结构 / 操作系统 / 计算机网络 / 计算机组成原理)
- 向量库: 3240 区块 (4科+题库+学习路线+代码实现+跨学科对比)，HNSW M=32
- 语义缓存: 相似度阈值 0.88，TTL 30min，容量 500，命中率 ~90%
- Negative Sampling: window 噪声覆盖率 <15% 软降级(×0.5)，对比查询豁免
