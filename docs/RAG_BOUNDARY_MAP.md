# RAG 边界地图（答辩/读码用 · 代码不动版）

> **定位**：`ARCHITECTURE_RETRIEVAL.md` 讲设计与论证，`src/rag/README.md` 讲主路径；
> 这里只补一样东西：**每个职责挂在哪个文件（停靠点）、保什么不变量、哪些地方靠约定而不是靠类型**。
> 配套结论：链路设计本身自洽，混乱集中在"出口签约、文件切分、门禁重复"三处，见 §8 台账。

---

## 0. 两条链路只有一个式子

```
离线：docs → loader → clean → split → enhance → tag(kp) → Chroma 集合（6 分层）
在线（产品）：TaskPolicy ─→ retrieve_for_task()（检索 → finalize → apply）─→ EvidenceBundle → Agent/前端溯源
在线（测量）：aretrieve_evidence_raw()（未裁剪包）─→ 检索门禁 / RAGAS / 诊断
```

变更铁律：**两条链共享同一批集合、同一批集合名定义**。改任何一边先查 §5 的真源表。

---

## 1. 入口与调用方矩阵（谁在哪进链路）

产品检索入口：`rag.retrieval.api.retrieve_for_task()`（含 finalize + apply）。
测量检索入口：`rag.retrieval.retriever.aretrieve_evidence_raw()`（未裁剪包）。
（`aretrieve_evidence` 仍是底层实现；`retriever_retry` 已并入 `retriever.py`。）

| # | 调用方 | 位置 | 性质 |
|---|---|---|---|
| 1 | Agent 检索工具 `_retrieve_payload()` | `agents/tools.py` | 生产 |
| 2 | 检索门禁 | `evaluation/gates/retrieval_gate/_gate.py` | 门禁 |
| 3 | RAGAS 质量评测 | `evaluation/ragas/adapters.py` | 评测 |
| 4 | 任务评测探针 | `evaluation/task_eval/retrieval_probe.py` | 评测 |
| 5 | 阶段追踪诊断 | `evaluation/diagnostics/_stage_trace_core.py` | 诊断 |

★ 生产与门禁/评测共用同一入口是有意为之（同一口径可比）。**不要**在门禁里另写检索副本。

## 2. 在线链路停靠点（6 步 → 文件）

| 步 | 停靠点 | 一句话 | 禁区（别人做会被打回的） |
|---|---|---|---|
| ① 理解 | `retrieval/query_classifier.py` / `query_decomposer.py` / `retrieval_plan.py` | 分类 → 分解 → 算预算 | 不做安全裁剪；不接触 Chroma |
| ② 召回·拼 | `retrieval/recall.py` + `recall_collections.py` | 这一查发哪几路、各查什么、查哪个集合 | **不查库**；只产出"规格" |
| ② 召回·跑 | `retrieval/routes.py` + `bm25.py` | 并发执行单路，碰 Chroma/BM25 的**唯一地方** | 不做 RRF；不做权限判断 |
| ③ 融合 | `retrieval/postprocess/`（`_rrf.py`） | 按路由秩加权 RRF，不拼原始分 | 不看 TaskPolicy |
| ④ 收紧 | `retrieval/pipeline/_stages.py`（orchestrator 编排）+ `reranker.py` + `hyde.py` + `postprocess/_window.py`、`_dedup.py` | 去重→阈值→重排→HyDE/窗口兜底 | 兜底触发条件写在 stage 内，不在门面 |
| ⑤ 出包 | `retrieval/evidence.py`（契约）+ `evidence_policy.py`（策略）+ `layer_recall.py` | 资格 eligibility 与披露 release 分离 | **release 全仓唯一出口 = `apply_evidence_policy()`**（§6-I3） |
| ⑥ 缓存验证 | `retriever_io.py` + `semantic_cache.py` + `verifier.py` + `common/metrics.py` | 查缓存→回写→规则校验→指标 | 缓存命中必须浅拷贝（§6-I5）；只缓存检索层，不缓存 LLM 生成 |

两个"融合"词要分清：`postprocess`（②③ 之间，多路→排序列表）≠ `fusion.py`（⑤ 之前，排序列表→FusedEvidence，`afuse_documents`）。

## 3. 离线链路停靠点

