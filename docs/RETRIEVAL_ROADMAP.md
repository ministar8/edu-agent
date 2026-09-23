# EDU-Agent 检索层优化路线图

> **定位**：与工程指导报告互补 —— 后者管**工程质量**（已于 2026-09-23 归档到
> `../edu-agent-engineering-archive/batch1/docs_ENGINEERING.md`），本文件管**检索效果与产品功能**。
> **依据**：2026-09-23 全量代码核实（评测口径 / 配置一致性 / 前端能力面，均为实测非估算）。
> **执行约定**：每个任务给「改哪里 + 验收标准 + 风险」；验收标准必须是**可判定的数字或可观测行为**。

---

## 0. 结论先行

**方向成立**：系统 90% 的产品价值来自检索链，把重心从工程侧搬到检索效果是对的。

**但有两个前置条件必须先解决，否则后续全是盲调：**

| # | 前置条件 | 现状（实测） |
|---|---|---|
| 1 | **度量口径断层** | 门禁只测「学科类目」（4 选 1），且 `category_hit_at_k = 1.0000`（40/40 全中）**已饱和**；答案级度量（RAGAS）**从未跑过**（`evals/results/` 目录不存在） |
| 2 | **本机链路 ≠ 生产链路** | `.env` 是 `RERANK_ENABLED=false`，但 `settings.py:116` 默认 `True`、`.env.example:51` 是 `true`、`agents/tools.py:152` **硬编码 `use_rerank=True`** |

**工程侧的定位调整（不是停止）**：覆盖率 36% → 72.3%、`retriever` 7% → 65.6%、6 个 0% 模块清零、质量门禁 + 结构棘轮在位 —— 工程侧**已经从「阻塞项」降级为「服务项」**。
剩余的是**规模债**（8 文件 >600 行 / 53 函数 >60 行），它不阻塞检索迭代，因为安全网已经建好。
**处置方式见 §4：不设独立路线，只在改动触达处偿还。**

---

## 1. 为什么必须先装仪表盘

### 1.1 现有门禁测不出「答案更准」

`src/evaluation/retrieval_gate.py` 的设计取舍第 1 条**自己写着**：

> 指标锚定在「学科类目」而不是「具体 chunk_id」

实测基线（`evals/retrieval_baseline.json`）：

| 指标 | 实测值 | 解读 |
|---|---|---|
| `category_hit_at_k` | **1.0000** | **40/40 全部命中，零余量** |
| `category_hit_at_1` | 0.9500 | 只有 2/40 未中 |
| 随机基线 | 0.2500 | 4 选 1 |

**结论**：在学科粒度上，任何改动的效果都测不出来；测出来了也大概率是噪声。

### 1.2 假 embedding 上的「改善」已被证明是伪影

归档报告 `../edu-agent-engineering-archive/batch1/docs_ENGINEERING.md` backlog #34 的四条路由对照实验：

- 放宽 BM25 候选池在**假路由**上 `hit@1` +5pp
- 在**真实 embedding 路由**上**收益为零 —— 连小数位都不变**

**推论**：CI 默认路由（假 embedding）给出的任何涨跌都不可信。**取舍必须真实路由复验。**

### 1.3 答案级度量完全空白

- `evals/results/` ★ **状态已更新（09-23 22:00）**：目录已建立，含 `ragas_probe.json` 与
  `ragas_smoke.json` 两份冒烟产物；**全量（40 条）仍未跑**
- `.github/workflows/test.yml` 里**没有 RAGAS job**（★ `.github/` 整体已于 09-23 归档，本工作区无 CI）
- `src/evaluation/cli.py` 需要 `uv sync --group eval` + 真实 LLM，纯手工

**所以「让检索出来的答案更准确」目前没有可操作的定义。**

---

## 2. 阶段 0 — 装上仪表盘（阻塞后续一切）

### T0.1 对齐本地与生产链路

| 项 | 内容 |
|---|---|
| 改哪里 | `.env`（`RERANK_ENABLED=false` → 跟随生产）；或在评测脚本里显式 `GATE_USE_RERANK=1` |
| 前置 | 本机 TEI 需运行：`docker start tei-embedding tei-rerank`（端口 11435 / 11436，**用 `docker start` 不要 `docker run` 重建**），起完等约 50s，**用真实推理请求验证而非只看 `/health`** |
| 验收 | `GATE_USE_RERANK=1 python -m evaluation.retrieval_gate` 跑通且与 `evals/retrieval_baseline_rerank.json` 对得上 |
| 风险 | 低。TEI 未起则检索类请求失败 |

