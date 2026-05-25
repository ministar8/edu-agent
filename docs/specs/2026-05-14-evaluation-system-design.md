# 两层级全面评估体系 — 设计文档

**日期**: 2026-05-14
**状态**: 草案

---

## 1. 总体架构

```
┌─────────────────────────────────────────────────────┐
│                 第一层 — RAGAS 标准指标               │
│                                                     │
│  Faithfulness · Context Precision · Context Recall   │
│  Answer Relevancy                                    │
│                                                     │
│  目的：与行业基准对标，衡量 RAG 系统基础质量            │
├─────────────────────────────────────────────────────┤
│                 第二层 — 系统专用诊断指标               │
│                                                     │
│  路由消融 · Sentence Window 分析 · Reranker 影响      │
│  查询分解诊断 · Pipeline 耗时分解 · 守卫治理统计       │
│                                                     │
│  目的：定位瓶颈，指导架构优化方向                       │
└─────────────────────────────────────────────────────┘
```

### 评估数据流

```
测试查询集 → RAG Pipeline → 原始响应
    │                           │
    │                           ▼
    │                    ┌──────────────┐
    │                    │  答案评估     │
    └───→ Ground Truth ─→│  RAGAS 计算   │ → Layer 1 报告
                         │  诊断计算     │ → Layer 2 报告
                         └──────────────┘
```

---

## 2. 第一层 — RAGAS 标准指标

### 2.1 指标定义

| 指标 | 含义 | 评分范围 | 数据需求 |
|---|---|---|---|
| **Faithfulness** | 答案是否基于检索到的上下文，不包含幻觉 | [0, 1] | query + context + answer |
| **Context Precision** | 检索到的上下文中，相关片段占比 | [0, 1] | query + context + reference |
| **Context Recall** | 所有需要的相关信息是否都被检索到 | [0, 1] | query + context + reference |
| **Answer Relevancy** | 答案与查询的相关性 | [0, 1] | query + answer |

### 2.2 实现方式

```python
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    context_precision,
    context_recall,
    answer_relevancy,
)

# 单次评估
result = evaluate(
    dataset=eval_dataset,  # 含 query, contexts, answer, reference
    metrics=[faithfulness, context_precision, context_recall, answer_relevancy],
)

# 聚合报告
{
    "faithfulness": {"mean": 0.87, "std": 0.12, "p50": 0.91, "p90": 0.98},
    "context_precision": {"mean": 0.72, ...},
    "context_recall": {"mean": 0.65, ...},
    "answer_relevancy": {"mean": 0.81, ...},
}
```

### 2.3 评估数据集

**来源**：从知识库文档自动生成 + 人工校验

```
backend/data/evaluation/
├── datasets/
│   ├── data_structure.jsonl      # 数据结构学科
│   ├── operating_system.jsonl    # 操作系统学科
│   └── mixed.jsonl               # 跨学科混合
├── results/
│   └── ragas_report.json         # 最新评估报告
└── config.yaml                   # 评估参数配置
```

**每条记录格式**：

```json
{
    "query": "什么是进程死锁？",
    "contexts": [
        "进程死锁是指两个或以上进程因争夺资源而互相等待...",
        "死锁产生的四个必要条件：互斥、占有并等待..."
    ],
    "answer": "进程死锁是指两个或以上进程相互等待对方释放资源...",
    "reference": "进程死锁是指多个进程因竞争资源而造成的一种僵局...",
    "metadata": {
        "category": "data_structure",
        "difficulty": "basic",
        "source_file": "deadlock.md"
    }
}
```

### 2.4 评估方式

```bash
# 全量评估
python -m app.evaluation.run --layer ragas --dataset all

# 单学科评估
python -m app.evaluation.run --layer ragas --category data_structure

# A/B 对比（旧分块 vs Sentence Window）
python -m app.evaluation.run --layer ragas --baseline old_chunking
```

---

## 3. 第二层 — 系统专用诊断指标

### 3.1 路由消融

**目的**：量化每条召回路由的边际贡献，判断是否可以裁剪路由以降低延迟。

**方法**：

```python
# 依次关闭单条路由，对比召回率变化
routes = ["semantic", "keyword_bm25", "focus", "expanded", "kg_expand"]

for route_to_disable in routes:
    enabled = [r for r in routes if r != route_to_disable]
    result = run_retrieval(query, enabled_routes=enabled)
    # 对比全量路由的结果
    recall_drop = full_recall - result.recall
```

**输出**：

```
Route Ablation Report
══════════════════════
Route Disabled     | Recall@5 Δ | Precision@5 Δ | Latency Δ
─────────────────────────────────────────────────────────
semantic           | -0.35      | -0.28         | -120ms
keyword_bm25       | -0.08      | -0.03         | -45ms
focus              | -0.05      | -0.04         | -15ms
expanded           | -0.12      | -0.10         | -60ms
kg_expand          | -0.03      | -0.02         | -200ms

结论：kg_expand 边际收益最低但延迟最高，考虑按查询类型选择性启用
```

