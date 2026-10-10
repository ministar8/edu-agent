# 检索架构总览（as-built · V-2026-10-02）

> **本文定位**：**现状总览**，供论文第 3 章与代码定位使用。
> **不重复设计论证** —— 设计依据见 `RETRIEVAL_LAYER_DESIGN.md`（分层设计）、
> `RETRIEVAL_POLICY.md`（策略契约）；执行方案与实测见 `RETRIEVAL_PLAN.md`；
> 「不做清单」见 `RETRIEVAL_ROADMAP.md`。
> 实验数字见 `EXPERIMENTS.md`（§1–§19），可追溯锚点见 §18.0 / 标签 `V-2026-10-02`。

---

## 1. 一页架构

```
提问
 │
 ▼
┌──────────────────────── ① Task Policy（策略真源）─────────────────────────┐
│ rag/task_policy.resolve_task_policy(query)                                │
│   → schema/task_policy.TaskPolicy                                         │
│   task_mode · preferred_layers · excluded_layers · legacy_policy          │
│   exam_resources(资格) · answer_policy(披露) · depth · layer_policy_id     │
│   ↓ 两个下游消费者：                                                       │
│     eligibility_where()      → 召回侧 where（进不进候选池）                │
│     eligible_semantic_layers() → top-up 可补哪些层                        │
└───────────────────────────────────────────────────────────────────────────┘
 │
 ▼
┌──────────────────────── ② Retrieval Plan（计算预算）──────────────────────┐
│ rag/retrieval_plan.resolve_retrieval_plan(cat, depth)                     │
│   → RetrievalStrategy{ layer, route_type, depth }                         │
│   depth 决定 skip_decompose / skip_rerank / k 等**计算**参数（非安全）    │
└───────────────────────────────────────────────────────────────────────────┘
 │
 ▼
┌──────────────────────── ③ Pipeline（9 阶段编排）──────────────────────────┐
│ rag/pipeline.aretrieve_evidence()                                         │
│  classify → plan → decompose → 多路召回 → 去重/阈值 → rerank → HyDE        │
│           → window 展开 → finalize                                         │
│  多路召回 = 4 基础路由 + N 元数据路由（见 §3），RRF 加权融合                │
└───────────────────────────────────────────────────────────────────────────┘
 │
 ▼
┌──────────────────────── ④ Evidence Policy（release 唯一出口）─────────────┐
│ rag/evidence_policy                                                       │
│  finalize_with_layer_ranking : legacy 池策略 + preferred 排序 + 截断        │
│                               + **sufficiency 兜底**                       │
│  apply_evidence_policy       : 按资格/披露裁剪（答案、题号、解析）           │
│   → Evidence Pack（下发给 Agent/LLM 的唯一形态）                           │
└───────────────────────────────────────────────────────────────────────────┘
 │
 ▼
Agent（supervisor → 专家 agent）→ 回答 / 出题 / 批改
```

**三条不变量**（改动时必须守住）：

1. **策略只有一个真源**：`schema/task_policy.TaskPolicy`。召回、top-up、结果裁剪都从它派生，不各自维护模式表。
2. **资格与披露分离**：`exam_resources` 管**进不进候选池**（eligibility），`answer_policy` 管**给不给**（release）。二者都在召回与出包两处双保险。
3. **release 只在 `apply_evidence_policy` 发生**：BM25 / RRF / reranker 内**不做**权限判断。

---

## 2. 术语表（论文用词 ↔ 代码）

