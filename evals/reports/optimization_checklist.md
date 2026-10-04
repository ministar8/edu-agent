# 优化问题清单（清零用）· 2026-10-02

> 目的：写论文前把项目侧未决项收干净。**每项必须落到「已修 / 不修（有理由）/ 已关闭」**，不允许悬空。
> 基线版本：`V-2026-10-02`（`e36c766`）。动手改检索链前先读 `RETRIEVAL_ROADMAP.md` §6「不做清单」。
> 状态取值：`OPEN` · `ANALYZED`（已分析待决策）· `DECIDED-WONTFIX` · `DONE` · `OUT-OF-SCOPE`

---

## A. 检索质量

| ID | 问题 | 现状与证据 | 影响 | 建议决策 | 状态 |
|---|---|---|---|---|---|
| A1 | **L2 跨学科污染 40.0%** | 10 条进包 L2 中 4 条错学科（§16 / `l2_impact_analysis.md` §7） | 包纯度 + `l2_only` 0.7194；full 仅 −0.011 | **不修**（小诊断：叠加噪声非挤占，6/6 目标在包）；论文披露 40.0% + 「未见挤出」 | **DECIDED-WONTFIX** |
| A2 | **生成侧是否被污染影响（C 档）** | 未做 prompt 对照；现有结论止于「可能引入噪声证据」 | 论文局限表述的严谨性 | 可选：不动检索链跑污染包 vs 净包生成对照；**或**论文写「生成侧未测」 | **OPEN**（可降级为披露） |
| A3 | RRF 阈值 > 可达上限 | 阈值按 k=20 标定、实际 k=36；`dropped_by=rrf_threshold` | vector_only 边界样本；full 不受影响 | **不修**（`RETRIEVAL_ROADMAP` 不做清单，#13/#25 先例） | **DECIDED-WONTFIX** |
| A4 | rerank 收益符号不稳 | +0.012 / 更早 −0.046 | 默认关，不进主表 | **不修**，论文写「收益不稳定」 | **DECIDED-WONTFIX** |
| A5 | decompose / HyDE 零增益 | 消融 Δ = 0 | 无 | **保留启用**（关闭无变化），如实报零增益 | **DECIDED-WONTFIX** |
| A6 | 语义缓存污染测量 | 命中会混进检索质量 | 已默认关 | **维持默认关** | **DECIDED-WONTFIX** |

## B. 指标与评测

| ID | 问题 | 现状与证据 | 影响 | 建议决策 | 状态 |
|---|---|---|---|---|---|
| B1 | **`layer_hit` 对学科盲** | 只查 `advanced ∈ layers`，错学科照算命中（`l2_impact_analysis.md` §2.2） | TMLP hit=1.0 不能当 L2 质量证据 | **不改指标**（动口径会破坏与 §10–§12 可比性）；论文注明盲区 | **ANALYZED** |
| B2 | **L3 任务专有指标未补** | `exam_hit@k` / `question_id recall` / `answer availability`（§9） | grade/verify 只能用层命中代理 | 可补脚本，**不动检索链**；或论文降级表述 | **OPEN** |
| B3 | **门禁语料不含 L1/L2/L3** | 门禁 2505 条全 legacy；生产 4085 条（`ARCHITECTURE_RETRIEVAL.md` §6.3） | L1/L2/L3 退化门禁捕不到 | **不扩门禁**（改基线数字，属链路级）；论文已写明边界 | **DECIDED-WONTFIX** |
| B4 | RAGAS 样本 n=20 | 生成成本限制 | 结论置信度有限 | **不重跑**；论文写明样本量 | **DECIDED-WONTFIX** |

## C. 工程 / 技术债（不影响论文数字）

| ID | 问题 | 现状 | 建议决策 | 状态 |
|---|---|---|---|---|
| C1 | `rag/` `tools/` 类型注解放宽 | `pyproject.toml` pyrefly 豁免 | **OUT-OF-SCOPE**（论文无关） | OUT-OF-SCOPE |
| C2 | TEI 单点依赖 / 曾宕机 | 双容器本地部署 | 文档已覆盖；**不改架构** | OUT-OF-SCOPE |
| C3 | L1L2L3_REVIEW 代码级 R/P/Q/E 项 | 大部分有先例或不动链 | 除非与 A1 决策合并处理 | OUT-OF-SCOPE |

## D. 明确不做（红线，重复确认）

来自 `RETRIEVAL_ROADMAP.md` §6：调参类改动、阈值微调、`merged_qa_meta` 路由、
启发式修真题选项、清理知识文件标题 —— **一律不做**。

---

## 清零路径（建议顺序）

1. ~~**A1**~~ → **已决策不修**（`l2_impact_analysis.md` §7：只脏不挤）
2. **A2** 二选一收口：跑生成对照 **或** 论文写「生成侧未测」
3. **B1 / B2** 论文口径决策（改脚本补指标 or 降级表述）
4. 其余维持 `DECIDED-WONTFIX` / `OUT-OF-SCOPE`

**完成判据**：本表无 `OPEN`/`ANALYZED` 残留 → 可进入写论文。
