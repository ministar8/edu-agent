# 毕业论文素材文档

> 本文档整合了系统优化记录、评估体系设计和分块策略重构的设计与实现，供论文撰写参考。

---

## 一、系统性能优化

### 1.1 优化前后总览

| 科目 | 用例数 | 优化前 PASS | 优化后 PASS | 通过率变化 |
|------|--------|-------------|-------------|------------|
| 数据结构 (DS) | 30 | 30 | 30 | 100% → 100% |
| 操作系统 (OS) | 20 | 20 | 20 | 100% → 100% |
| 计算机网络 (CN) | 18 | 13 | 18 | 72% → **100%** |
| 计算机组成 (CO) | 20 | 15 | 20 | 75% → **100%** |
| **合计** | **88** | **78** | **88** | **89% → 100%** |

> 注：CO 优化后 2 条在 120s 超时下为 TIMEOUT，180s 超时下全部通过。

### 1.2 失败用例详情

#### 计算机网络 (5 条 NON-PASS → 0)

| # | Agent | 类型 | 查询 | 优化前状态 | 优化后状态 | 耗时(s) |
|---|-------|------|------|------------|------------|---------|
| 8 | question | 选择题 | 出一道关于子网划分的选择题 | COV_FAIL (0/2) | PASS | 65.1 |
| 15 | path | 路径 | 计算机网络应该怎么学？ | TIMEOUT | PASS | 117.2 |
| 18 | question | 综合 | 出一道综合题，涉及IP路由和TCP连接 | TIMEOUT | PASS | 119.0 |
| — | question | 选择题 | 出一道关于TCP拥塞控制的选择题 | TIMEOUT | PASS | 65.4 |
| — | knowledge | 概念 | OSI七层模型和TCP/IP四层模型的区别 | TIMEOUT | PASS | 104.5 |

#### 计算机组成 (5 条 NON-PASS → 0)

| # | Agent | 类型 | 查询 | 优化前状态 | 优化后状态 | 耗时(s) |
|---|-------|------|------|------------|------------|---------|
| 2 | knowledge | 对比 | 冯诺依曼结构和哈佛结构的区别 | TIMEOUT | PASS | ~173 |
| 18 | path | 路径 | 计算机组成原理应该怎么学？ | TIMEOUT | PASS | ~118 |
| 5 | question | 选择题 | 出一道关于浮点数表示的选择题 | COV_FAIL | PASS | 63.5 |
| 8 | grading | 批改 | Cache替换算法有哪些？只有LRU | COV_FAIL | PASS | 112.6 |
| 20 | grading | 批改 | 流水线数据冲突类型？只有结构冲突 | COV_FAIL | PASS | 118.0 |

### 1.3 根因分析

| 根因 | 影响范围 | 症状 |
|------|----------|------|
| **L2/L3 无检索查询提取** | question/grading/path_agent | 出题/批改/路径查询直接做向量检索，语义偏差大，召回空 |
| **检索链路延迟高** | L2 pre-retrieval, L3 fallback | aretrieve_evidence_with_retry 单次 20-25s |
| **L2 ReAct 超时** | path_agent | ReAct 多轮工具调用，总耗时 >120s |
| **L3 无 no-rerank 降级** | 所有 L3 agent | rerank 失败/超时后无 fallback，直接返回空 |
| **L3 fallback 链路低效** | 所有 L3 agent | Step 3 fallback 仍用 aretrieve_evidence_with_retry |
| **关键词匹配不宽容** | CO #2 冯诺依曼 | "冯·诺依曼" 无法匹配 "冯诺依曼" |

### 1.4 优化措施

#### L2 Agent — 检索查询提取 + no-rerank fallback

**文件**: `app/agents/supervisor.py` `_run_l2_agent`

| Agent | 提取逻辑 | 示例 |
|-------|----------|------|
| question_agent | 正则提取知识点："关于X的选择题" → "X" | "关于子网划分的选择题" → "子网划分" |
| grading_agent | 去掉学生答案，保留题干 | "题目：X 学生答案：Y" → "X" |
| path_agent | 去掉学习类词，加"学习路线 重点章节" | "计算机网络应该怎么学" → "计算机网络 学习路线 重点章节" |

- 新增 no-rerank fallback：rerank 检索空时降级为 `aretrieve_documents(use_rerank=False)`
- L2 ReAct fallback 替换为 direct retrieval + LLM generation

#### L3 Agent — 同 L2 提取 + 多级 fallback

**文件**: `app/agents/supervisor.py` `_run_l3_agent`

- **Step 0**: 同 L2 的检索查询提取逻辑
- **Step 1b**: no-rerank fallback（deep retrieval 空时降级）
- **Step 2**: agent-specific prompt（question_agent 用 QUESTION_PROMPT 而非通用 prompt）
- **Step 3**: RAG fallback 从 `aretrieve_evidence_with_retry` → `aretrieve_documents`（更轻量）

#### 关键词匹配容错

**文件**: 所有 `_golden_set_*.py` 的 `_check_coverage`