**适配 Sentence Window 改造**：路由消融在 Sentence Window 架构下依然适用，因为 routing 层在 recall 阶段执行，早于 post-processing 的 window 展开。

### 3.2 Sentence Window 效果分析

**目的**：评估窗口大小（±N）、adaptive chunk_size 策略对上下文完整性和检索精准度的影响。

**方法**：

```python
configs = [
    {"window_size": 0, "chunk_size": 400},   # 无展开，旧 chunk_size
    {"window_size": 1, "chunk_size": 400},   # 小窗口
    {"window_size": 2, "chunk_size": 800},   # 推荐配置
    {"window_size": 3, "chunk_size": 800},   # 大窗口
]

for cfg in configs:
    result = eval_pipeline(query, **cfg)
    report.record(cfg, result.metrics)
```

**输出指标**：

| 指标 | 含义 |
|---|---|
| **context_completeness** | 展开后上下文是否包含完整概念定义 |
| **window_precision** | 窗口中无关内容的占比 |
| **window_overlap_rate** | 多 section 重叠窗口的冗余度 |
| **adaptive_hit_distribution** | 各 content_type（text/section/list/code_mixed）的命中比例 |

**对比维度**（消融实验）：

| 变量 | 值 | 测量指标 |
|---|---|---|
| window_size | 0, 1, 2, 3 | Context Precision/Recall |
| chunk_size (text/section) | 400, 600, 800, 1000 | 上下文完整性、句子截断率 |
| chunk_size (list/table) | 不拆 vs 拆 | 列表语义完整性 |
| content_type 检测 | 开启 vs 关闭 | 不同类型 chunk 命中率变化 |

### 3.3 Reranker 影响

**目的**：量化 Reranker（DashScope gte-rerank）对最终排序的改善程度。

**方法**：

```python
# 对同一批候选，对比 Reranker 前/后
before_rerank = retrieve(query, use_rerank=False)
after_rerank = rerank(query, before_rerank)

metrics = {
    "top1_changed": after_rerank[0] != before_rerank[0],
    "top5_recall_improve": precision_delta(before_rerank, after_rerank),
    "negative_filtered": count_removed(before_rerank, after_rerank),
    "rerank_latency": rerank_time,
}
```

**输出**：

```
Reranker Impact Report
══════════════════════
Metric               | Before Rerank | After Rerank | Δ
───────────────────────────────────────────────────────
Precision@5          | 0.58          | 0.74         | +0.16
Recall@5             | 0.62          | 0.71         | +0.09
Top-1 Relevance      | 0.72          | 0.89         | +0.17
───────────────────────────────────────────────────────
Latency Overhead     | —             | +180ms       | —
```

### 3.4 查询分解诊断

**目的**：评估查询分解（Decomposition）的触发准确率和子查询的独立贡献。

**指标**：

| 指标 | 计算方式 |
|---|---|
| **decompose_trigger_rate** | 被分解的查询数 / 总查询数 |
| **decompose_success_rate** | 分解后召回提升的查询占比 |
| **subquery_independent_contribution** | 仅子查询命中的文档占比 |
| **oversplit_rate** | 不应拆分却被拆分的比例 |

**输出**：

```
Query Decomposition Report
═══════════════════════════
Total Queries: 200
Decomposed: 45 (22.5%)
  - Success: 38 (84.4%)
  - Oversplit: 3 (6.7%)

Subquery Impact:
  - Only sub-query contributed: 12 queries (26.7%)
  - Original dominated: 26 queries (57.8%)
  - Equal contribution: 7 queries (15.6%)
```

### 3.5 Pipeline 耗时分解

**目的**：发现 RAG Pipeline 性能瓶颈，指导缓存和并行策略优化。

**监控点**（在 retriever.py 中已有 metrics.emit，需要补全缺失的埋点）：

```python
pipeline_timing = {
    "total": 1250ms,
    "embedding": {              # 查询 embedding
        "duration": 45ms,
        "p50": 42ms, "p95": 60ms,
    },
    "recall": {                 # 多路召回（含所有路由）
        "duration": 350ms,
        "routes": {
            "semantic": {"hits": 15, "time": 80ms},
            "keyword_bm25": {"hits": 8, "time": 120ms},
            "focus": {"hits": 6, "time": 30ms},
            "expanded": {"hits": 12, "time": 50ms},
            "kg_expand": {"hits": 5, "time": 70ms},
        },
    },
    "rrf_merge": {"duration": 2ms},
    "dedup": {"duration": 1ms},
    "rerank": {                 # Reranker 调用
        "duration": 180ms,
        "candidates_in": 40,
        "candidates_out": 5,
    },
    "sentence_window": {        # Window 展开
        "duration": 65ms,
        "sections_expanded": 3,
        "chunks_added": 7,
    },
    "rag_context": {"duration": 1ms},
}
```

**需补充的埋点**（当前缺失）：

- `postprocess.py` 中 `sentence_window_expand` 的耗时
- `bm25_search` 的逐 term 耗时
- KG 展开的独立耗时

