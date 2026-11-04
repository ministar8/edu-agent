# RAG 包导航（代码侧 · 与论文第 3 章对齐）

> **只讲主路径与命名，不重复设计论证。**  
> 设计 / 策略契约 / 实验数字见 `docs/`：`ARCHITECTURE_RETRIEVAL.md` · `RETRIEVAL_LAYER_DESIGN.md` · `RETRIEVAL_POLICY.md` · `EXPERIMENTS.md`。

## 主路径（6 步，答辩与读码共用）

```text
① 查询理解   normalize → classify → TaskPolicy + RetrievalPlan →（可选）decompose
② 多路召回   semantic + BM25 + focus + expanded + 元数据路由（并发）
③ 融合       加权 RRF（按路由秩，不拼原始分）
④ 过滤重排   同节去重 → 分数阈值 →（可选）rerank →（不足）HyDE / 窗口 / top-up
⑤ 出包       finalize 层排序 + 充分性兜底 → apply_evidence_policy（资格/披露）
⑥ 缓存验证   写语义缓存 + 规则 verifier + 指标
```

**两条显式入口**：

| 入口 | 用途 | 是否裁剪 |
|---|---|---|
| `retrieval.api.retrieve_for_task` | 产品路径（Agent） | ✅ finalize + apply |
| `retrieval.retriever.aretrieve_evidence_with_retry` | 检索质量测量 / 实验 | ❌ 原始包 |

## 命名对照（最容易混的三对）

| 你想找的 | 用这个词 | 代码 | 不要和谁混 |
|---|---|---|---|
| 门面 / 对外 API | **retriever** | `retrieval/retriever.py` | 不是 `routes`（那是单路执行） |
| 产品检索入口 | **retrieve_for_task** | `retrieval/api.py` | 不是测量入口（那里不裁剪） |
| 阶段编排（9 步流水线） | **pipeline** | `retrieval/pipeline/` | 不是「论文里的 Plan」 |
| 论文里的 Plan | **RetrievalPlan** | `retrieval/retrieval_plan.py` | 与 TaskPolicy 不是一回事 |
| 策略真源（安全/披露） | **TaskPolicy** | `schema/task_policy.py` + `retrieval/task_policy.py` | 不管 k / coarse_k |
| 路由**怎么拼**（查什么） | **recall** | `retrieval/recall.py` | 不执行检索 |
| 路由**怎么跑**（并行查） | **routes** | `retrieval/routes.py` | 不负责 RRF 融合 |
| 证据包 | **FusedEvidence / Evidence Pack** | `retrieval/evidence.py` | release 只在 `evidence_policy` |

## 三层策略（职责一句话）

| 层 | 管什么 | 典型字段 |
|---|---|---|
| **TaskPolicy** | 进不进池、包里能不能带答案/题号 | `exam_resources` · `answer_policy` · `preferred_layers` |
| **RetrievalPlan / depth** | 算多少、跳不跳分解/重排准备 | `k` · `coarse_k` · `skip_decompose` · `skip_rerank` |
| **部署开关** | 这个环境是否真跑 rerank 等 | `settings.RERANK_ENABLED`（见 `docs/RERANK_SWITCH_ANALYSIS.md`） |

★ `use_rerank` **参数** ≠ 是否执行重排：它表示「按重排口径准备候选（影响 coarse_k）」；真正是否调用 `rerank()` 还看 `depth.skip_rerank` 与 `RERANK_ENABLED`。

## 模块地图（按主路径顺序）

| 步 | 模块 | 一句话 |
|---|---|---|
| ① | `pipeline` → `query_classifier` / `task_policy` / `retrieval_plan` / `query_decomposer` | 理解与预算（pipeline 独占） |
| ② | `recall`（拼路由）+ `routes`（跑路由）+ `bm25` / `common/embeddings` | 多路候选 |
| ③ | `postprocess`（`weighted_rrf_merge` 等） | 秩融合 |
| ④ | `postprocess` 去重阈值 · `reranker` · `hyde` · `layer_recall` | 收紧候选 |
| ⑤ | `evidence` + `evidence_policy` + `api.retrieve_for_task` | 唯一下发形态（产品门面含 release） |
| ⑥ | `semantic_cache` · `verifier` · `common/metrics` | 缓存与可观测 |

离线入库（不在请求路径）：`ingest.py` / `ingest_layers/` + `chunking/` → Chroma。

## 读代码顺序（建议）

1. `retrieval/api.py` + `retrieval/retriever.py`（两条入口）  
2. `retrieval/pipeline/__init__.py` + `_orchestrator.py`（阶段顺序）  
3. `retrieval/recall.py` vs `routes.py`（拼 vs 跑）  
4. `retrieval/evidence_policy.py`（release 唯一出口）  
5. `docs/ARCHITECTURE_RETRIEVAL.md`（术语表 + 路由清单 + 层）