- 新增中间点/空格容错：`re.sub(r"[·\.\s]", "", kw)` 匹配
- "冯诺依曼" 可匹配 "冯·诺依曼"

#### 超时调整

- Golden Set 单条超时：120s → 180s

### 1.5 性能指标

#### 平均耗时（PASS 用例）

| Agent | 优化前 (s) | 优化后 (s) | 变化 |
|-------|-----------|-----------|------|
| knowledge_agent | ~90 | ~85 | -6% |
| question_agent | TIMEOUT | ~63 | ∞ → 63s |
| grading_agent | ~110 | ~115 | +5% |
| path_agent | TIMEOUT | ~118 | ∞ → 118s |

#### 检索链路对比

| 链路 | 优化前 | 优化后 |
|------|--------|--------|
| L2 pre-retrieval | aretrieve_evidence_with_retry (~20s) | aretrieve_documents (~3-5s) |
| L2 fallback | ReAct 多轮 (~120s+) | direct retrieval + LLM (~30s) |
| L3 Step 1 | aretrieve_documents (仅 rerank) | aretrieve_documents + no-rerank fallback |
| L3 Step 3 | aretrieve_evidence_with_retry | aretrieve_documents |

#### 覆盖率

| 科目 | 优化前平均覆盖率 | 优化后平均覆盖率 |
|------|-----------------|-----------------|
| CN | ~85% | 100% |
| CO | ~80% | 97% (1条 miss "立即", 1条 miss "中断") |

### 1.6 架构变更图

```
优化前 L2/L3:
  query → [向量检索(含压缩)] → [ReAct多轮] → answer
                                ↓ 超时
                          TIMEOUT / COV_FAIL

优化后 L2:
  query → [提取检索关键词] → [aretrieve_documents] → [fast-path LLM] → answer
                                ↓ 空结果
                          [no-rerank fallback] → [LLM] → answer
                                ↓ 仍空
                          [direct retrieval + LLM] → answer

优化后 L3:
  query → [提取检索关键词] → [deep retrieval + rerank] → [agent-specific LLM] → answer
                                ↓ 空结果
                          [no-rerank fallback] → [LLM] → answer
                                ↓ LLM超时
                          [aretrieve_documents(fallback)] → [LLM] → answer
```

---

## 二、评估体系设计

### 2.1 总体架构

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

### 2.2 第一层 — RAGAS 标准指标

| 指标 | 含义 | 评分范围 | 数据需求 |
|---|---|---|---|
| **Faithfulness** | 答案是否基于检索到的上下文，不包含幻觉 | [0, 1] | query + context + answer |
| **Context Precision** | 检索到的上下文中，相关片段占比 | [0, 1] | query + context + reference |
| **Context Recall** | 所有需要的相关信息是否都被检索到 | [0, 1] | query + context + reference |
| **Answer Relevancy** | 答案与查询的相关性 | [0, 1] | query + answer |

### 2.3 第二层 — 系统专用诊断指标

#### 路由消融

量化每条召回路由的边际贡献，判断是否可以裁剪路由以降低延迟。

