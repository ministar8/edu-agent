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
| `src/evaluation/` | 评测。**三套彼此独立的尺子**：① **`task_eval/`** —— **论文效果章的产出器**（5 任务 `qa/generate/grade/verify/memory` × 66 条 demo case；子命令 `run/sanity/calibrate/rejudge/reprobe/backfill`）；② RAGAS Layer-1（`dataset/adapters/ragas_eval/cli`，组件指标，**不是任务指标**）；③ 检索质量门禁（`retrieval_gate` / `probe_gate` / `telemetry_report`）。★ 版本锚点见 `docs/EXPERIMENTS.md` **§20**（效果）与 §18（检索） |
| `docs/` | **工程文档**（见 `docs/README.md` 索引）。现行：**`ARCHITECTURE_RETRIEVAL.md` 检索架构总览（as-built + 术语表）** / `ARCHITECTURE.md` 系统架构 / `KB_MASTER_DESIGN.md` 知识库总册 / `RETRIEVAL_LAYER_DESIGN.md` + `RETRIEVAL_POLICY.md` 层设计与策略契约 / `DOCKER.md` 容器 + TEI 端点契约 / **`RETRIEVAL_PLAN.md` 执行方案** / `RETRIEVAL_ROADMAP.md` 路线与**「不做清单」** / `L1L2L3_RETRIEVAL_REVIEW.md` 分级评审 / `RERANK_SWITCH_ANALYSIS.md` 重排开关分析 / **`EXPERIMENTS.md` 实验总册** |

## 常用命令