### 3.6 守卫治理统计

**目的**：评估反幻觉体系（前置守卫 + 后置治理）的实际拦截率与误伤率。

**前置检索守卫**（`retrieval_guard.py`）：

| 指标 | 含义 |
|---|---|
| **guard_block_rate** | 被守卫拦截的查询占比 |
| **guard_justified_block** | 拦截正确的比例（确实应拦截） |
| **guard_false_positive** | 误拦率（本可正常检索） |

**后置答案治理**（`answer_governance.py`）：

| 指标 | 含义 |
|---|---|
| **governance_trigger_rate** | 治理介入的答案占比 |
| **governance_downgrade_rate** | 被降级处理的比例 |
| **forgery_detection_rate** | 检测到虚构内容的比例 |
| **governance_false_positive** | 治理误判率 |

---

## 4. 评估运行器设计

### 4.1 命令行接口

```bash
python -m app.evaluation.run --help

# 用法
python -m app.evaluation.run --layer all                    # 全量评估
python -m app.evaluation.run --layer ragas                  # 仅 RAGAS
python -m app.evaluation.run --layer diagnosis --diagnostics route_ablation,rerank  # 指定诊断项
python -m app.evaluation.run --layer all --category data_structure  # 单学科
python -m app.evaluation.run --layer all --baseline old     # A/B 对比
python -m app.evaluation.run --layer all --output json      # JSON 输出
```

### 4.2 报告格式

**JSON 报告**（`results/` 目录）：

```json
{
    "evaluation_id": "2026-05-14-v1",
    "timestamp": "2026-05-14T10:00:00Z",
    "layer1": {
        "faithfulness": {"mean": 0.87, "std": 0.12, "n": 200},
        "context_precision": {"mean": 0.72, ...},
        "context_recall": {"mean": 0.65, ...},
        "answer_relevancy": {"mean": 0.81, ...},
    },
    "layer2": {
        "route_ablation": {...},
        "sentence_window": {...},
        "reranker_impact": {...},
        "query_decomposition": {...},
        "pipeline_timing": {...},
        "guard_governance": {...},
    },
    "config": {
        "dataset": "mixed.jsonl",
        "layer": "all",
        "category": null,
        "baseline": null,
    }
}
```

**Markdown 摘要**（同时输出到 STDOUT + 文件）：

```
# Evaluation Report — 2026-05-14

## Layer 1: RAGAS Metrics
- Faithfulness: 0.87 (±0.12)
- Context Precision: 0.72 (±0.18)
- Context Recall: 0.65 (±0.21)
- Answer Relevancy: 0.81 (±0.14)

## Layer 2: Diagnostics

### Route Ablation
[table]

### Sentence Window Effect
[table]

### Reranker Impact
[table]

### Pipeline Timing
[breakdown]

## Verdict
Overall: GOOD. Context Recall needs improvement.
Suggested action: Increase window_size from 2→3, or expand ef_search from 100→150.
```

### 4.3 目录结构

```
backend/app/evaluation/
├── __init__.py
├── run.py                  # CLI 入口
├── config.py               # 评估参数配置
├── datasets.py             # 数据集加载与管理
├── layer1_ragas.py         # RAGAS 指标计算
├── layer2_diagnosis.py     # 系统诊断指标计算
├── reporters/
│   ├── __init__.py
│   ├── json_reporter.py    # JSON 输出
│   └── markdown_reporter.py # Markdown + 控制台输出
└── utils.py                # 辅助函数
```

---

## 5. 实现优先级

| 优先级 | 模块 | 工作量 | 依赖 |
|---|---|---|---|
| P0 | 评估数据集生成（自动 + 人工） | 2d | 知识库文档 |
| P0 | Layer 1: RAGAS 指标集成 | 1d | ragas 库 |
| P1 | Layer 2: Pipeline 耗时分解 | 0.5d | 现有 metrics 埋点补充 |
| P1 | Layer 2: Sentence Window 效果分析 | 1d | 多配置消融 |
| P1 | Layer 2: Reranker 影响 | 0.5d | 无 |
| P2 | Layer 2: 查询分解诊断 | 1d | 无 |
| P2 | Layer 2: 路由消融 | 1d | 路由抽象化 |
| P2 | Layer 2: 守卫治理统计 | 1d | 守卫/治理模块 |
| P2 | JSON + Markdown 报告输出 | 0.5d | 无 |

---

## 6. 与现有评估代码的关系

当前项目已有 `metrics.py` + `trace.py` 用于查询级监控。评估体系是对此的补充，而非替代：

| 层面 | metrics.py / trace.py | 评估体系 |
|---|---|---|
| 定位 | 生产监控 | 离线诊断 |
| 数据 | 单次查询 | 固定数据集批量评估 |
| 指标 | 延迟、命中率、角色分布 | RAGAS 质量指标 + 诊断消融 |
| 输出 | JSONL 日志 | 聚合报告 + 对比 |

两者共用 metrics.emit 的埋点数据，评估体系在此基础上叠加质量分析和消融实验。