| 论文/文档用词 | 代码符号 | 位置 | 说明 |
|---|---|---|---|
| Task Policy | `TaskPolicy` | `schema/task_policy.py` | 一次检索的完整策略对象（唯一真源） |
| Task Mode | `task_mode` | 同上 | `learn / method / practice / grade / explain / verify` |
| Retrieval Plan | `RetrievalStrategy` | `rag/retrieval_plan.py` | `{layer, route_type, depth}` |
| Evidence Policy | `apply_evidence_policy` | `rag/evidence_policy.py` | release 唯一出口 |
| Evidence Pack | `FusedEvidence.text_evidences` | `rag/evidence.py` | 下发给模型的证据集合 |
| eligibility | `ExamResources` | `schema/task_policy.py` | L3 三种资源的候选资格（question/answer/paper） |
| release | `answer_policy` / `explanation_policy` | 同上 | 包内能否出现答案 / 解析 |
| preferred_layers | `preferred_layers` | 同上 | **软偏好**：top-up 补齐 + 排序提权；非硬过滤 |
| eligible layers | `eligible_semantic_layers()` | 同上 | **当前策略下允许进池的语义层**（资格派生） |
| legacy 池策略 | `legacy_policy` | 同上 | `exclude / fallback / include`（资产状态，非第四层） |
| pack sufficiency | `pack_nonempty_rate` | `scripts/task_mode_layer_policy.py` | 非空证据包占比 |

### 2.1 知识分层（★ legacy 不是"第四层"）

| 层 | `kb_depth` | `doc_role` | 目录 | live 索引条数 |
|---|---|---|---|---|
| **L1 基础** | `basic` | `textbook` | `knowledge/basic/` | **123** |
| **L2 进阶** | `advanced` | `method` | `knowledge/advanced/` | **98** |
| **L3 真题** | `exams` | `exam_item` / `exam_answer` | `knowledge/exams/` | **1359**（674 / 685） |
| **legacy 资产** | *(无)* | *(无)* | `knowledge/{四科,questions,learning_paths}/` | **2505** |

> `legacy` 是**资产质量/迁移状态**，不是第四知识层：它由 `legacy_policy` 管**入池**，
> **不进** `layer_weights`（schema 校验器强制）。
> 实测依据：真删 legacy 后层精度 0.396 → **1.000**（`EXPERIMENTS.md` §3）。

---

## 3. 召回层：路由与融合

### 3.1 路由清单

| 类别 | 路由 | 说明 |
|---|---|---|
| 基础路由（4） | `semantic` · `keyword_bm25` · `focus` · `expanded` | 全查询常开；`focus` 用 `extract_query_terms` 的短词串，`expanded` 用同义词扩展 |
| 元数据路由 | `concept_meta` · `comparison_meta` · `section_meta` · `code_meta` · `exercise_meta` · `answer_meta` · `structured_meta` · `formula_meta` · `table_meta` | 按 `content_type` 等元数据精准过滤，**命中率极高故权重高** |

> `merged_qa_meta`（Q&A 原子）**专用路由已撤销**（两轮净负）；merged_qa chunk 仍经基础路由被召回。

### 3.2 权重与融合

- 权重表：`rag/recall._ROUTE_WEIGHTS`（键 `(路由, 查询类别)`），**单一真源** `recall.ALL_ROUTES`。
- 融合：`rag/postprocess.weighted_rrf_merge` —— **加权 RRF**：`score = Σ w(route,cat) / (k_dyn + rank)`；
  `k_dyn` 随路由数放大（见 `_dynamic_rrf_k`）。
- ★ **Chroma 的 score 是余弦距离（越小越好）**。`routes._raw_search` 的向量分支**必须按 score 升序取前 k**
  —— V-2026-10-02 修的就是这里（此前按 `-score` 降序，等于返回最不相似的 k 条，见 `EXPERIMENTS.md` §18.2 #3）。

---

## 4. 证据层：从候选池到 Evidence Pack

```
候选池 ──dedup_same_section──► 同 section 去重（每节上限随类别浮动）
       ──score >= 有效阈值───► RRF 阈值过滤（空则保底 top-1）
       ──rerank() top_n─────► 重排截断（默认关）
       ──相对/绝对阈值───────► 双重过滤（兜底 top-2）
       ──sentence_window_expand / merge_window_into_anchors──► 最终证据
                        ↓
        finalize_with_layer_ranking（legacy 池策略 + preferred 排序 + sufficiency 兜底）
                        ↓
        apply_evidence_policy（资格 + 披露裁剪）→ Evidence Pack
```

