# 智能教学辅导多Agent系统

基于 LangChain + LangGraph 的多智能体协作教学辅导系统，面向 **408 计算机考研** 课程，集成 RAG 检索增强生成与知识图谱，支持可视化展示 Agent 协作过程。

## 系统架构

```
┌──────────────────────────────────────────────────────────┐
│                前端可视化层 (Next.js + React)               │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐   │
│  │ 智能问答  │  │ Agent协作 │  │ 知识库管理            │   │
│  │          │  │ 流程图    │  │ + RAG过程 + 图谱      │   │
│  └──────────┘  └──────────┘  └──────────────────────┘   │
└────────────────────────┬─────────────────────────────────┘
                         │ REST API (CORS)
┌────────────────────────┴─────────────────────────────────┐
│                后端服务层 (FastAPI)                          │
│  ┌────────────────────────────────────────────────────┐   │
│  │          多Agent编排引擎 (LangGraph)                  │   │
│  │  Supervisor → 知识检索 / 出题 / 批改 / 推荐 + 回答治理  │   │
│  └────────────────────────────────────────────────────┘   │
└────────────────────────┬─────────────────────────────────┘
                         │
┌────────────────────────┴─────────────────────────────────┐
│  ┌──────────────────────────────────────────────────┐      │
│  │        RAG 检索管线 (5路并行召回)                    │      │
│  │  语义+BM25+聚焦+同义词+KG扩展 → RRF → Reranker    │      │
│  │  跨4科集合路由(data_structure/.../computer_network)  │      │
│  └──────────────────────────────────────────────────┘      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ ChromaDB      │  │ Neo4j        │  │ SQLite       │    │
│  │ (4科+题库)    │  │ (知识图谱)   │  │ (用户/对话)  │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└──────────────────────────────────────────────────────────┘
```

## Agent 协作

```
用户提问 → Supervisor 路由
  ├─ knowledge_agent（知识点检索与讲解）
  ├─ question_agent（练习题生成）
  ├─ grading_agent（答案批改评分）
  └─ path_agent（学习路径推荐）
每个 Agent: 检索工具 → 前置守卫(防幻觉) → 生成回答 → 后治理(来源/格式校验)
```

## 知识库（408 计算机考研）

| 学科 | 集合名 | 内容来源 | Chunks |
|------|--------|----------|--------|
| 数据结构 | `data_structure` | OCR教材 + 王道笔记 + CS-Basic | 2230 |
| 计算机组成原理 | `computer_organization` | Aye10032 笔记 | 592 |
| 操作系统 | `operating_system` | 王道笔记 + CSPostgraduate | 904 |
| 计算机网络 | `computer_network` | OCR教材 + CS-Notes + 手写 | 1420 |
| 题库 | `questions` | 2019-2024 真题 | 300 |

## 项目结构

```
毕业设计/
├── .env.example              # 环境变量模板
├── .gitignore
├── docker-compose.yml        # Docker 编排
├── README.md
├── knowledge/                # 知识库 Markdown 文件
│   ├── data_structure/
│   ├── computer_organization/
│   ├── operating_system/
│   ├── computer_network/
│   └── questions/
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt      # Python 依赖
│   └── app/
│       ├── main.py           # FastAPI 入口
│       ├── config.py         # Pydantic Settings 配置
│       ├── api/              # REST API 路由
│       │   ├── auth.py       # 认证接口
│       │   ├── chat.py       # 对话接口
│       │   ├── knowledge.py  # 知识库管理接口
│       │   ├── questions.py  # 题目接口
│       │   └── visualization.py  # 可视化接口
│       ├── agents/           # 多Agent编排
│       │   ├── supervisor.py         # Supervisor 路由
│       │   ├── knowledge_agent.py    # 知识检索Agent
│       │   ├── question_agent.py     # 出题Agent
│       │   ├── grading_agent.py      # 批改Agent
│       │   ├── path_agent.py         # 路径推荐Agent
│       │   ├── answer_governance.py  # 回答后治理
│       │   ├── retrieval_guard.py    # 前置守卫
│       │   ├── memory_manager.py     # 记忆管理
│       │   └── kg_tools.py           # 知识图谱工具
│       ├── rag/              # RAG 检索管线
│       │   ├── retriever.py          # 检索门面（多路召回→去重→阈值→Rerank→展开→补齐）
│       │   ├── recall.py             # 召回路由构建（语义/BM25/聚焦/同义词/KG扩展）
│       │   ├── query_classifier.py   # 查询分类（规则优先，LLM兜底）
│       │   ├── synonyms.py           # 同义词扩展
│       │   ├── bm25.py              # BM25 全文检索
│       │   ├── reranker.py          # Reranker 重排序
│       │   ├── postprocess.py       # 去重/层级展开/连续补齐
│       │   ├── context.py           # RAG 上下文拼接
│       │   ├── vectorstore.py       # ChromaDB 管理
│       │   ├── embeddings.py        # Embedding 封装
│       │   ├── cleaner.py           # 文档清洗
│       │   ├── splitter.py          # 文档分块
│       │   ├── enhancer.py          # 文档增强（摘要/QA生成）
│       │   ├── loader.py            # 文档加载
│       │   ├── ingest.py            # 入库 CLI
│       │   ├── knowledge_graph.py   # Neo4j 知识图谱
│       │   ├── graph_builder.py     # 图谱构建
│       │   ├── metrics.py           # 检索指标
│       │   ├── trace.py             # RAG 过程追踪（可视化用）
│       │   └── _metadata_spec.py    # 元数据规范
│       ├── db/               # 数据层
│       │   ├── models.py             # SQLAlchemy ORM
│       │   └── session.py           # 数据库会话
│       ├── schemas/          # 请求/响应模型
│       │   ├── auth.py
│       │   ├── chat.py
│       │   └── knowledge.py
│       ├── services/         # 业务逻辑
│       │   ├── auth.py              # 认证服务
│       │   ├── consistency_checker.py # 一致性检查
│       │   └── knowledge_ingest.py  # 入库服务
│       └── tools/            # 离线工具
│           ├── anomaly.py           # 异常检测
│           ├── dedup.py             # 去重
│           ├── normalizer.py        # 文本规范化
│           ├── imputer.py           # 缺失值填充
│           ├── quality_metrics.py   # 质量评估
│           ├── retrieval_eval.py    # 检索评测
│           └── eval_annotate.py     # 标注工具
└── frontend/                # Next.js 前端
    ├── package.json
    ├── next.config.js
    ├── tailwind.config.ts
    └── src/
        ├── app/                    # Next.js App Router
        │   ├── layout.tsx          # 根布局（AuthProvider）
        │   ├── page.tsx            # 主页（Shell + 状态编排）
        │   └── login/page.tsx      # 登录页
        ├── components/             # UI 组件
        │   ├── app-shell/          # 应用框架（Sidebar/Header/Content）
        │   ├── chat/               # 聊天面板
        │   ├── questions/          # 题目生成
        │   ├── knowledge/          # 知识库管理
        │   ├── rag/                # RAG 过程可视化
        │   ├── knowledge-graph/    # 知识图谱
        │   └── AgentFlow.tsx       # Agent 协作流程图
        ├── hooks/                  # 自定义 Hook
        ├── lib/                    # 工具库（auth/http/api/errors）
        └── types/                  # TypeScript 类型定义
```

