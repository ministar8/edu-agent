# EDU-Agent 架构说明

> 408 考研智能教学辅导系统 · 多 Agent + RAG
> 本文用途：**把系统讲清楚**。每一节都可以独立作为答辩/论文的一小节。
> 数字均为 2026-09-23 实测（`src/` 共 20,770 行 / 104 个 .py 文件）。

---

## 1. 一句话定位

一个**面向 408 考研（数据结构 / 计算机组成 / 操作系统 / 计算机网络）**的智能教学辅导系统。
它要解决的不是「问答」，而是**教学闭环**：知识讲解 → 出题练习 → 答案批改 → 长期记忆。

技术上有两条主线：

| 主线 | 内容 | 代码位置 | 规模 |
|---|---|---|---|
| **A. 检索增强（论文核心）** | 8 阶段检索链：把 41 篇知识文档变成**可溯源、可评测**的证据 | `src/rag/` | 11,003 行 |
| **B. 多 Agent 编排** | 1 个 supervisor + 3 个专家，按意图分派并闭环 | `src/agents/` | 943 行 |

**为什么这两条都要有**：单纯 RAG 只能「查了再答」，无法处理「给我出 5 道题」「帮我改这道题」这类
**有副作用的请求**；单纯多 Agent 没有可靠的知识底座，会退化成「让大模型凭记忆讲 408」。
本项目的设计是**让专家 Agent 通过工具调用检索链**，两者正交组合。

---

## 2. 分层总览

```
┌──────────────────────────────────────────────────────────────────┐
│  前端  static/  （原生 HTML/CSS/JS，无构建步骤）                    │
│        登录 · 流式对话 · 出题 · 批改                                │
└────────────────────────────┬─────────────────────────────────────┘
                             │ HTTP / SSE
┌────────────────────────────▼─────────────────────────────────────┐
│  服务层  src/service/                                             │
│    service.py  FastAPI 应用 + 路由 + SSE 流式编排                  │
│    auth.py     JWT 认证（注册/登录/登出）                          │
│    health.py   健康检查    metrics.py  指标    errors.py  错误码   │
└────────────────────────────┬─────────────────────────────────────┘
                             │ 图调用（ainvoke / astream）
┌────────────────────────────▼─────────────────────────────────────┐
│  编排层  src/agents/                                              │
│    teaching_graph.py  外层图：load_memory → supervisor            │
│    supervisor.py      langgraph-supervisor 多专家路由             │
│    knowledge_agent / question_agent / grading_agent               │
│    tools.py           专家可调用的工具（含检索工具）                │
└────────────────────────────┬─────────────────────────────────────┘
                             │ 工具调用
┌────────────────────────────▼─────────────────────────────────────┐
│  检索层  src/rag/  ★ 论文核心                                      │
│    8 阶段检索链 → 融合成 FusedEvidence（带来源、分数、验证结论）     │
│    vectorstore / bm25 / reranker / fusion / verifier / semantic_cache│
└────────────────────────────┬─────────────────────────────────────┘
                             │
┌────────────────────────────▼─────────────────────────────────────┐
│  记忆层  src/memory/      工作记忆（记忆卡）+ 长期记忆（Store）      │
│  基础设施  src/core/      配置 / LLM 客户端 / 通用工具              │
│  数据层  src/db/          用户与会话（SQLAlchemy）                  │
│  契约层  src/schema/      全部请求/响应 Pydantic 模型              │
│  提示词  src/prompts/     版本化提示词（PROMPT_SET_VERSION）        │
└──────────────────────────────────────────────────────────────────┘
```

**依赖方向严格单向向下**：服务层 → 编排层 → 检索层 → 存储。
`src/rag/` **不 import** `src/agents/` 或 `src/service/`，因此检索链可以被独立评测
（这正是 `src/evaluation/` 能做实验的前提）。

---

## 3. 在线链路：一次提问的完整生命周期