> ★ 在 T0.1 完成前，**本机任何「检索变准了」的结论都不该采信** —— 你验的是另一条链。

### T0.2 清掉静默无效的配置键

| 项 | 内容 |
|---|---|
| 问题 | `Settings` 用 `extra="ignore"`，不认识的键**静默无效**（会让人以为配了其实没有） |
| 实测残留 | `.env` 里 `RERANK_MODE` / `CONTEXT_TOKEN_BUDGET_DEEP` / `CONTEXT_TOKEN_BUDGET_SHALLOW` / `DATABASE_TYPE` |
| 改哪里 | `.env` 删除上述 4 键（删前先确认无消费者） |
| 验收 | `Settings.model_fields` 与 `.env` 的双向差集为空 |

### T0.3 补齐 `.env.example`

| 项 | 内容 |
|---|---|
| 实测缺口 | `BM25_CANDIDATE_FACTOR` / `BM25_CANDIDATE_FLOOR` 在 `Settings` 里但 `.env.example` **未记录**（#34 新增的旋钮没写文档） |
| 改哪里 | `.env.example` |
| 验收 | 双向差集只剩白名单（`AVAILABLE_MODELS` / `LANGCHAIN_TRACING_V2`） |

### T0.4 跑第一次 RAGAS，存基线

| 项 | 内容 |
|---|---|
| 命令 | `uv sync --group eval` → `uv run python -m evaluation.cli --dataset evals/sample_408.jsonl --limit 20 --tag baseline` |
| 产出 | `evals/results/*.json` |
| 验收 | `faithfulness` / `context_recall` / `context_precision` / `answer_relevancy` 四个数字落盘，并回填到本文件 §5 |
| 风险 | 需要真实 LLM（**会产生费用**）→ 先用 `--limit 20` |

### T0.5 黄金集加「知识点」中间层

**这是整条路线图最关键的一项。**

| 项 | 内容 |
|---|---|
| 为什么不做 chunk_id 级 | `retrieval_gate.py` 的取舍理由成立：chunk 级期望会在任何切分变更后大面积失效。**用「知识点标签」做中间层** —— 既不随切分失效，又比学科细一档 |
| 改哪里 ① | `evals/sample_408.jsonl` 每条 `metadata` 加 `knowledge_points: [...]` |
| 改哪里 ② | `src/evaluation/retrieval_gate.py` 加 `kp_hit@k` / `kp_mrr` 指标 |
| ★ 陷阱 | `src/evaluation/dataset.py:57` 会把 list 值 **join 成逗号串** → 读取端必须按逗号切分 |
| 验收 | `kp_hit@k` 基线 **< 1.0**（必须有下降空间，否则说明标注粒度还是太粗） |
| 依赖 | 需要 408 领域标注。**先 40 条跑通，再扩到 150~200 条** |

---

## 3. 阶段 1 — 让检索可感知（零后端成本）

> 这一阶段的价值：**用户看见出处才敢信答案，也才有能力报错**。
> 引用 UI 同时是反馈闭环的入口，而反馈是黄金集唯一的可持续来源。

### T1.1 引用溯源 UI

**好消息：机制已经全部就绪，只差接线。**

| 层 | 现状 |
|---|---|
| 后端契约 | `schema/evidence.py` 的 `EvidenceDoc` **已含** `source` / `section_path` / `chunk_id` / `score` / `rerank_score` / `knowledge_points` / `excerpt` |
| 事件通道 | `agents/utils.py` 的 `CustomData.dispatch()` 走 `custom` 流模式 → `ChatMessage(role="custom")`，**`retrieval_stage` 已在用** |
| 前端 | `static/app.js:502` **已解析** `m.type === "custom" && m.custom_data` |

**缺的只有两处：**

| 改哪里 | 内容 |
|---|---|
| `src/agents/tools.py` | 在 `_stage_sink()` 旁加 `_docs_sink()`，把 `RetrievalResult.docs` 以 `CustomData(kind="retrieval_docs")` 下发（注意 `_stage_sink` 对 `get_stream_writer()` 的守卫要照抄 —— 非流式调用会抛 `RuntimeError`） |
| `static/app.js` | 在 `m.custom_data.kind === "retrieval_docs"` 分支收集 docs，`finally` 里渲染成可折叠引用块；样式加进 `static/style.css` |
| 验收 | 提问后回答下方出现来源列表（文件名 + 章节路径 + 分数），可折叠 |
| 风险 | 低 |