**两个易错点（已在代码注释中固化）**：

1. **阈值可能高于 RRF 可达上限**：阈值按 `k=20` 标定，实际 `k_dyn` 在 13 条路由下为 36，量纲错配
   → 某些类别**必然返回空**。当前处理：只做「空结果保底 top-1」，**不调阈值**（见 `RETRIEVAL_ROADMAP.md` 不做清单）。
2. **top-up 必须继承资格**：`layer_recall.topup_preferred_layers` 只决定「从哪些层补」，
   **不实现资格规则**；`eligibility_where` 由 policy 提供（V-2026-10-02 修，§18.1）。

---

## 5. 模块 ↔ 代码 ↔ 文档

| 概念 | 代码文件 | 行数 | 关联文档 |
|---|---|---|---|
| 检索门面（对外入口） | `rag/retriever.py` | 465 | 本文 §3 |
| 阶段编排 | `rag/pipeline.py` | 1139 | 本文 §1 |
| 多路召回 / 单路由 | `rag/routes.py` | 393 | §3 |
| 路由构建 / 权重 / 学科推断 | `rag/recall.py` | 654 | §3 |
| 融合（RRF）/ 去重 / 窗口 | `rag/postprocess.py` | 688 | §4 |
| 重排 | `rag/reranker.py` | 271 | `RERANK_SWITCH_ANALYSIS.md` |
| 查询分类 / depth | `rag/query_classifier.py` | 457 | `RETRIEVAL_POLICY.md` §4 |
| 查询分解 | `rag/query_decomposer.py` | 195 | §4（零增益） |
| HyDE 兜底 | `rag/hyde.py` | 58 | §4（零增益） |
| 层 top-up | `rag/layer_recall.py` | 130 | §4 |
| 策略真源 | `schema/task_policy.py` | 255 | `RETRIEVAL_POLICY.md` |
| 策略解析 / 分类 | `rag/task_policy.py` | 221 | `RETRIEVAL_POLICY.md` §4 |
| 检索计划 | `rag/retrieval_plan.py` | 59 | 本文 §1 |
| 证据契约 | `rag/evidence.py` | 100 | 本文 §4 |
| release 出口 | `rag/evidence_policy.py` | 330 | `RETRIEVAL_LAYER_DESIGN.md` |
| 同义词 / 领域词 | `rag/synonyms.py` · `rag/rag_utils.py` | 493 · 269 | `EXPERIMENTS.md` §18.2 |
| 入库链 | `rag/ingest.py` · `loader` · `cleaner` · `splitter` · `enhancer` · `knowledge_tagger` | — | `KB_MASTER_DESIGN.md` |

---

## 6. 评测体系

### 6.1 两类口径（互补，不互替）

| 口径 | 回答 | 工具 |
|---|---|---|
| **检索指标** | 「证据**找没找到**」 | `kp_hit@k` / `kp_mrr`（章级）/ `cat@1`（学科级） |
| **生成指标** | 「找到的证据**有没有被用好**」 | RAGAS：faithfulness / context_precision / context_recall / answer_relevancy |

### 6.2 门禁 vs 诊断工具（★ 别混）

| 工具 | 索引 | 退出码 | 用途 |
|---|---|---|---|
| `evaluation.gates.retrieval_gate` | **临时索引** | 有（跌破基线即失败） | 回归门禁 |
| `evaluation.gates.probe_gate` | 临时索引 + 就绪屏障 | 有 | 小节级探针（拦后退、放前进） |
| `evaluation.diagnostics.candidate_trace` | **生产索引**、无就绪屏障 | **无** | 逐层归因诊断，**不是门禁** |