```
①  POST /api/stream   {message, thread_id}
        │
        │  认证（JWT）→ 参数解析 → 归属校验
        ▼
②  返回 StreamingResponse(text/event-stream)      ← 注意：先校验再开流
        │                                          错误以 4xx 返回，而不是流中断
        ▼
③  teaching_graph（外层图）
        ├─ load_memory   读长期记忆 → 生成「记忆卡」
        │                以 **固定消息 ID** 的 SystemMessage 注入
        └─ supervisor    裁剪历史后进入内层 supervisor
        │
        ▼
④  supervisor 按意图路由到专家之一
        ├─ knowledge_agent  知识讲解 → 调用检索工具
        ├─ question_agent   出题     → agenerate_question_set
        └─ grading_agent    批改     → agrade_answer
        │
        ▼
⑤  专家需要知识时 → tools.py → aretrieve_evidence_with_retry（见 §4）
        │
        ▼
⑥  专家产出闭环输出 → supervisor 用 Command(goto=END) 短路，回到外层图
        │
        ▼
⑦  SSE 事件流回前端
        {"type":"token"}   逐 token（stream_mode="messages"）
        {"type":"message"} 完整消息（stream_mode="updates"）
        {"type":"error"}   错误
        data: [DONE]       结束标记
```

### 3.1 三个值得讲的设计点

**(a) 记忆卡用「固定消息 ID + upsert」而不是追加。**
LangGraph 的 `add_messages` reducer 对**同 ID** 消息做替换。若每轮追加一张记忆卡，
上下文会随对话轮数线性膨胀（且全是不同时刻的过期快照）。固定 ID 让 state 里**至多一张当前卡**。
同时 `load_memory` 会清理历史 checkpoint 里旧版累积的无 ID 卡片 —— 这是**向前兼容已有会话数据**的处理。

**(b) 裁剪只作用于「本轮送给模型的输入」。**
`trim_conversation` 在 `run_supervisor` 里裁剪，**不写回 state**。
因此 checkpoint 里保留完整历史（前端「历史记录」功能需要），但模型上下文有上界。

**(c) 专家必须闭环，否则报错而不是静默返回。**
`supervisor.py` 里 `forward_after_agent` 用 `Command(graph=Command.PARENT, goto=END)` 短路；
若专家未产出闭环输出，抛 `UnclosedSpecialistOutput`。装配期另有
`_assert_hook_covers_specialists` 校验 hook 覆盖了全部专家 —— **防止新增专家时漏挂钩子**。

---

## 4. 论文核心：8 阶段检索链

入口函数（**生产与评测共用同一个**）：

```python
from rag.retriever import aretrieve_evidence_with_retry
fused, verification = await aretrieve_evidence_with_retry(query=..., k=..., use_rerank=...)
```

| 阶段 | 事件名 | 阶段函数 | 做什么 |
|---|---|---|---|
| 1 | `classify` | `_stage_classify_query` | 查询分类（学科 / 意图），决定后续策略 |
| 2 | `plan` | `_stage_resolve_plan` | 解析检索策略与路由 |
| 3 | `decompose` | `_stage_decompose_query` | 复杂问题拆成子查询 |
| 4 | `recall` | `_stage_recall_and_merge` | **多路召回**：向量检索 + BM25，合并 |
| 5 | `dedup` | `_stage_dedup_and_threshold` | 去重 + 分数阈值过滤 |
| 6 | `rerank` | `_stage_rerank` | 交叉编码器重排（TEI，`use_rerank=True` 时） |
| 7 | `hyde` | `_stage_hyde` | HyDE：用假设性答案补召回 |
| 8 | `expand` | `_stage_expand_windows` | 窗口扩展：补回被切碎的上下文 |

阶段顺序在 `retriever.py:1503-1579` 由 `_emit_stage(...)` 显式标注，**可被 SSE 实时上报**
（`StageSink`），所以前端能看到「正在重排」这类中间状态。

### 4.1 输出：`FusedEvidence`

检索链的产物不是一堆文本，而是**带元信息的证据对象**：

