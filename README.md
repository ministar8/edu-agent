# 智能教学辅导多Agent系统

基于 LangChain + LangGraph 的多智能体协作教学辅导系统，面向 408 计算机考研课程，集成 RAG 检索增强生成与知识图谱，支持可视化展示 Agent 协作过程。

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

复杂查询 (comparison / deep):
  Supervisor → Planner → LangGraph Send 并行分发
    ├─ text_retrieval   # 纯文本检索
    ├─ kg_retrieval     # 纯知识图谱检索
    └─ knowledge_agent  # 综合检索
  → Synthesis Agent 合成 → 三阶段治理
```

## 知识库（408 计算机考研）

| 学科 | 集合名 | 内容来源 | 区块数 |
|------|--------|---------|--------|
| 数据结构 | data_structure | OCR教材 + 王道笔记 + CS-Basic | 2230 |
| 计算机组成原理 | computer_organization | Aye10032 笔记 | 592 |
| 操作系统 | operating_system | 王道笔记 + CSPostgraduate | 904 |
| 计算机网络 | computer_network | OCR教材 + CS-Notes + 手写 | 1420 |
| 题库 | questions | 2019-2024 真题 | 300 |

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 14 + @xyflow/react + TailwindCSS |
| 后端 | FastAPI + Pydantic Settings + Uvicorn |
| Agent | LangChain + LangGraph (StateGraph + Command) |
| RAG | ChromaDB + bge-m3 + 5路并行召回 + Reranker + 跨4科路由 |
| 知识图谱 | Neo4j + Cypher |
| LLM | Qwen / DeepSeek / GLM (OpenAI 兼容接口) |
| 嵌入 | bge-m3 (1024-dim, 本地 Ollama) |
| 重排序 | ColBERT Late Interaction |

## 项目结构

```
毕业设计/
├── knowledge/                    # 知识库 Markdown 文件（4科+题库）
├── backend/
│   ├── app/
│   │   ├── api/                  # REST API 路由（chat/auth/knowledge/questions/visualization）
│   │   ├── agents/               # 多Agent编排（Supervisor + 4专业Agent + Planner + 治理层）
│   │   ├── rag/                  # RAG 检索管线（多路召回/重排序/压缩/校验/图谱）
│   │   ├── evaluation/           # 评估体系（RAGAS + 诊断 + 消融实验）
│   │   ├── db/                   # 数据层（SQLAlchemy ORM + 会话管理）
│   │   ├── schemas/              # 请求/响应模型
│   │   ├── services/             # 业务逻辑（认证/知识点追踪/入库）
│   │   ├── tools/                # 离线工具（去重/规范化/质量评估/检索评测）
│   │   ├── main.py               # FastAPI 入口
│   │   └── config.py             # Pydantic Settings 配置（.env 统一管理）
│   ├── data/                     # 评估数据集 + 结果
│   ├── run_full_eval.py          # 完整评估脚本
│   └── run_ablation.py           # 消融实验脚本
└── frontend/                     # Next.js 前端
    └── src/
        ├── app/                  # App Router（layout/page/login）
        ├── components/           # UI 组件（chat/questions/knowledge/rag/knowledge-graph）
        ├── hooks/                # 自定义 Hook
        ├── lib/                  # 工具库（auth/http/api/errors）
        └── types/                # TypeScript 类型定义
```

## 快速启动

### 1. 环境配置

```bash
cp .env.example .env            # 必填：LLM_API_KEY、EMBEDDING_API_KEY
conda create -n edu-agent python=3.12 && conda activate edu-agent
pip install -r backend/requirements.txt
cd frontend && npm install
```

Ollama：安装后运行 `ollama pull bge-m3` 下载 Embedding 模型

Neo4j（可选）：从 https://neo4j.com/download/ 安装，不启动则跳过图谱功能

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

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| LLM_API_KEY | LLM API 密钥 | — |
| LLM_API_BASE | LLM API 地址 | DashScope 兼容接口 |
| LLM_MODEL | LLM 模型名 | qwen3.5-flash-2026-02-23 |
| EVAL_JUDGE_MODEL | 评测 Judge 模型（留空跟随 LLM_MODEL） | — |
| EMBEDDING_API_KEY | Embedding API 密钥 | ollama |
| EMBEDDING_API_BASE | Embedding API 地址 | http://localhost:11434/v1 |
| EMBEDDING_MODEL | Embedding 模型名 | bge-m3 |
| NEO4J_URI | Neo4j 连接地址 | bolt://localhost:7687 |
| NEO4J_PASSWORD | Neo4j 密码 | — |
| KNOWLEDGE_DIR | 知识库文件目录 | ./knowledge |
| CHROMA_PERSIST_DIR | ChromaDB 持久化目录 | ./chroma_db |
| JWT_SECRET | JWT 签名密钥 | — |

LLM 和 Embedding 均使用 OpenAI 兼容接口，支持 DeepSeek、Qwen、GLM 等国产模型，更换服务商只需修改 `LLM_API_BASE` 和 `LLM_MODEL`。

## 评估体系

### RAGAS 指标

| 指标 | 说明 |
|------|------|
| faithfulness | 回答是否忠于检索证据 |
| answer_relevancy | 回答与问题的相关度 |
| context_precision | 检索结果的信号噪声比 |
| context_recall | 检索结果的覆盖率 |

### 运行方式

```bash
# 完整评估
python run_full_eval.py

# 快速验证 (10 条)
python run_full_eval.py --quick

# 消融实验 (6 组条件)
python run_ablation.py --quick
```

## 量化数据

- 知识图谱: 274 节点 / 407 边 (数据结构学科)
- 评估数据集: 40 条跨学科样本
- HNSW 索引参数: M=32, ef_construction=300, ef_search=100
- 上下文 Token 预算: 6000
- 嵌入维度: 1024 (bge-m3)
- 嵌入批次大小: 64
- 并发检索线程: 6