### T1.2 反馈采集（赞 / 踩 + 错因）

| 改哪里 | 内容 |
|---|---|
| 后端 | 新增 `POST /api/feedback`（`src/service/service.py`）+ 落库表（`src/db/`） |
| 前端 | `static/app.js` 的 `buildActions()`（现有「复制」「重新生成」旁）加两个按钮 |
| 记录字段 | `thread_id` / `query` / `answer` / **本次检索到的 `chunk_ids`** / 错因标签 |
| 验收 | 点踩能落库且能按 `chunk_id` 反查 |
| ★ 价值 | **这是黄金集唯一的可持续来源** —— 没有它，黄金集只能靠人工编，永远追不上真实用户的错法 |

---

## 4. 阶段 2 — 上游数据（杠杆最大的地方）

> **为什么杠杆在上游**：`#13`（放宽五级标题 → `precision` 稳定 -1.8pp）、
> `#25`（保留短 section → MRR 一致下降）、`#34`（放宽候选池 → 真实收益为零）
> —— 三次失败的模式**完全一致：都在检索管线内部找杠杆，而管线已经很密了**。

### T2.1 知识库扩容

| 项 | 内容 |
|---|---|
| 现状 | `knowledge/` 共 41 文件 = 4 科讲义 + 2019~2024 六套真题 + 1 份学习路线 |
| 缺什么 | **2025/2026 真题**、**考纲 ↔ 章节映射表**、错题 / 易混点专题、跨科综合题 |
| 验收 | 入库 chunk 数、覆盖考点数（对比扩容前） |
| ★ 注意 | 入库后**必须**调 `evaluation.retrieval_gate.wait_for_index_ready()`；生产路径**不要自动重建**（删集合 = 真实数据丢失） |

### T2.2 small-to-big：用足已有的父子块

| 项 | 内容 |
|---|---|
| 现状 | `section.parent_chunk_id` / `child_chunk_ids` **已经入库**；`_stage_expand_windows` 已有窗口展开能力 |
| 问题 | `splitter.py` 的 `MIN_CHUNK_LENGTH` 会丢掉 **9.0%** 的短 section（2007 个里 181 个、6808 字符）。#25 试过保留但 MRR 掉了 —— 因为**保留了却没做排序补偿** |
| 正确做法 | 「**小块检索 + 大块送上下文**」：小块命中后带出父块作为上下文，而不是把小块的原始分数直接留在排序里 |
| 改哪里 | `src/rag/retriever.py` 的 `_stage_expand_windows` |
| 验收 | `category_precision` 不降 **且** `kp_hit@k` 提升 **且 真实路由复验通过** |
| 风险 | 中。务必吸取 #25 教训 |

### T2.3 元数据接入检索决策

| 项 | 内容 |
|---|---|
| 现状 | `src/rag/_metadata_spec.py` 有 **60+ 字段**（`section.path` / `depth` / `chunk_role` / `content_type` / `keywords` / `heading_slug`…），但**大部分没被用于检索** |
| 判断 | 典型的「**数据已就绪、能力未开发**」 |
| 改哪里 | `src/rag/recall.py` 的元数据路由：把 `section.path` / `content_type` 接进过滤与加权 |
| 验收 | 三条路由门禁全不退化 + `kp_hit@k` 提升 |

---

## 5. 阶段 3 — 中游排序（高价值但高风险）

### T3.1 跨集合融合排序（backlog #35 剩余项）

**这是目前唯一被证明会真错排的机制。**

| 项 | 内容 |
|---|---|
| 病例 | `虚拟内存` 查询：单集合内 OS 的 top-1（0.1843）**高于** CO（0.1824），但**跨集合 RRF 融合后 CO 反超** |
| 根因 | `all_specs` 是「集合 × 路由」的**笛卡尔积**（26 条列表）全部丢进**同一个 RRF 池**，而 **RRF 奖励「出现在更多列表里」的文档，不奖励「分数更高」的文档** |
| 佐证 | CO 的知识文件**自己写着**「详见 操作系统 3.内存管理 七、虚拟内存管理」—— 连它都把权威解释指向 OS |
| 改哪里 | `src/rag/postprocess.py` 的 RRF 融合 |
| 方案二选一 | ① 按集合归一化后再融合；② 给「推断出的集合」加权 |
| 验收 | **三条路由全跑**；`虚拟内存` 与 `段页式` 不再错排；其余 query 不退化 |
| 风险 | **高** —— 动核心排序算法。本仓库在该区域已有 3 次「看起来该修、实测有害」的先例（#13 / #25 / #34） |