- `text_evidences` —— 逐条文本证据（含来源、分数）
- `final_context` —— 拼装后的最终上下文
- `verification` —— `EvidenceVerifier` 的质量校验结论

**这个区分很重要**，评测口径就建立在它上面（见 §6.1）。

### 4.2 检索链的规模问题（已知，诚实记录）

`retriever.py` 有 **1,968 行 / 32 个顶层函数**，但真正属于「门面」的只有 4 个：
`retrieve_documents` / `aretrieve_documents` / `aretrieve_evidence` / `aretrieve_evidence_with_retry`。
其余是阶段函数与内部工具。

**职责归属存在错位**：`_stage_hyde` 有 116 行在 `retriever.py` 里，而专门的 `hyde.py` 只有 58 行。
这是「先跑通、后整理」留下的形态，**不影响正确性，但影响可读性**。
重构方向是把阶段函数下沉到各自的模块（`hyde.py` / `query_decomposer.py` …），
`retriever.py` 只留编排。**尚未做**，因为重构检索链必须重跑评测门禁（见 §7）。

---

## 5. 离线入库链

```
knowledge/*.md (41 篇)
   │
   ▼  rag/loader.py        解析（含 PDF 支持）
   ▼  rag/cleaner.py       清洗
   ▼  rag/enhancer.py      增强
   ▼  rag/knowledge_tagger.py  打标（学科类目）
   ▼  rag/splitter.py      切分（1,214 行 —— 含语义分段）
   ▼  rag/ingest.py        入库 → chroma_db/
```

**为什么这条链要单独说**：它是「检索质量」的上游。切分粒度、清洗规则的变化会直接改变
检索指标，**但这条链不计入覆盖率门槛** —— 排除的依据是「评测门禁端到端跑了真实入库链路」，
由 `TestBuildIndexUsesRealPipeline` 守着（**改成旁路那条测试会红，不要删**）。

---

## 6. 评测体系（论文实验章节的证据来源）

`src/evaluation/` 是**独立于服务层的实验设施**，可以单独运行：

### 6.1 两套互补口径

| 口径 | 模块 | 测什么 | 局限 |
|---|---|---|---|
| **检索门禁** | `retrieval_gate.py` | 检索本身的命中率/精度（**比基线**，容差 0.02） | 学科类目**已饱和**（1.0000）；章级 `kp_*` 仍有空间（0.90~0.925），但只到「章」、不到节/小节 |
| **RAGAS** | `ragas_eval.py` | 端到端答案质量：faithfulness / context_precision / context_recall / answer_relevancy | 依赖 judge LLM，有成本与随机性 |

**为什么要两套**：门禁是**回归防护**（改检索链不许退化），RAGAS 是**效果陈述**（给论文写数字）。
门禁跑得快、确定性高，适合 CI；RAGAS 慢且要外部服务，适合手动跑。

### 6.2 评测口径的三个「坑」（已处理）

**(a) contexts 不能既放成员又放拼接体。**
`fusion.py:228` 的 `final_context = "\n\n".join(parts)`，而 `parts` 就是各条 evidence 的格式化文本。
若把它和逐条 evidence **一起**作为 `contexts` 交给 RAGAS，指标会因「拼接体 vs 成员」的自我包含
关系被**系统性抬高**（`not in contexts` 只能挡住完全相同的整串）。
**已修**：`adapters.retrieve_contexts` 只返回逐条 evidence 正文（去重），kg-only 场景才回退。

**(b) `answer_relevancy` 的 embeddings 必须显式注入。**
ragas 0.4.3 的 `aevaluate` 对 `embeddings is None` 的指标会**自动兜底**注入一套默认 OpenAI embedding ——
所以「不注入」不是「跳过该指标」，而是**静默换一套向量**度量，导致该指标与其余三个不同源。
**已修**：注入检索链同一套 embeddings；构建失败则把该指标从本次评测中**摘掉**并在报告里留痕
（`_meta.dropped_metrics`），而不是让它悄悄换口径。