| 步 | 停靠点 |
|---|---|
| 单文件流水 | `rag/ingest.py`（现只管 `learning_paths`）：loader→cleaner→splitter→enhancer→knowledge_tagger→vectorstore |
| 分层构建 | `rag/ingest_layers/`：`build()`（纯函数，不落库）+ `ingest()`（落库+写 links）；生产顺序 basic→advanced→exams→exam_practice→code→learning_paths |
| 脚本 | `scripts/ingest/*`（调 ingest_layers）；`ingest_basic_all.py` / `ingest_advanced.py` / `ingest_exams.py` / `ingest_exam_practice.py` / `ingest_code.py` |
| 存储门面 | `rag/common/vectorstore.py`（含 HNSW 元数据校验 `needs_rebuild`；"集合终坏只能重建"见 `wait_until_ready` 注释） |
| Embedding | `rag/common/embeddings.py`：bge-m3/TEI，批 16、单条 ≤3000 字符 |

## 4. 三层策略对照（不回答"到底谁管 k"就用这张表）

| 层 | 管什么 | 真源文件 |
|---|---|---|
| **TaskPolicy** | 安全/披露：进不进池（ eligibility ）、包里能不能带答案/题号（ release ） | `schema/task_policy.py` + `rag/retrieval/task_policy.py` |
| **RetrievalPlan / depth** | 计算预算：k、coarse_k、skip_decompose、skip_rerank | `retrieval/retrieval_plan.py` |
| **部署开关** | 这个环境是否真跑 rerank | `settings.RERANK_ENABLED`（论证见 `docs/RERANK_SWITCH_ANALYSIS.md`） |

## 5. 数据真源表（"一个集合是什么"该查哪）

| 数据 | 单一真源 | 同步的影子（改动须查） |
|---|---|---|
| 集合名 ↔ 学科 | `recall_collections.py`（`SUBJECT_COLLECTIONS`/`_CODE_COLLECTION`） | `ingest_layers/*`、`scripts/ingest/*` |
| 集合目录 → 采集 | `ingest_layers/__init__.py::build_all()` | `rag/ingest.py DEFAULT_CATEGORIES` |
| 层 / doc_role 元数据 | `ingest_layers/_shared.py` + `common/_metadata_spec.py` | `evidence_policy.py` 读取字段 |
| 距离→相似度 | `embeddings.similarity_from_distance()`（**全仓唯一换算点** §6-I1） | 无 |
| 缓存常量 | `retrieval/_semantic_cache_codec.py` | `routes._query_cache`（另一层缓存，非同一物） |

★ 这张表本身可作答辩结论使用："集合身份目前定义分散在 3 处，靠 `build_all()` 间接对齐"——这是已知债务不是设计目标。

## 6. 全链不变量（任何改动不许违反；违反即 bug）

- **I1 相似度方向**：距离→相似度只许在 `similarity_from_distance()` 发生；未登记的 `hnsw:space` 抛错而非静默回退。
- **I2 学科集合路由语义**：`recall_collections._contains_collection_keyword` 对非 ASCII 用子串、拟 ASCII 用词边界——单字关键词已展开成词形，重新加单字关键词会回归误命中。
- **I3 release 唯一出口**：BMO25/Reranker/去重/缓存内一律不做 TaskPolicy 裁剪；答案字段裁剪只发生在 `apply_evidence_policy()`。
- **I4 `use_rerank` 语义**：表示"按重排口径准备候选（决定 coarse_k）"，不表示"会调用 rerank()"；是否执行看 `depth.skip_rerank` × `RERANK_ENABLED`。
- **I5 缓存隔离**：`routes` 缓存命中必须浅拷贝（下游写 metadata 会污染缓存）；语义缓存存**裁剪前**的 FusedEvidence，命中后仍过 finalize + apply（顺序见 `_semantic_cache_codec` 文档串）。
- **I6 溯源真源**：`rerank_used` 不是独立布尔，唯一真源是 `rerank_status == success`（`pipeline/_orchestrator._tag_evidence_provenance`）。溯源字段一律走 metadata 下划线前缀键（`_retrieval_depth/_route_type/_effective_k/...`），门禁断言依赖这些键名。
- **I7 双保险**：exam 资源过滤在召回侧（policy.eligibility_where + merge_where_filters 进 Chroma where）与出包侧（`evidence_policy._resource_blocked`）各一道，缺一不可。

