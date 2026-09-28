# docs/ 索引

**先读哪个**：改检索相关代码前 → `RETRIEVAL_PLAN.md`（当前方案）+ `RETRIEVAL_ROADMAP.md`（**「不做清单」在这里，改动前必看**）。

## 现行文档

| 文件 | 作用 | 何时读 |
|---|---|---|
| **`KB_DESIGN.md`** | **知识库四块设计**（基础知识 / 进阶王道 / 真题 / 学习路径 + Relation）与迁移清单 | **动知识库/入库前** |
| `ARCHITECTURE.md` | 分层与调用链（L0~L3 分层、检索/生成/护栏） | 理解系统结构 |
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

## 评测产物

`evals/results/` 下有两类，都是**证据**，不要随意清理：

1. `ragas_*.json` —— **付费**的 RAGAS 答案级评测结果（含时间戳，可当基线用，避免为跑「before」再付费）；
2. `step*_*/` —— 各轮检索改动的**免费门禁验证证据**（门禁 / 探针 / 诊断日志 + 产生它们的脚本原文）。
   每个目录有自己的 `README.md`，写明背景、关键数字与「读日志时要知道的事」。

> ★ 这些目录里的 `*.log` 由 `.gitignore` 的**例外规则** `!evals/results/**/*.log` 放行
> （`*.log` 会静默拦截它们）；`scripts/*.py` 则被 pre-commit 的 ruff 钩子 **排除**
> （`exclude: ^evals/`）—— 归档脚本是证据，不该被会改写文件的钩子重排。