**(c) 假 embedding 上的一切结论都是伪影。**
`USE_FAKE_EMBEDDING=true` 时用的是字符 bigram 哈希（只保留词汇重叠信号，无语义泛化）。
实测教训：**在假路由上的「改善」和「退化」都不可信** —— 放宽 BM25 候选池曾让假路由 `hit@1` +5pp，
真实路由收益为零（连小数位都没变）。所以涉及语义质量的取舍**必须真实路由复验**。
RAGAS 报告里会写入 `_meta.warnings` 标注这一点。

### 6.3 门禁的路由

```bash
# 默认：假 embedding + 重排 off（调用方不要求重排）
PYTHONPATH=src uv run python -m evaluation.retrieval_gate
# 重排 on（走确定性假打分，无需 TEI）
PYTHONPATH=src GATE_RERANK_MODE=on uv run python -m evaluation.retrieval_gate
# 生产关闭态：要求重排、但部署关掉（复现 .env 的 RERANK_ENABLED=false）
PYTHONPATH=src GATE_RERANK_MODE=disabled uv run python -m evaluation.retrieval_gate
# 真实 embedding（唯一需要 TEI，用来回答「语义质量」）
PYTHONPATH=src GATE_USE_REAL_EMBEDDING=1 uv run python -m evaluation.retrieval_gate
```

路由按 `(embedding, rerank)` 组合区分，**已登记的组合各有一份基线**，
`load_baseline()` 拒绝跨口径比对（退出码 2）；未登记的组合直接拒绝（`SUPPORTED_ROUTES`）。
★ 重排 `on` 路由只证明**接线没坏**，不证明质量更好。
★ `disabled` 与 `off` 的差别**不在最终结果，而在代码路径** —— 前者会进入重排阶段才被
部署开关短路，候选池更大，故指标不可互比（实测 `disabled` 的 `category_precision`
0.9874 显著高于 `off` 的 0.9561）。
★ 各路由都跑「路由前提自检」（`_assert_route_preconditions`）：证明声称跑的那条路由
**真的被执行了**，抓 rerank 静默回退与 `rerank_used` 自报失真。

**九项指标**（`_METRIC_SPECS`）：

| 指标 | 方向 | 说明 |
|---|---|---|
| `category_hit_at_1` / `category_hit_at_k` / `category_mrr` | higher | **学科类目**（4 选 1）—— 已饱和（`hit@k = 1.0000`） |
| `category_precision` | higher | 返回证据中属目标学科的比例 |
| `empty_result_rate` | lower | 返回空证据的查询比例（堵「静默返回空」盲区） |
| `mean_evidence_count` | higher | 平均证据条数 |
| **`kp_hit_at_k`** / **`kp_mrr`** | higher | **章级知识点**的命中率 / MRR（2026-09-24 新增） |
| `kp_annotated` | higher | 被标注的查询条数（容差 0 ⇒ **标注被误删立刻失败**） |

★ **为什么加 `kp_*`**：学科级已饱和（1.0000），**测不出任何检索改动**。章级有真实下降空间
（实测 `off` = 0.9250、`disabled` = 0.9000），且能区分这两条路由 —— 学科级对两者都是 1.0，完全区分不出。

★ **「章」的载体是知识库文件**（`chapter_of_source`），不是 H1 标题：实测 H1 不均匀 ——
大文件 H1 = 章（`二、二叉树Binary tree`）、小文件 H1 = 具体主题（`3.链栈`），还有 `1定义`
这类碎片（根因是部分文件**没有 H1**，splitter 便把最深标题当路径首段）。文件恰好是标准章单元
（`05_树与二叉树` / `03_存储系统` / `05_传输层` …）。

★ 黄金集侧用 `metadata.knowledge_points` 标注章名（可多个，跨章条目给双标注）。
基线 `_meta.kp_granularity` 记录粒度载体，供 `load_baseline` 自证口径。