### 6.3 ★ 已知局限（更新 2026-10-10）

**(a) 门禁语料已含 L1/L2/L3，但走的是「通用路径」而非「生产入库脚本」。**

`retrieval_gate.build_index()` 自 2026-10-10 起遍历 `_INDEX_SOURCES`（basic / advanced /
exams / code + learning_paths），**已覆盖 L1/L2/L3** —— 本节此前记录的「门禁零 L1/L2/L3」
（只走 `rag.ingest.DEFAULT_CATEGORIES`）**已作废**。

但它复用的是**通用** `load_single_file → clean → split → enhance → tag` 链路，
**不调任何 `scripts/ingest_*.py`**；而生产四个科 / exams / code 集合恰恰由那些脚本入。
两边的解析与切分不同 ⇒ chunk 数**逐集合不等**：

| 集合 | 生产（`./chroma_db`） | 门禁（临时索引） |
|---|---|---|
| data_structure | 134 | 163 |
| computer_organization | 129 | 144 |
| operating_system | 105 | 121 |
| computer_network | 126 | 145 |
| exams | 1482 | 1619 |
| code_ds / code_os | 14 / 12 | 23 / 18 |
| learning_paths | 24 | 24（**唯一相等** —— `rag.ingest` 唯一真正入库的层） |

**含义**：门禁度量的是**通用链路**的回归，**不等于生产入库路径** ⇒ **改 `ingest_*.py`
（或任何只影响生产解析/切分）的改动，门禁测不到**。
→ ★ **2026-10-10 已修**：门禁改用 `rag.ingest_layers.build_all()`（与 `scripts/ingest_*.py`
**同源**），索引与生产**逐位相等**（134/129/105/126/1482/14/12）。上面这张对照表保留作背景。

**(b) 门禁不可复现：kp_mrr 噪声地板 ≈ ±0.003。**

同码同命令、跨进程重跑，`kp_mrr` 在 0.7591–0.7644 间抖动（`category_hit@*` 已稳）。
实测排除：chunk 内容确定、HNSW 图确定、同进程内确定；`PYTHONHASHSEED=0` 只减不消。
**收敛到 1 条 query**（`请出一道考查 TCP 序号与确认号的题。`）的 top-2 chunk 互换
（kp 排名 1↔2，折算 `0.5/156≈0.0032`）。性质是**并列打破**：RRF 主排序
（`postprocess.py:178`）已用 `_dedup_key` 做次级键、修好了 `cat@1`，但**下游仍有按
「分数」单键排序处**（如 `dedup_same_section`），其并列时依赖受**并发路由完成次序**
影响的输入顺序。⇒ **低于 ±0.003 的 `kp_mrr` 退化，门禁测不出**（① 的 cat@1 −0.0128
等**大**结论不受影响）。

> 该边界已同步写进代码注释（`retrieval_gate` 模块 docstring · `build_index` docstring ·
> `probe_gate` 模块 docstring），避免「门禁全绿 = 系统没退化」被误读。

---

## 7. 关键决策（V-2026-10-02）

完整表见 `EXPERIMENTS.md` §19。此处只列**影响架构**的三条：

| 决策 | 内容 | 依据 |
|---|---|---|
| **向量路由排序方向** | Chroma score 是距离 → **升序**取前 k | §18.2 #3（此前降序 = 返回最不相似） |
| **资格与 top-up 同源** | top-up 与主检索共用 `eligibility_where`；`eligible_layers` 兜底 preferred 全不合规 | §15.6 |
| **pack sufficiency 兜底** | 包内无合规项时从合规候选取前 k 回填 | §15.7 |

**未修（如实记录）**：L2 跨学科污染 40.0% · RRF 阈值高于可达上限 · rerank 收益符号不稳 ·
decompose/HyDE 零增益 · **门禁走通用路径 ≠ 生产入库 · 门禁 kp_mrr 噪声 ±0.003（本节 6.3）**。
