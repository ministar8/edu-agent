# CLAUDE.md

本文件为 Claude Code / 贡献者提供本仓库的工作指引。

## 项目定位

**EDU-Agent** —— 408 考研智能教学辅导多 Agent 系统。基于 LangGraph + FastAPI + RAG，
支持知识问答、智能出题与答案批改。工程骨架对齐 [agent-service-toolkit](https://github.com/JoshuaC215/agent-service-toolkit)。

```
用户提问 → Supervisor（langgraph-supervisor create_supervisor 路由）
  ├─ knowledge_agent   知识讲解（RAG 检索）
  ├─ question_agent    出题（结构化真源 + 对话修饰）
  └─ grading_agent     批改（结构化打分 + 对话修饰）
        │
   RAG 检索管线：查询归一 → 分类 → 多路召回(语义 + BM25 + 元数据 + 同义词)
                → RRF 融合 → Reranker → HyDE → 语义缓存
```

**存储**：ChromaDB（向量检索 + 语义缓存）｜SQLite（`data/sqlite/` 下：用户 `edu_agent.db` + 会话 `checkpoints.db` + 长期记忆 `store.db`）

## 目录职责

| 路径 | 职责 |
|---|---|
| `src/agents/` | 多 Agent 编排：`registry.py` + `orchestration/`（teaching_graph / supervisor / state）+ `specialists/`（三专家 + 真源）+ `runtime/`（factory / tools / temperature） |
| `src/rag/` | 检索流水线：`api.py`（产品门面，含 release）、`retriever.py`（测量入口/门面）、`pipeline/`（编排+阶段）、`postprocess/`（RRF/去重/窗口）、`fusion.py`（证据融合）、`reranker.py`、`hyde.py`、`semantic_cache.py`、`ingest.py` |
| `src/core/` | `settings.py`（配置单例）、`llm.py`（`get_model` / `get_llm` 工厂） |
| `src/prompts/` | 提示词集中管理（agents 的 system prompt / supervisor 分派 / rag 单轮模板 / service 出题批改模板），import 期校验变量与花括号 |
| `src/service/` | FastAPI：`service.py`（路由 + SSE）、`auth.py`（JWT）、`threads.py`（会话列表）、`utils.py` |
| `src/schema/` | Pydantic 协议/领域模型（`schema.py` / `models.py` / `auth.py` / `questions.py` / `grading.py` / `evidence.py` 检索对外契约）；`rag/common/schemas.py` 只放检索链内部 LLM 输出 |
| `src/memory/` | 短期 checkpointer + 消息窗口 `window.trim_conversation` + 长期 Store（工厂/schema/topic/weak_topics/记忆卡） |
| `src/db/` | SQLAlchemy User 表与建表逻辑 |
| `src/document_processing/` | 离线文档清洗工具（**不参与运行时**；原名 `tools/`，与 `agents/tools.py` 消歧） |
| `static/` | 静态前端（login.html / index.html / app.js / api.js / auth.js / theme.js / style.css） |
| `knowledge/` | 408 知识库（四科讲义 + 题库 + 学习路线） |
| `src/evaluation/` | 评测。**三套彼此独立的尺子**：① **`task_eval/`** —— **论文效果章的产出器**（5 任务 `qa/generate/grade/verify/memory` × 66 条 demo case；子命令 `run/sanity/calibrate/rejudge/reprobe/backfill`）；② RAGAS Layer-1（`dataset/adapters/ragas_eval/cli`，组件指标，**不是任务指标**）；③ 检索质量门禁（`retrieval_gate` / `probe_gate` / `telemetry_report`）。★ 版本锚点见 `docs/EXPERIMENTS.md` **§20**（效果）与 §18（检索） |
| `docs/` | **工程文档**（见 `docs/README.md` 索引）。现行：**`ARCHITECTURE_RETRIEVAL.md` 检索架构总览（as-built + 术语表）** / `ARCHITECTURE.md` 系统架构 / `KB_MASTER_DESIGN.md` 知识库总册 / `RETRIEVAL_LAYER_DESIGN.md` + `RETRIEVAL_POLICY.md` 层设计与策略契约 / `DOCKER.md` 容器 + TEI 端点契约 / **`RETRIEVAL_PLAN.md` 执行方案** / `RETRIEVAL_ROADMAP.md` 路线与**「不做清单」** / `RERANK_SWITCH_ANALYSIS.md` 重排开关分析 / **`EXPERIMENTS.md` 实验总册** |

## 常用命令

```bash
uv sync                                  # 安装依赖
uv sync --group eval                     # RAGAS 评测依赖（可选）
PYTHONPATH=src uv run python -m evaluation.ragas.cli --dataset evals/datasets/golden/sample_408.jsonl --limit 5
# ↑ 路径已按实仓校正：旧写法 `evals/sample_408.jsonl` 从来不存在，真实黄金集 = evals/datasets/golden/sample_408.jsonl（= src/evaluation/ragas/cli.py 的 --dataset 默认值；核对：git ls-files evals/datasets/golden）

# 任务级评测（论文效果章 · src/evaluation/task_eval）
PYTHONPATH=src uv run python -m evaluation.task_eval sanity       # Gold 体检，进 0B 前必跑
PYTHONPATH=src uv run python -m evaluation.task_eval run --no-agent   # 只跑检索探针，零 LLM 成本
PYTHONPATH=src uv run python -m evaluation.task_eval run          # 跑 agent + judge，出效果数字（消耗 token）
PYTHONPATH=src uv run python -m evaluation.task_eval reprobe      # 只重跑检索探针（零 LLM）
PYTHONPATH=src uv run python -m evaluation.task_eval backfill     # 回填机械可算字段（零 LLM）

# Memory 链路 Gate 与效果探针（★ 本机必须带 PYTHONIOENCODING=utf-8，否则 GBK 打印 ✅ 时崩）
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/ops/verify_memory_loop.py
uv run python src/run_service.py         # 启动服务 → http://127.0.0.1:8000
# 知识库入库：`rag.ingest` 自 2026-10-10 起**只负责 learning_paths**
# （四科 / exams / code 已迁到 `ingest_layers`，逐层脚本见 `scripts/ingest/`）
uv run python -m rag.ingest              # learning_paths 增量
uv run python -m rag.ingest --rebuild    # 只重建 learning_paths（≠ 全量重建）

# 全量重建（四科 + exams + code + learning_paths）：先备份/删除 chroma_db，
# 再按序调用六层 ingest()（与 retrieval_gate.build_index 同源）
PYTHONPATH=src uv run python -c "from rag.ingest_layers import basic,advanced,exams,exam_practice,code,learning_paths,_shared; kp=_shared.load_kp_ids(); basic.ingest(kp); advanced.ingest(kp); exams.ingest_all(kp); exam_practice.ingest(kp); code.ingest_all(kp); learning_paths.ingest()"

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
- **注册新 agent 需同步三处**：`src/agents/registry.py` 的 import、`agents` 字典条目、`langgraph.json` 的 `graphs`。
  注册后可通过 `/api/{agent_id}/invoke|stream|history|threads` 直接寻址；未知 agent 返回 404。
- **密钥字段用 `SecretStr`**，取值需 `.get_secret_value()`。
- **LangSmith 追踪**：`LANGCHAIN_*` 由 `Settings.export_langsmith_env()` 在 lifespan 中写入
  `os.environ`（LangChain 只从进程环境读取并自动埋点，放 Settings 里无效）。
  开追踪只需在 `.env` 设 `LANGCHAIN_TRACING_V2=true` 与 `LANGCHAIN_API_KEY`，不需要改代码。
- **规模红线**：单文件 ≤600 行、单函数 ≤60 行（人工遵守，本工作区无自动门禁）。
- 关键逻辑与复杂函数写中文注释。

## 工作区边界

- **测试套件**：`tests/` 目录下单测约 **300 例**（`tests/test_memory/` 205 例 + `tests/test_document_processing/` 101 例 + 其他），纯本地 I/O、无网络无密钥、不碰真 Store/Chroma。
- **CI**：只有两条 job（`.github/workflows/ci.yml`），① `ruff check` + `ruff format --check` + `pyrefly check` + `pytest -q`；② 检索质量门禁（只跑默认路由，假 embedding / 重排 off）。`task_eval` 与 Memory Gate 刻意不进 CI（要真密钥、按 token 计费、且模型输出有随机性），改动后需本机手动重跑。
- **保留的自研门禁**：`evaluation.gates.retrieval_gate` / `probe_gate`（检索）+ Memory Gate（效果）。

## 注意事项（精简版）

- **假 embedding 模式**：`USE_FAKE_EMBEDDING=true` 时 `get_embeddings()` 返回本地确定性哈希实现，**只保留词汇重叠信号、没有语义泛化能力，严禁用于生产**。
- **Windows 下**：`run_service.py` 会把事件循环切到 `WindowsSelectorEventLoopPolicy`（异步 DB 驱动不兼容 Proactor）。
- **检索质量门禁**：改动检索链（阈值、RRF 权重、切分策略、去重、集合路由）后，必须跑 `evaluation.gates.retrieval_gate`，与 `evals/baselines/retrieval_baseline.json` 对比，任一指标退化即失败。
- **临时索引建库**：本机 `%TEMP%`（`C:\Users\star\AppData\Local\Temp`）**不可写**，SQLite 建库/压实要写临时文件，`retrieval_gate` / `probe_gate` 建临时索引前须先设 `export TMPDIR=$PWD/data/tmp TEMP=... TMP=... SQLITE_TMPDIR=$PWD/data/tmp`。