★ **未标注的查询不进 `kp_hit@k` 分母**（`kp_annotated` 单列）—— 「未标注」不等于「未命中」。

---

## 7. 工程门禁（保留的「够用」部分）

| 门禁 | 命令 | 作用 |
|---|---|---|
| 类型检查 | `pyrefly check` | **必须 0 错误**；可选依赖导入标 `# type: ignore[import-not-found]` |
| 静态检查 | `ruff check src/` | 含 `S110`（拦静默吞异常）、`C90`（圈复杂度 ≤25） |
| 格式 | `ruff format --check src/` | ★ **与 check 是两条命令，必须分别跑** |
| 检索回归 | `evaluation.retrieval_gate` | **九项指标**比基线，容差 0.02；按 `(embedding, rerank)` 组合分路由，各一份基线 |

> ★ **命令范围**：本工作区不含 `tests/`，有效范围是 `src/`（带 `tests/` 会报 `E902`，
> **不是代码问题**）。结构规模棘轮与覆盖率门槛**已随测试套件移出**，本工作区无自动门禁。

**圈复杂度棘轮的设计意图**：门禁的目的是**阻止新增债务**，不是逼人还清旧债。
所以复杂度阈值设成「当前最复杂函数的复杂度」，开启时命中 0 处 —— 新代码一超标就被拦，既有代码一处不动。

★ **改检索链必须重跑门禁**，且**先确认改动落在门禁覆盖范围内** —— 门禁通过 ≠ 改动安全。

---

## 8. 存储拓扑

| 存储 | 路径 | 内容 | 由谁读写 |
|---|---|---|---|
| **向量库** | `chroma_db/` | 41 篇知识文档的向量索引 | `rag/vectorstore.py`、`rag/semantic_cache.py` |
| **会话状态** | `checkpoints.db` | LangGraph checkpoint（thread 级对话状态） | `SQLITE_DB_PATH` |
| **长期记忆** | `store.db` | Store 向量索引（学生画像、错题） | `memory/sqlite.py`（`SQLITE_STORE_PATH`） |
| **业务库** | `edu_agent.db` | 用户、认证 | `db/session.py`（SQLAlchemy） |

**四个库分开是刻意的**：生命周期完全不同 —— 向量库随知识库重建，
会话状态随对话增长，长期记忆按学生累积，业务库最稳定。
混在一个库里会导致「重建知识库时误删用户」。

★ **路径必须用 Windows 形式传给 Python**：Git Bash 的 `/tmp` ≠ Windows 的 `/tmp`（= `C:\tmp`），
`SQLITE_DB_PATH=/tmp/x.db` 会**静默新建空库** → 查询全空。
**结果「全空 / 全一致」时，先怀疑查的是不是空对象。**

---

## 9. 模块归属与规模

按「对论文的价值」三分：

| 归属 | 模块 | 行数 | 占比 |
|---|---|---|---|
| **论文主体** | `rag` + `agents` + `prompts` + `schema` | 12,808 | 61.7% |
| **产品外壳** | `service` + `memory` + `core` + `db` | 3,216 | 15.5% |
| **数据处理工具** | `tools` | 2,871 | 13.8% |
| **评测设施** | `evaluation` | 1,845 | 8.9% |
| 顶层入口 | `src/__init__.py` + `run_service.py` | 30 | 0.1% |
| | **合计** | **20,770** | 100% |

> `src/tools/` 被 `evaluation/retrieval_gate.py` 与 `rag/ingest.py` 依赖（`clean_documents`），
> **不能单独归档** —— 删它会让门禁与入库链一起崩。

**已归档的工程化设施**（`mv` 同盘重命名，未删除），清单见
`../edu-agent-engineering-archive/ARCHIVE_INDEX.md`：
测试套件 17,540 行 / CI（`.github/`）/ codecov / `docs/ENGINEERING.md` / 3 个诊断脚本 /
`src/client/` SDK。★ 其中 **`.pre-commit-config.yaml` 已取回并适配启用**。
归档前固化的论文素材：**1,688 测试用例 / 覆盖率 75.2% / 8,982 语句**。

