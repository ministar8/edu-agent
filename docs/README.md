# docs/ 索引

**先读哪个**：改检索相关代码前 → `RETRIEVAL_PLAN.md`（当前方案）+ `RETRIEVAL_ROADMAP.md`（**「不做清单」在这里，改动前必看**）。

## 现行文档

| 文件 | 作用 | 何时读 |
|---|---|---|
| `ARCHITECTURE.md` | 分层与调用链（L0~L3 分层、检索/生成/护栏） | 理解系统结构 |
| **`RETRIEVAL_PLAN.md`** | **当前执行方案**（Step 1~6 + 实测数据 + 已否决项） | **动手改检索前** |
| `RETRIEVAL_ROADMAP.md` | 效果路线图；**含「不做清单」（同类改动有负收益先例）** | **动手改检索前** |
| `L1L2L3_RETRIEVAL_REVIEW.md` | L1/L2/L3 分级设计评审（问题清单 + 五维度优劣） | 改分级/路由/阈值前 |
| `RERANK_SWITCH_ANALYSIS.md` | `RERANK_ENABLED` 三态与 `use_rerank` 双职责分析 | 改重排开关相关代码前 |
| `DOCKER.md` | 部署、健康检查、**TEI 端点契约** | 起容器 / 探活 TEI 前 |

## 归档（仅历史记录，不代表当前结论）

`archive/` 下：

| 文件 | 说明 |
|---|---|
| `RETRIEVAL_PLAN_V1.md` | V1 方案，已被当前方案取代 |
| `RETRIEVAL_PLAN_V2.md` | V2 方案，已被取代，但保留为**分析记录**（含 §5.8~§5.14 的实测过程） |
| `RETRIEVAL_DIAGNOSIS.md` | V1 诊断，结论已并入当前方案 |
| `ENGINEERING_COMPARISON.md` | 与上游模板对比，**不描述当前实现** |

## 任务产物（非系统文档）

- `真题选项*.html`：真题选项修复任务的**审阅/补表产物**，由 `scripts/fix_question_options.py` 生成，
  `RETRIEVAL_ROADMAP.md` 有引用。

## 评测产物

`evals/results/` 下是 RAGAS 等**付费评测结果**。
按项目纪律，它们**是证据**（含时间戳，可当基线用，避免为跑「before」再付费），不要随意清理。