### T3.2 路由分类层补测与度量

| 项 | 内容 |
|---|---|
| 现状 | `recall.py` 覆盖率 **55.9%**、`query_classifier.py` **70.6%** —— **决策层是全链路覆盖最低的部分** |
| 为什么危险 | 分类错 → 路由权重错 → 排序错，而**门禁完全看不出来**（学科还是对的） |
| 改哪里 | 补「分类 → 路由激活」的契约测试；把「激活了哪些路由」写进阶段追踪（`src/evaluation/stage_trace.py` 已有基建） |
| 验收 | 人为改错分类能**被测试抓住**（做反向验证，不能只写永远绿的测试） |

---

## 6. 明确不做清单

**调参类改动一律不做：**

| 不做 | 依据 |
|---|---|
| 学科路由权重调参 | #34 |
| RRF 路由权重调参 | #34 |
| BM25 候选池（`BM25_CANDIDATE_FACTOR` / `BM25_CANDIDATE_FLOOR`） | #34：真实 embedding 上收益为零 |
| 检索阈值微调 | #13 / #25 |
| 放宽 `splitter` 标题正则 | #13：`precision` 稳定 -1.8pp |
| 无条件保留短 section | #25：MRR 一致下降 |

**理由**：三次实证，真实口径零收益或有害；且假 embedding 会给出**真实环境里不存在**的假信号。

---

## 7. 工程侧处置策略

| 策略 | 说明 |
|---|---|
| 不设独立路线 | 工程侧不再单独立项 |
| 只在改动触达处还债 | 改了 `retriever.py` 就顺手拆函数、补测试 |
| 棘轮只收紧不放松 | 改小后跑 `python tests/test_structure_ratchet.py` 收紧基线；**数值变大 = 回退，应被质疑** |
| CI 三条命令照跑 | `ruff check src/ tests/ scripts/`、`ruff format --check src/ tests/ scripts/`（**两条单独跑，check 通过 ≠ 格式通过**）、`pyrefly check` |
| 改了检索链必须跑门禁 | `uv run python -m evaluation.retrieval_gate`（CI 有独立 job `retrieval-quality-gate`） |

---

## 8. 执行顺序与验收总表

```
T0.1 对齐链路 ──┐
T0.2 清残留配置 ├─→ T0.4 RAGAS 基线 ──→ T1.2 反馈采集 ──→ 黄金集自增长
T0.3 补 .env.example │
T0.5 知识点黄金集 ─┘        ↓
                      T1.1 引用 UI（可与 T0.5 并行，零后端成本）
                            ↓
                      T2.1 知识库扩容 → T2.2 small-to-big → T2.3 元数据路由
                            ↓
                      T3.1 跨集合融合 → T3.2 路由分类层补测
```

| 任务 | 可判定验收标准 |
|---|---|
| T0.1 | `GATE_USE_RERANK=1` 门禁与 `retrieval_baseline_rerank.json` 对得上 |
| T0.2 | `Settings` ↔ `.env` 双向差集为空 |
| T0.3 | `Settings` ↔ `.env.example` 双向差集只剩白名单 |
| T0.4 | `evals/results/*.json` 存在且含 4 个指标数字 |
| T0.5 | `kp_hit@k` 有基线且 **< 1.0** |
| T1.1 | 回答下方出现来源列表（文件名 + 章节路径 + 分数） |
| T1.2 | 点踩落库，可按 `chunk_id` 反查 |
| T2.1 | 入库 chunk 数 / 覆盖考点数上升 |
| T2.2 | `category_precision` 不降 **且** `kp_hit@k` 提升 **且** 真实路由复验通过 |
| T2.3 | 三条路由门禁不退化 **且** `kp_hit@k` 提升 |
| T3.1 | 三条路由全跑；两条错排病例修正；其余不退化 |
| T3.2 | 人为改错分类能被测试抓住（反向验证变红） |

---

## 9. 一句话

**价值在检索层是对的；但 T0 不做，T1~T3 就是在没有仪表盘的情况下调发动机 —— 而且调的是本机那台、和线上不是同一台的发动机。**