---

## 10. 已知边界与不足（答辩诚实清单）

这些问题**存在且已知**，列出来是为了被问到时能答，而不是藏起来：

1. **检索门禁的类目指标已饱和**（`category_hit_at_k = 1.0000`，40/40）。
   它能防回归，但**证明不了语义质量** —— 后者要靠 RAGAS 与真实 embedding 路由。
2. **`retriever.py` 职责错位**（1,968 行 / 32 函数，门面只 4 个），可读性差，重构未做。
3. **`verifier.py` 的 LLM 校验层实际未启用**（`use_llm_verify` 全为 False）。
   「有代码 ≠ 在用」，判据只能是调用链。
4. **~~`rerank_used` 语义不准~~ —— ✅ 已修（2026-09-24）**。
   原问题：`_stage_rerank` 返回的 `rerank_used` 判的是「**调用了**重排」，不是「重排**生效**」。
   `reranker.rerank()` 在 `settings.RERANK_ENABLED` 为假时于 `reranker.py:133`
   提前 `return documents[:top_k]`（一行重排都没跑），而 `rerank_used` 仍为 `True`。
   本机 `.env` 正是 `RERANK_ENABLED=false` + `use_rerank` 默认 `True` 的组合
   → **报告会把「未重排」标成「已重排」**。
   修复：把部署开关的判定从「被调用者内部」**前移到 `_stage_rerank` 入口**
   （`rerank_active = use_rerank and settings.RERANK_ENABLED`，**刻意不回写 `use_rerank`**
   —— 后者还兼着候选池大小的职责）。关闭时整段短路，顺带消除了
   「候选被 `_apply_rerank_threshold` 兜底截断到 2 条」这个**连带副作用**。
   `reranker.py:133` 保留为防御网（触达即 warning）。
   门禁新增 `GATE_RERANK_MODE=disabled` 路由 + `rerank_used` 断言防回归。
   完整分析见 `docs/RERANK_SWITCH_ANALYSIS.md`。
   另：RAGAS 路径仍显式声明 `settings.RERANK_ENABLED = cfg.use_rerank`，
   跑前用**真实推理请求**探活（不是只看 `/health`），报告写入 `_meta.run_config`。
5. **配置漂移**（`Settings` 用 `extra="ignore"`，`.env` 里它不认识的键**静默无效**）：
   - ✅ 已清（2026-09-24）：`.env` 的 `DATABASE_TYPE` 是唯一残留的孤儿键（已删）。
     ★ 文档此前记录的 `RERANK_MODE` / `CONTEXT_TOKEN_BUDGET_DEEP` / `CONTEXT_TOKEN_BUDGET_SHALLOW`
     **实测已不在 `.env` 中** —— 旧清单过期，勿再照抄。
   - `.env` **缺** `RERANK_EXPAND_FACTOR`（`.env.example` 有）→ 走默认值 5。
   核对法：`Settings.model_fields` 与 `.env.example` 的 `^[A-Z_]+=` 求**双向**差集。