## 7. 人肉同步点（"约定 > 类型"清单，答辩问软肋就用这并）

这些地方的正确性**不靠编译器/类型保护，靠注释与人**保持一致：

1. **两条入口已显式分开**：产品路径走 `retrieve_for_task()`（内部 finalize + apply）；测量路径走
   `aretrieve_evidence_raw()`（原始包）。`finalize/apply` 仍在语义缓存**之上**，不得下移
   （`_semantic_cache_codec.py` 明文警告）。
2. **`pack_blocked()` ↔ `apply_evidence_policy` 的 continue 条件**必须逐条一致（`evidence_policy.py` 内注释自证）。
3. **单一编排**：classify→plan→decompose 只由 pipeline 执行（`_run_stages_early`）；门面通过
   `_PlanSink` 旁路拿到解析结果，不再自己算一遍。评测脚本仍经 `_stages` 命名空间猴子补丁拦截。
4. **评测脚本兼容 import**：`pipeline.__init__` 从 `_internals` 重导出
   `SCORE_THRESHOLD/StageSink/_resolve_thresholds/_derive_rerank_status` 及各类型；
   `R._resolve_thresholds` 也不能删。
5. **双策略模块**：`schema/task_policy.py` 与 `rag/retrieval/task_policy.py` 分工靠文件内注释，命名只差前缀。
6. **索引健康**：`get_collection_info` 返回 `needs_rebuild` 属检测器非修复器；HNSW 段丢失只能重建集合，进程内等待无效。

## 8. 技术债台账（已梳理、未动代码 · 2026-11）

按"收益/风险"排序，均可单独列优先级；**本轮全部不执行**，仅作方向记录：

| # | 债 | 证据 | 建议 |
|---|---|---|---|
| T1 | 出口契约劈两半 | `_semantic_cache_codec.py:44-52` 明文警告 | **已收口（2026-11-04）**：新增产品门面 `retrieve_for_task`（含 finalize+apply）；测量路径保持未裁剪包；`finalize/apply` 仍在缓存之上 |
| T2 | 双重编排（理解段两份实现） | §7-3 | **已收口（2026-11-04）**：pipeline 独占 classify/plan/decompose，门面经 `_PlanSink` 旁路取结果 |
| T3 | 文件机械拆分：`_support/_helpers/_types/_constants/_log` 到处是 | 拆分标记 docstring 全仓 15+ 处 | **部分收口（2026-11-04）**：`_constants/_types/_support` → `_internals`；`retriever_retry` 并入 `retriever`；`postprocess/_log` 删除。剩余 `chunking/` 与 `common/_vectorstore_*` 未动 |
| T4 | 集合身份 3 处散装 | §5 | P2：建唯一 `collections.py` 登记处，ingest/recall 双消费 |
| T5 | 门禁重复收口处：retrieval_gate 自携 `_index/_golden/_modes/_baseline`，另有 probe_gate / task_eval probe / ragas adapters / diagnostics 5 套并存 | `evaluation/` 目录 | P3：门禁做索引+golden 唯一生产者，其余消费者化；被覆盖者标 deprecated |
| T6 | 双缓存（`routes._query_cache` vs `SemanticCache`）语义不同但同名易混 | §2 注 | 仅文档/命名澄清，不动逻辑 |
| T7 | 溯源走 metadata 字符串键（I6） | `_orchestrator.py` | 远期：抽 typed `Provenance` 字段；动它 dout 会牵动所有门禁断言，必须最后做 |
| T8 | 类型注解放宽 | `pyproject.toml:135` 自认 | 随 T1/T2 收敛后逐步收紧 |

## 9. 答辩三十秒版本

> 我们把 RAG 整理成"一个产品入口、一个测量入口、两条链、三层策略、一个出口"。
> Agent 走 `retrieve_for_task`（含 release），门禁/RAGAS/诊断走
> `aretrieve_evidence_raw`（原始包）保证测量口径；离线按六个分层集合入库 Chroma，在线六步主路径；
> 安全上 TaskPolicy 负责资格与披露，裁剪在 `apply_evidence_policy` 唯一出口发生；
> 相似度换算全仓单点、每步带漏斗指标与溯源标记，且由检索门禁与 RAGAS 复用生产路径闭环验证。
> 已知技术债（出口签约、文件粒度、门禁收口）已记入边界地图台账，属于工程收口问题，不影响架构正确性。
