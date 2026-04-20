# 智能教学辅导多Agent系统

基于 LangChain + LangGraph 的多智能体协作教学辅导系统，集成 RAG 检索增强生成与知识图谱，支持可视化展示 Agent 协作过程。

## 系统架构

```
┌──────────────────────────────────────────────────┐
│              前端可视化层 (Next.js + React)         │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │ 智能问答  │ │ Agent协作 │ │ 知识库管理       │  │
│  │          │ │ 流程图    │ │ + RAG过程 + 图谱  │  │
│  └──────────┘ └──────────┘ └──────────────────┘  │
└─────────────────────┬────────────────────────────┘
                      │ REST API (CORS)
┌─────────────────────┴────────────────────────────┐
│              后端服务层 (FastAPI)                    │
│  ┌────────────────────────────────────────────┐   │
│  │        多Agent编排引擎 (LangGraph)           │   │
│  │   Supervisor → 检索 / 出题 / 批改 / 推荐    │   │
│  └────────────────────────────────────────────┘   │
└─────────────────────┬────────────────────────────┘
                      │
┌─────────────────────┴────────────────────────────┐
│              数据与模型层                            │
│  ChromaDB (向量) + Neo4j (图谱) + LLM API         │
└──────────────────────────────────────────────────┘
```

## 多Agent协作流程

| Agent | 职责 | RAG 集合 |
|-------|------|----------|
| **Supervisor** | 分析问题意图，路由到对应子Agent | — |
| **知识点检索Agent** | RAG检索教材，生成带引用的讲解 | `general` |
| **题目生成Agent** | 检索题库模板，生成新练习题 | `questions` |
| **批改评估Agent** | 检索标准答案，对比评分反馈 | `answers` |
| **学习路径推荐Agent** | 查询知识图谱，推荐学习路径 | `learning_paths` |

## 项目结构

```
毕业设计/
├── .env                  # 环境变量（API Key等，不提交Git）
├── .env.example          # 环境变量模板
├── requirements.txt      # Python 依赖
├── README.md
├── knowledge/            # 知识库文件目录
├── chroma_db/            # 向量数据库（自动生成）
├── backend/
│   └── app/
│       ├── main.py       # FastAPI 入口 + CORS + 路由注册
│       ├── config.py     # Pydantic BaseSettings 配置
│       ├── api/          # API 路由（chat/knowledge/visualization）
│       ├── agents/       # Agent 定义（supervisor/4个子Agent）
│       ├── models/       # Pydantic 数据模型
│       └── rag/          # RAG 管道（loader/splitter/embeddings/vectorstore/retriever/kg）
└── frontend/
    └── src/
        ├── app/          # Next.js 页面 + 布局
        ├── components/   # UI 组件（ChatPanel/AgentFlow/KnowledgePanel/RAGProcess/KGPanel）
        └── lib/          # 工具（API配置等）
```

## 快速启动

### 1. 环境配置

```bash
# ① 复制环境变量模板并填写 API Key
copy .env.example .env
# 必填项：LLM_API_KEY、EMBEDDING_API_KEY、NEO4J_PASSWORD

# ② 创建 conda 环境并安装 Python 依赖
conda create -n edu-agent python=3.12
conda activate edu-agent
pip install -r requirements.txt

# ③ 安装前端依赖
cd frontend
npm install
```

> **Neo4j 安装**：从 https://neo4j.com/download/ 下载安装，启动后在浏览器 http://localhost:7474 连接数据库，首次登录设置密码，填入 `.env` 的 `NEO4J_PASSWORD`

### 2. 启动服务

```bash
# 终端1：启动 Neo4j（必须先于后端启动）
# 方式一：命令行启动
neo4j console                  # 启动后访问 http://localhost:7474
# 方式二：Neo4j Desktop → 点击 Start → 状态变为 Running
# 启动后浏览器打开 http://localhost:7474 确认连接正常

# 终端2：启动后端
conda activate edu-agent
cd backend
python -m app.main             # http://127.0.0.1:8000

# 终端3：启动前端
cd frontend
npm run dev                    # http://localhost:3000
```

> **启动顺序**：Neo4j → 后端 → 前端。Neo4j 未启动时，知识图谱相关功能会报错，其他功能正常。

### 3. 构建知识库

将教材 PDF、题库等文件放入 `knowledge/` 目录，在前端"知识库管理"Tab 中上传并选择分类（general/questions/answers/learning_paths）。

## 环境变量说明

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `LLM_API_KEY` | LLM API 密钥 | — |
| `LLM_API_BASE` | LLM API 地址 | `https://api.deepseek.com/v1` |
| `LLM_MODEL` | LLM 模型名 | `deepseek-chat` |
| `EMBEDDING_API_KEY` | Embedding API 密钥 | — |
| `EMBEDDING_API_BASE` | Embedding API 地址 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `EMBEDDING_MODEL` | Embedding 模型名 | `text-embedding-v3` |
| `CHROMA_PERSIST_DIR` | ChromaDB 持久化目录 | `./chroma_db` |
| `NEO4J_URI` | Neo4j 连接地址 | `bolt://localhost:7687` |
| `NEO4J_USER` | Neo4j 用户名 | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j 密码 | — |
| `BACKEND_HOST` | 后端监听地址 | `127.0.0.1` |
| `BACKEND_PORT` | 后端监听端口 | `8000` |

> LLM 和 Embedding 均使用 OpenAI 兼容接口，支持 DeepSeek、Qwen、DashScope 等国产模型，更换服务商只需修改 `.env` 中的 `API_BASE` 和 `MODEL`。

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 14 + React Flow + TailwindCSS + Axios |
| 后端 | FastAPI + Pydantic Settings + Uvicorn |
| Agent | LangChain + LangGraph (StateGraph + Command) |
| RAG | ChromaDB + DashScope Embedding + RecursiveTextSplitter |
| 知识图谱 | Neo4j + Cypher |
| LLM | DeepSeek / Qwen (OpenAI 兼容接口) |