6. **~~real embedding 路由的空结果~~ —— ✅ 已修（2026-09-24）**。
   原问题：`real+off` 路由 **3/156** 条 query 返回空（`empty_result_rate = 0.0192`），
   而 fake 路由恒为 0 —— 因 real 路由此前一直跑不了（TEI 未起），**该问题从未暴露**。
   **去重后本有 120+ 条候选，全部被阈值卡掉。**

   **根因是两个独立缺陷叠加**（实测反推，非推断）：

   | # | 缺陷 | 细节 |
   |---|---|---|
   | ① | **阈值校准的数学前提被违反** | `_resolve_retrieval_policy` 的校准公式基于 **k=20**（其注释里就是 `2.5/40` 的算例），但 `_dynamic_rrf_k` 在 13 条路由时给出 **k=36**，分数尺度随之缩小约 1.8× |
   | ② | **HyDE 兜底恰好对这三类禁用** | `should_trigger_hyde` 对 `answer`/`exercise`/`code` 直接 `return False`，而这 3 条正是 answer×2 + code×1 |

   数字链条（实测）：
   ```
   阈值 = 0.06 × (2.5/1.5) × 微调 = 0.12（answer/exercise）· 0.11（long/comparison）
   RRF 可达上限（两条最高权重路由相加）= 2.5/37 + 1.5/37 = 0.1081
   → 阈值 > 上限 → 只要 top 文档没命中 ≥3 条路由，必然返回空
   ```

   **修复**：`_stage_dedup_and_threshold` 末尾加「空结果保底」—— 过阈值后为空、
   但去重后有候选时，返回 **top-1** 并打 warning。
   **刻意不调阈值**：`RETRIEVAL_ROADMAP.md` 的「不做清单」明确列着「检索阈值微调」（#13/#25，
   三次实证真实口径零收益或有害）。且该 bug 的本质是**「有候选却返回空」这个独立的降级缺陷** ——
   LLM 拿不到任何上下文 → 必然答错，比返回低分候选更糟。取 top-1 而非 top-k：不假装这些文档
   「合格」，并保留低召回信号（`docs_count<2`）给下游 HyDE。

   **效果**：`real+off` 空结果 **0.0192 → 0.0000**；`cat@k` 0.8462 → **0.8590**、
   `kp@k` 0.7756 → **0.7821**。连带发现 **`fake+disabled` 也会触发**（候选池更大、路径不同）
   → 一并重录基线；`fake+off` / `fake+on` 逐位未变。**5 条路由的 `empty_result_rate` 现全为 0。**

   **未做（需决策）**：缺陷 ① 的**阈值校准本身**没有修 —— 修它等价于调阈值（在「不做清单」内），
   且会改变**全部** query 的阈值。若要修，应让阈值随 `_dynamic_rrf_k` 同比缩放
   （`× (_RRF_K_BASE+1)/(rrf_k+1)`），并在**真实路由**上验证是否伤 precision。
7. **~~`--update-baseline` 会把故障态写成基线~~ —— ✅ 已修（2026-09-24）**。
   原问题：`--update-baseline` 只拒绝「有 query **抛异常**」的情况，而
   **静默返回空不抛异常** —— 一次 Chroma 索引竞态让 16/156 条 query 返回空
   （`empty` 0 → 0.1026、`cat@k` 0.7949 → 0.5705），门禁**照样把故障态写成了基线**，
   复跑才发现。**录制侧的静默失败与判定侧的静默失败同样危险** ——
   后者早有 `report_retrieval_anomalies` 防护，前者此前没有。

   **修复**：新增 `check_baseline_sanity(metrics, baseline_path)`，写盘前与**现有基线**比对，
   命中任一类可疑点即拒绝：

   | 检查 | 阈值 | 依据 |
   |---|---|---|
   | 指标偏离旧基线 | > **0.10** | 正常的数据/代码改动远小于此（实测 1.2 改切分让 `cat@k` 动 0.013、`cat_prec` 动 0.031）；而该故障是 **Δ0.22**，量级差一个数量级 |
   | **空结果率上升** | **任何上升** | 与 `_METRIC_SPECS` 里 `empty_result_rate` 的容差 0 一致。**只查上升** —— 下降是好事；且不能写成「>0 即拒」，`real` 路由修复前合法地处于 0.0192 |

   旧基线不存在 / 读不出 / 口径不一致时**放行**（无可比对象，不该拦）。
   拒绝时打印可疑点 + 两种处置建议（故障→复跑；预期内改动→`--force-baseline`），
   逃生通道成功后注明「已跳过合理性校验」。

   **反向验证**（守卫必须被证明**会拦**，不能只看它存在）：

   | 场景 | 期望 | 实测 |
   |---|---|---|
   | 指标与旧基线一致 | 放行 | ✅ |
   | `cat@k` 0.8462 → 0.5705（复现该故障） | 拦住 | ✅ |
   | 空结果率 0 → 0.1026（复现该故障） | 拦住 | ✅ |
   | 旧基线口径不一致 | 放行 | ✅ |
   | 旧基线不存在 | 放行 | ✅ |

   端到端：故意把基线 `cat@k` 改成 0.50 → `--update-baseline` **拒绝、退出码 2、
   文件未被改写**；`--force-baseline` 则成功覆盖并注明跳过。正常路径不受影响。
