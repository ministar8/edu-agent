# Step 2（撤销入库同义词归一）验证证据

**日期**：2026-09-27
**对应提交**：本目录随「检索层 Step 2：撤销入库同义词归一（采纳 3-②）」一并提交。
**方案与结论**：`docs/RETRIEVAL_PLAN.md` 的 §2（净效果表）、§4（Step 1 / Step 2）。

本目录是**原始门禁日志**，不是摘要。所有数字都能从日志里逐行核对。

---

## 1. 背景

入库时 `cleaner.normalize_synonyms()` 会把文档改写成标准术语（全库 5191 处），
而 query 侧没有对齐 ⇒ BM25 的 `$contains` 字面匹配对变体**恒 0 命中**、
reranker 给变体极低分、且索引文本 ≠ 源文件（引用溯源失真）。

Step 2 撤销了这一归一。本目录记录撤销前后的全部门禁运行。

## 2. 目录结构

| 目录 | 内容 | 说明 |
|---|---|---|
| `step1/` | `r0`~`r5`（6 次） | **Step 1**：未归一索引上跑全部 6 条路由。`r5` 是隔离对照（关掉 `expand_query_with_synonyms`）。`.exit` 为退出码 |
| `rebaseline/` | `b1`~`b6`、`c1`~`c5` | **基线重录**两轮。`b` 轮用 `--update-baseline`，`c` 轮加 `--force-baseline` + 竞态重试 |
| `verify/` | `v1`~`v6`（6 次） | **复验**：默认配置（不带任何 env 覆盖）下跑 6 条路由，与重录后的基线比对 |
| `scripts/` | 4 个 `.sh` | 产生上述日志的脚本原文，含 env 与路由顺序 |

## 3. 如何复现

```bash
# Step 1：未归一口径（Step 2 之前）
INGEST_SYNONYM_NORMALIZE=false RERANK_QUERY_NORMALIZE=false \
  PYTHONPATH=src .venv/Scripts/python.exe -m evaluation.retrieval_gate

# 复验：Step 2 之后（默认配置即可）
PYTHONPATH=src .venv/Scripts/python.exe -m evaluation.retrieval_gate
```

真实路由（`real/*`）需要 TEI 在 `localhost:11435`（embedding）与 `11436`（rerank）。
其余路由组合见 `scripts/verify.sh`。

> ⚠️ **TEI 重启后必须等模型加载完（约 45 秒）再跑真实路由。**
> 只探 `/health` 会误判 —— 本轮实测前两次代码路径探活报 `RemoteProtocolError`，
> 第 3 次才返回 `dim=1024`。

## 4. 关键数字

索引：**2107 → 2092** chunk（DS 703 / CO 415 / OS 358 / CN 314 / questions 278 / LP 24）。

| 路由 | `kp@k`（Δ） | `kp_mrr`（Δ） | `cat@1`（Δ） |
|---|---|---|---|
| `fake/off` | 0.8141（+0.0705） | 0.6571（+0.0517） | 0.9038（+0.0256） |
| `fake/on` | 0.7756（+0.0577） | 0.7171（+0.0789） | 0.9487（+0.0064） |
| `fake/disabled` | 0.7756（+0.0705） | 0.6165（+0.0664） | 0.9167（+0.0064） |
| **`real/off`** | **0.8397（+0.0448）** | **0.6688（+0.0401）** | **0.8782（−0.0064）** |
| **`real/disabled`** | **0.7692（+0.0256）** | **0.6351（+0.0428）** | 0.8910（+0.0128） |
| `fake/off`·关 `expand` | 0.8141（+0.0705） | 0.6522（+0.0468） | 0.8974（+0.0192） |

- Δ 相对 Step 2 **之前**的旧基线。
- **假路由数字不可外推**（`USE_FAKE_EMBEDDING` 只保留词汇重叠信号）——
  生产可预期的量级是 `real/off` 与 `real/disabled` 两行。
- **代价**：`real/off` 的 `cat@1`/`cat@k`/`cat_mrr` 各降约 0.006~0.008、`cat_prec` −0.0019
  （门禁容差 0.02 内，但属真实下降，已在方案 §2 单列）。

## 5. 读日志时要知道的三件事

1. **`b` 轮多数是失败的，那是有价值的信息，不是噪声。**
   `b1`/`b2`/`b4`/`b5` 被 `check_baseline_sanity` 拒绝（**未写盘**），`b3` 因 Chroma
   「已建索引的集合中有 300 次检索期查询异常」失败 —— 前者是已知的
   `mean_evidence_count` 量纲缺陷，后者是 HNSW 落盘竞态。改用 `--force-baseline`
   + 重试后 `c1`~`c5` 才成功；`b6`（`real_disabled`）是 `b` 轮里唯一成功的，
   ⇒ **这 6 份基线的来源轮次并不统一**。

2. **门禁有运行间方差，同一配置重复运行不逐位相同。**
   `real/off` 的 `kp_mrr` 三次测量为 0.6688 / 0.6715 / 0.6752（极差 **0.0064**）。
   方差远小于容差 0.02，不影响门禁结论；但**不能拿它做「逐位复现」式归因**。

3. **`v4`/`v5`/`v6` 的首次运行全部立即失败**（12:48，三条在 47 秒内相继退出），
   原因是 TEI embedding 返回 `502 Bad Gateway`。**当前 `verify/` 下的 v4~v6 是 TEI 恢复后
   重跑的成功版本**（文件时间 12:56 / 13:01 / 13:05），那次失败的日志已被覆盖，未保留。

## 6. 与 `evals/results/` 下其他产物的区别

本目录是**免费**的门禁日志（确定性哈希 embedding，无 LLM 调用）；
同目录下的 `ragas_*.json` 是**付费**的 RAGAS 答案级评测产物。两者口径不同，不可互比。