```bash
uv sync                                  # 安装依赖
uv sync --group eval                     # RAGAS 评测依赖（可选）
PYTHONPATH=src uv run python -m evaluation.cli --dataset evals/datasets/golden/sample_408.jsonl --limit 5
# ↑ 路径已按实仓校正：旧写法 `evals/sample_408.jsonl` 从来不存在，真实黄金集 = evals/datasets/golden/sample_408.jsonl（= src/evaluation/cli.py 的 --dataset 默认值；核对：git ls-files evals/datasets/golden）

# 任务级评测（论文效果章 · src/evaluation/task_eval）
PYTHONPATH=src uv run python -m evaluation.task_eval sanity       # Gold 体检，进 0B 前必跑
PYTHONPATH=src uv run python -m evaluation.task_eval run --no-agent   # 只跑检索探针，零 LLM 成本
PYTHONPATH=src uv run python -m evaluation.task_eval run          # 跑 agent + judge，出效果数字（消耗 token）
PYTHONPATH=src uv run python -m evaluation.task_eval reprobe      # 只重跑检索探针（零 LLM）
PYTHONPATH=src uv run python -m evaluation.task_eval backfill     # 回填机械可算字段（零 LLM）

# Memory 链路 Gate 与效果探针（★ 本机必须带 PYTHONIOENCODING=utf-8，否则 GBK 打印 ✅ 时崩）
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/memory_step2_gate.py
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/memory_step4fix_gate.py
PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/memory_e5_probe.py --reanalyse --write  # 零 LLM 重析
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

- **不含**测试套件、代码覆盖率与结构规模棘轮门禁 —— 已从本仓库移出。
  ★ 原归档目录 `../edu-agent-engineering-archive/` **在本机已不存在**（2026-10-03 核实），
  无本地副本可取回。
- **有 CI，但只有两条 job**（`.github/workflows/ci.yml`，2026-10-06 加）：
  ① `ruff check` + `ruff format --check` + `pyrefly check`；
  ② 检索质量门禁 —— **只跑默认路由**（假 embedding / 重排 off），比对的只是
  `evals/baselines/retrieval_baseline.json` **这 1 份**。★ 门禁整体按 `(embedding, rerank)`
  组合登记了 **6 份基线**，但其余 5 条（含唯一能答语义质量问题的**真 TEI 路由**）
  **不在 CI 里**，须本机手跑（见 `README.md` 的路由口径说明）。
  另支持 `workflow_dispatch` —— 答辩时可现场触发一次。
- ★ **`task_eval` 与三个 Memory Gate 刻意不进 CI**：要真密钥、按 token 计费、且模型输出有随机性。
  ⇒ **论文效果章的数字没有任何自动兜底**，改动批改链 / Memory 写链 / 评测器后，
  **必须本机手动重跑** `scripts/memory_step*_gate.py`（带 `PYTHONIOENCODING=utf-8`）。
- **保留**的自研门禁：`evaluation.retrieval_gate` / `probe_gate`（检索）+ 上述 Memory Gate（效果）。
- 检索数字的版本归属见 `docs/EXPERIMENTS.md` §18（`V-2026-10-02`），
  效果数字见 **§20**（`V-2026-10-07`，标签对象 `abc115b` → 落点提交 `0f24891`）；两处都列了「已知偏离」，引用前先核对归属矩阵。

## 注意事项

- 检索依赖两个本地 TEI 容器：`tei-embedding`（`localhost:11435`）与 `tei-rerank`（`localhost:11436`）。
  部署入口只有 `scripts/tei_deploy.ps1`；日常 `docker start tei-embedding tei-rerank`。
  就绪以 `scripts/tei_ready.py` 为准（`/health` 200 ≠ 模型加载完成）。细节见 `docs/DOCKER.md`「TEI」。
- **假 embedding 模式**：`pyproject.toml` 的 `[tool.pytest_env]` 设 `USE_FAKE_EMBEDDING=true` 后，
  `get_embeddings()` 返回本地确定性哈希实现（`rag.embeddings.HashingEmbeddings`）——
  **检索质量门禁靠它在无 TEI 时做确定性比对**。该实现**只保留词汇重叠信号、
  没有语义泛化能力，严禁用于生产**。
  注意：`semantic_cache._DATA_DIR` / `_JSONL_FILE` 是**模块级常量（import 期固化）**，
  临时重定向须用 `monkeypatch` 指向临时目录，否则会写坏真实的 `chroma_db/semantic_cache/`。
- Windows 下 `run_service.py` 会把事件循环切到 `WindowsSelectorEventLoopPolicy`（异步 DB 驱动不兼容 Proactor）。
- `src/rag/` 与 `src/tools/` 的类型注解尚不严格，`pyproject.toml` 中对这两个目录放宽了 pyrefly 检查（技术债）。
- **Q&A 原子机制**：真题/例题会产出 `merged_qa` chunk（`section.chunk_role`），
  并填 `qa.question/answer/answer_key`。`_ANSWER_RE` 同时认讲义「答案：」与真题
  「选项行尾 ✅ + **解析**：」。`merged_qa_meta` **专用召回路由已否决**（两轮净负），
  但 merged_qa 仍会经基础路由被大量召回。
- **检索质量门禁**：改动检索链（阈值、RRF 权重、切分策略、去重、集合路由）后，必须跑
  `PYTHONPATH=src uv run python -m evaluation.retrieval_gate`。
  它用确定性哈希 embedding + 临时索引跑 156 条黄金集 query（`evals/datasets/golden/sample_408.jsonl`），与 `evals/baselines/retrieval_baseline.json`
  对比，任一指标退化即失败。**它衡量的是检索管线是否退化，不是语义质量**（语义质量用
  `evals/cli.py` 的 RAGAS）。改动导致指标变化时，用 `--update-baseline` 重录，
  但**必须在 PR 里说明为什么这个变化是可接受的**。
- **探针门禁（细粒度补充）**：`PYTHONPATH=src uv run python -m evaluation.probe_gate`。
  `retrieval_gate` 的 `kp_*` 是**章级**（只看文件名），测不到「**小节级细节是否进了证据**」；
  本门禁用 `evals/datasets/golden/retrieval_probes.jsonl` 的 5 条 probe，记录每条 probe 的**目标 chunk 在
  哪一层丢失**（`dropped_by`），与 `evals/baselines/probe_baseline.json` 比较 ——
  **拦「后退」、放行「前进」**（层级序见 `candidate_trace.DROP_REASONS`）。
  跑在**临时索引 + 就绪屏障**上；权威路由为
  `GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1`。
  **不要**用 `candidate_trace` 当门禁 —— 它跑生产索引、无就绪屏障、无退出码。
- **遥测报表（只读，不是门禁）**：`PYTHONPATH=src uv run python -m evaluation.telemetry_report`。
  它给 `data/metrics/rag_metrics.jsonl`（由 `rag.metrics` 写入、此前**无任何读方**）
  补上读方：流量构成、逐阶段漏斗（按 `query_type`）、有效阈值分布、入库交叉校验。
  **无基线、无判定**；`--output <path>` 落盘归档（建议 `evals/results/`）。
  ★ 两条使用纪律：① 用 `query_preview ∩ 黄金集` 判定流量来源 —— 实测 **99.4% 是评测流量**
  ⇒ 它回答「管线各层在黄金集上的行为分布」，**不是**线上统计，别拿它推断生产表现。
  ② **日志混了多个代码版本**（Step 1~10 各轮实验都写进同一份），必须用
  `--since` / `--until`（ISO 或 `6h`/`3d`）把窗口钉到单一版本，否则读到的是**混合口径**
  —— 实测 `generate` 过阈率在 09-27 15:00 前后为 0.075 → 0.187。
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
- **评测器口径四条硬规则**（2026-10-07 一轮 review 里全部实测踩到，改评测器前先读这几句）：
  ① **「测不到」记 `None`（N/A，不进分母），绝不记 `False`** —— 旧 `category_hit` 用
  `.get(subject, subject)` 把学科码 `cn` 拿去比类目名，恒 False，
  系统性压低了 `grade`/`verify` 各 4 条（而 `qa`/`generate` 用 `network` 所以一直没暴露）；
  ② **`case_invalid` 不进失败率**（分母 = 有效 n）—— 方案 §2.B「validity ≠ product failure」；
  ③ **`used` 必须有记忆卡的事实前提**（`recalled_actual`），且 `correct_use` **按样本极性定义**
  —— 旧口径下负样本「什么都没做」判失败、「碰巧提到」判通过，两个方向都错；
  ④ **gold 一律用可接受集**（`expected_any`）并**逐题查 `kp_index`** ——
  `堆` 不在表里、`排序` 与 `快速排序` 是并存两个节点，单值 gold 必产生假阴性。
  ★ ①~④ 分别由 `memory_step4fix_gate.py` 的 **③j / ③i / ③d~③h** 锁定，不是靠文档自觉。
