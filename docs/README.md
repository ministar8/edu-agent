# docs/ 索引

**先读哪个**：动知识库 → `KB_MASTER_DESIGN.md`（总册）。动检索路由/策略 → `RETRIEVAL_LAYER_DESIGN.md` + `RETRIEVAL_POLICY.md`。改检索相关代码前 → `RETRIEVAL_PLAN.md` + `RETRIEVAL_ROADMAP.md`（**「不做清单」在这里，改动前必看**）。**写论文 / 快速定位代码 → `ARCHITECTURE_RETRIEVAL.md` + `EXPERIMENTS.md`。**

## 现行文档

| 文件 | 作用 | 何时读 |
|---|---|---|
| **`KB_MASTER_DESIGN.md`** | **知识库总册**（L1/KP/L2/L3 + 边 + gap + ID + 现状） | **动知识库/入库前** |
| **`RETRIEVAL_LAYER_DESIGN.md`** | **检索层设计（定稿）**（task_mode / eligibility / ranking / release） | **动检索路由前** |
| **`RETRIEVAL_POLICY.md`** | **策略契约**（retrieval_policy 字段、默认表、LangGraph 落点） | 实现 Classifier/Policy 前 |
| `BASIC_DESIGN.md` | L1 细节 | 写/改 Basic |
| `ADVANCED_DESIGN.md` | L2 细节 | 写/改 Advanced |
| `EXAMS_DESIGN.md` | L3 细节（D0–D6 决策） | 写/改 Exams |
| `ARCHITECTURE.md` | 分层与调用链（L0~L3 分层、检索/生成/护栏） | 理解系统结构 |
| **`ARCHITECTURE_RETRIEVAL.md`** | **检索架构总览（as-built）+ 术语表 + 模块索引 + 已知局限** | **写论文第 3 章 / 定位代码** |
| **`RETRIEVAL_PLAN.md`** | **当前执行方案**（Step 1~6 + 实测数据 + 已否决项） | **动手改检索前** |
| `RETRIEVAL_ROADMAP.md` | 效果路线图；**含「不做清单」（同类改动有负收益先例）** | **动手改检索前** |
| `L1L2L3_RETRIEVAL_REVIEW.md` | L1/L2/L3 分级设计评审（问题清单 + 五维度优劣） | 改分级/路由/阈值前 |
| `RERANK_SWITCH_ANALYSIS.md` | `RERANK_ENABLED` 三态与 `use_rerank` 双职责分析 | 改重排开关相关代码前 |
| `DOCKER.md` | 部署、健康检查、**TEI 端点契约** | 起容器 / 探活 TEI 前 |

## 门禁（改了检索链就跑）

| 命令 | 粒度 | 说明 |
|---|---|---|
| `python -m evaluation.retrieval_gate` | 章级 `kp_*` + 学科级，156 条黄金集 | 改动检索链后**必须**跑；任一指标跌破基线即失败 |
| `python -m evaluation.probe_gate` | **小节级**：目标 chunk 在**哪一层**丢失，5 条探针 | 补上 `retrieval_gate` 的盲区（`kp_*` 只看文件名）。**拦「后退」、放行「前进」** |
| `python -m evaluation.candidate_trace` | 逐层快照（诊断） | **不是门禁** —— 跑生产索引、无就绪屏障、无退出码 |

## 遥测报表（不是门禁）

| 命令 | 说明 |
|---|---|
| `python -m evaluation.telemetry_report` | 把 `data/metrics/rag_metrics.jsonl` 聚合成人可读报表：流量构成、逐阶段漏斗（按 `query_type`）、有效阈值分布、分层/路由分布、入库交叉校验。**只读、无基线、无判定** —— 退出码只用于「读不到日志」。★ 两条使用纪律：① 用 `query_preview ∩ 黄金集` 判定流量来源，实测 **99.4% 是评测流量** ⇒ 它回答的是「管线各层在黄金集上的行为分布」，**不是**线上统计；② 日志**混了多个代码版本**，必须用 `--since` / `--until` 把窗口钉到单一版本（实测 `generate` 过阈率在 09-27 15:00 前后 0.075 → 0.187），否则读到的是**混合口径**。`--output <path>` 可把 JSON 落盘归档（建议 `evals/results/`） |

## 评测产物（`evals/results/`）

都是**证据**，不要随意清理。所有归档 JSON **自带 `provenance`**
（`code_version` / `golden_sha256` / `script` / `argv`），可从论文数字反查到代码版本。

| 路径 | 内容 |
|---|---|
| `retrieval/ablation/` | 组件消融 · 重排对照 · Task-aware · 基础 RAG · 方差 · 阈值敏感度 · L2 归因 |
| `retrieval/layer_policy/` | L1/L2/L3 分层消融 · Task × Layer 交互矩阵 |
| `retrieval/legacy_runtime/` | legacy 三策略 |
| `generation/ragas/` | `raw.jsonl` 逐样本 · `metrics.json` 汇总 · `summary.md` 结论 |
| `system_validation/` | Agent 行为 · LangGraph State 闭环 |
| `../baselines/` | 门禁基线（`retrieval_baseline.json` 等），门禁运行时即时比对 |

> 目录清单与命名约定的说明见 `evals/results/README.md`；实验数字与解读见 `docs/EXPERIMENTS.md`。
> 归档脚本落在 `scripts/`，由 pre-commit 的 ruff 钩子正常检查。
> （`.pre-commit-config.yaml` 的 `exclude: ^evals/` 仍保留，服务 `baselines/` 与 `datasets/`
> 这类**输入**；`.gitignore` 的 `!evals/results/**/*.log` 例外当前已无匹配文件。）