## 快速启动

### 1. 环境配置

```bash
cp .env.example .env            # 必填：LLM_API_KEY、EMBEDDING_API_KEY
conda create -n edu-agent python=3.12 && conda activate edu-agent
pip install -r backend/requirements.txt
cd frontend && npm install
```

> **Ollama**：安装后运行 `ollama pull bge-m3` 下载 Embedding 模型
> **Neo4j**（可选）：从 https://neo4j.com/download/ 安装

### 2. 启动服务

```bash
# 终端1：Ollama（Embedding 服务）
ollama serve

# 终端2：Neo4j（可选，不启动则跳过图谱功能）
neo4j console

# 终端3：后端
cd backend && python -m app.main     # http://127.0.0.1:8000

# 终端4：前端
cd frontend && npm run dev           # http://localhost:3000
```

### 3. 构建知识库

```bash
cd backend
python -m app.rag.ingest             # 增量入库
python -m app.rag.ingest --rebuild   # 全量重建
python -m app.rag.ingest --no-graph  # 跳过图谱构建（Neo4j未启动时推荐）
python -m app.rag.ingest --category data_structure  # 指定分类
```

### 4. Docker 部署（可选）

```bash
docker compose up -d    # 一键启动
docker compose logs -f  # 查看日志
docker compose down     # 停止
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | LLM API 密钥 | — |
| `LLM_API_BASE` | LLM API 地址 | DashScope 兼容接口 |
| `LLM_MODEL` | LLM 模型名 | `glm-5` |
| `EMBEDDING_API_KEY` | Embedding API 密钥 | `ollama` |
| `EMBEDDING_API_BASE` | Embedding API 地址 | `http://localhost:11434/v1` |
| `EMBEDDING_MODEL` | Embedding 模型名 | `bge-m3` |
| `NEO4J_URI` | Neo4j 连接地址 | `bolt://localhost:7687` |
| `NEO4J_PASSWORD` | Neo4j 密码 | — |
| `KNOWLEDGE_DIR` | 知识库文件目录 | `./knowledge` |
| `CHROMA_PERSIST_DIR` | ChromaDB 持久化目录 | `./chroma_db` |
| `JWT_SECRET` | JWT 签名密钥 | — |

> LLM 和 Embedding 均使用 OpenAI 兼容接口，支持 DeepSeek、Qwen、GLM 等国产模型，更换服务商只需修改 `API_BASE` 和 `MODEL`。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 14 + @xyflow/react + TailwindCSS |
| 后端 | FastAPI + Pydantic Settings + Uvicorn |
| Agent | LangChain + LangGraph (StateGraph + Command) |
| RAG | ChromaDB + bge-m3 + 5路并行召回 + Reranker + 跨4科路由 |
| 知识图谱 | Neo4j + Cypher |
| LLM | GLM / DeepSeek / Qwen (OpenAI 兼容接口) |
| 部署 | Docker Compose |