8. **~~出题类查询被判「学科未命中」~~ —— ✅ 已修（2026-09-24）**。
   原问题：`category_hit_at_k` / `category_hit_at_1` 只认 `SUBJECT_TO_CATEGORY` 映射出的
   **一个**学科类目，而 `questions`（历年真题）**不是学科**、不在映射表里。
   于是对出题类查询「请出一道关于 X 的题」，**返回历年真题 —— 恰恰是正确行为 ——
   被判成「学科未命中」**。实测 `generate` 类 `cat@1` 一度只有 **0.0312**（几乎全判错）：
   32 条出题查询里有 17 条在报告里显示「期望 data_structure，实际 questions」。

   **修复**：把「期望类目」从**单值**改为**多值**：

   | 位置 | 改动 |
   |---|---|
   | `load_golden_queries` | 对 `query_type == "generate"` 返回 `(对应学科, "questions")` |
   | `QueryOutcome` | `expected_category: str` → `expected_categories: tuple[str, ...]` |
   | `first_correct_rank` / `category_precision` | 单值相等 → **成员判断**（命中任一即算命中） |

   合法来源因此变成「**对应学科的讲义** 或 **历年真题**」二者之一 —— 这正是出题场景的真实语义。

   **效果（real+off）**：`cat@1` 0.6987 → **0.8846**、`cat@k` 0.8590 → **0.9423**、
   `cat_mrr` 0.7507 → **0.9092**、`cat_prec` 0.7939 → **0.8923**；
   门禁的「首条未命中」列表从 **46 条降到 18 条**，**出题类条目全部消失**。
   ★ 关键验证：**`kp_hit_at_k` / `kp_mrr` 逐位不变**（0.7821 / 0.6107）——
   说明这次只修正了类目口径、没动知识点口径，**不是靠放宽指标刷分**。

   **代价（诚实记录）**：出题类的 `cat@*` 变宽松了 —— 它现在只回答「是否命中了对应学科
   **或**真题」，不再区分二者。若要单独看「真题召回得够不够」，应看 merged_qa 在证据里的
   占比（门禁暂未提供该指标，见第 6 条的说明）。

   **顺带解锁**：`recall.py` 里 `merged_qa_meta` 路由的恢复前置（「先解决 `questions` 的
   度量语义」）由此满足 —— 该路由可以重新评估了（改动存于仓库外
   `edu-agent-merged_qa_route.patch`）。
6. **阈值在 import 期固化**（`retriever.py` 里 `SCORE_THRESHOLD = settings.XXX`），
   改 `.env` 后**必须重启服务**才生效。反例：`RERANK_ENABLED` 是**调用期**读取，
   所以命令行临时覆盖是有效的 —— **两类字段必须区分对待**。
7. **测试套件已移出工作区**，本工作区无法跑全量测试；覆盖率数字是归档前固化的快照
   （1,688 用例 / 75.2% / 8,982 语句）。
   ★ 因此**结构规模棘轮与覆盖率门禁在本工作区跑不了** —— 改动 `src/` 时要靠人工判断
   是否会让某个文件/函数变长。

---

## 附：一句话讲完

> 这是一个把「**8 阶段检索链**」作为论文核心、用「**多 Agent 编排**」组织教学闭环的系统；
> 检索链的输出是**带来源与验证结论的证据对象**而非裸文本，因此它既能被服务层消费，
> 也能被独立的评测设施（检索门禁 + RAGAS）度量 —— **评测与线上共用同一个检索入口**，
> 这是整套实验结论可信的前提。