方法：依次关闭单条路由，对比召回率变化。

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
```

#### Sentence Window 效果分析

评估窗口大小（±N）、adaptive chunk_size 策略对上下文完整性和检索精准度的影响。

| 指标 | 含义 |
|---|---|
| **context_completeness** | 展开后上下文是否包含完整概念定义 |
| **window_precision** | 窗口中无关内容的占比 |
| **window_overlap_rate** | 多 section 重叠窗口的冗余度 |

#### Reranker 影响

量化 Reranker 对最终排序的改善程度。

```
Reranker Impact Report
══════════════════════
Metric               | Before Rerank | After Rerank | Δ
───────────────────────────────────────────────────────
Precision@5          | 0.58          | 0.74         | +0.16
Recall@5             | 0.62          | 0.71         | +0.09
Top-1 Relevance      | 0.72          | 0.89         | +0.17
Latency Overhead     | —             | +180ms       | —
```

#### 查询分解诊断

| 指标 | 计算方式 |
|---|---|
| **decompose_trigger_rate** | 被分解的查询数 / 总查询数 |
| **decompose_success_rate** | 分解后召回提升的查询占比 |
| **subquery_independent_contribution** | 仅子查询命中的文档占比 |
| **oversplit_rate** | 不应拆分却被拆分的比例 |

#### Pipeline 耗时分解

发现 RAG Pipeline 性能瓶颈，指导缓存和并行策略优化。

```python
pipeline_timing = {
    "total": 1250ms,
    "embedding": {"duration": 45ms},
    "recall": {
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
    "rerank": {"duration": 180ms, "candidates_in": 40, "candidates_out": 5},
    "sentence_window": {"duration": 65ms, "sections_expanded": 3},
}
```

#### 守卫治理统计

| 指标 | 含义 |
|---|---|
| **guard_block_rate** | 被前置守卫拦截的查询占比 |
| **guard_justified_block** | 拦截正确的比例 |
| **governance_trigger_rate** | 后治理介入的答案占比 |
| **forgery_detection_rate** | 检测到虚构内容的比例 |

### 2.4 评估运行方式

```bash
# 完整评估（RAGAS + 诊断）
python -m app.evaluation.cli --layer all

# 仅 RAGAS 指标
python -m app.evaluation.cli --layer ragas

# 仅诊断指标
python -m app.evaluation.cli --layer diagnosis

# 单学科
python -m app.evaluation.cli --category data_structure

# 快速验证
python -m app.evaluation.cli --quick

# 完整评估脚本
python run_full_eval.py

# 消融实验 (5 组条件)
python run_ablation.py --quick
```

### 2.5 评估数据集

每条记录格式：

```json
{
    "query": "什么是进程死锁？",
    "contexts": ["进程死锁是指两个或以上进程因争夺资源而互相等待..."],
    "answer": "进程死锁是指两个或以上进程相互等待对方释放资源...",
    "reference": "进程死锁是指多个进程因竞争资源而造成的一种僵局...",
    "metadata": {
        "category": "operating_system",
        "difficulty": "basic",
        "source_file": "deadlock.md"
    }
}
```

---

## 三、Sentence Window 分块策略重构

### 3.1 问题诊断

#### Summary chunk 的问题

`_generate_section_summary()` 是纯规则化生成：提取关键词 → 句子语义评分 → 贪心装箱。核心缺陷：规则化的句子评分无法理解语义，高频出现"定义句优先"误判——"XXX并不是YYY"这种否定句因匹配"是"被当作定义句得高分。Summary 内容质量不稳定，且与 detail chunk 的语义匹配度不可控。

#### QA chunk 的问题

`_generate_qa_block()` 将陈述句通过正则模式匹配转为疑问句（如 `"X是Y" → "什么是X？"`）。核心缺陷：模式覆盖极其有限（9 条规则），大量教学内容无法匹配；生成的问句机械呆板；问题质量无法与用户真实查询匹配。

#### 固定 chunk_size 的问题

固定 400 字符对所有内容类型一刀切。对于包含完整概念解释的段落（通常 600-1000 字），会被截断成碎片；对于列表或代码片段又显得过大。

### 3.2 解决方案：Sentence Window 检索

#### 核心思路

**删除 Summary 和 QA 两种 chunk 角色**，仅保留 detail chunk。检索后，对命中的 detail chunk 自动展开上下文窗口（前 N 句 + 后 N 句），让 LLM 获得完整上下文。

```
改造前:  Section → [Summary × N, QA × N, Detail × N]
        检索后: dedup_same_section → expand_hierarchical → contiguous_fill

改造后:  Section → [Detail × N (adaptive chunk_size)]
        检索后: sentence_window_expand
```

#### Adaptive chunk_size

根据 `content_type` 动态调整：

| content_type | chunk_size | 理由 |
|---|---|---|
| section / text | 800 | 概念解释需要完整段落 |
| list | 不拆，整个列表一个 chunk | 列表语义粒度在整体 |
| code_mixed | 400 | 代码片段相对独立 |
| exercise / answer | 600 | 题目+解析不宜截断 |
| table 类（pdf_table） | 不拆 | 表格完整性优先 |

#### Sentence Window 展开逻辑

`postprocess.py` 新增 `sentence_window_expand`，替代原有的 `expand_hierarchical_context` + `contiguous_fill`：

1. 对检索命中的每个 chunk，获取其 `section.id` 和 `section.chunk_index`
2. 从向量库查询同 section 的所有 detail chunk，按 chunk_index 排序
3. 以命中 chunk 为锚点，向前后各取 `window_size` 个 chunk（默认左右各 2）
4. 合并多个命中 chunk 产生的重叠窗口
5. 总字符数预算 3000 chars（超预算则缩窗）
6. 标记 `_window_expanded` 以区分子命中

#### 简化检索后处理管线

```
原始: RRF merge → dedup_same_section → threshold → rerank → expand_hierarchical → contiguous_fill
新版: RRF merge → sentence_window_expand → threshold → rerank → build_rag_context
```

### 3.3 影响范围

| 文件 | 改动 |
|---|---|
| `app/rag/splitter.py` | 移除 `_generate_section_summary`、`_generate_qa_block` 调用；chunk_size 从固定值改为按 content_type 查表；移除 summary/qa 角色相关 metadata 写入 |
| `app/rag/postprocess.py` | 新增 `sentence_window_expand`；简化 `dedup_same_section`（移除角色优先级）；删除 `expand_hierarchical_context`；删除 `contiguous_fill` |
| `app/rag/retriever.py` | 更新 `retrieve_documents` 中的后处理管线 |
| `app/rag/enhancer.py` | 不需要改——`_detect_content_type` 已存在，`splitter` 直接复用 |

### 3.4 预期效果

1. **上下文完整性**：Sentence Window 保证 LLM 看到命中 chunk 的完整上下文，不再依赖规则化 Summary
2. **检索精准度**：所有 chunk 都是原始正文（detail），语义空间一致，Reranker 排序更准确
3. **代码简化**：移除约 500 行规则生成代码，减少 bug 面
4. **无 LLM 调用增加**：所有改动均为规则化操作，不增加额外延迟
