# Step 3（A2：代码 chunk 保留语义锚点）验证证据

**日期**：2026-09-27
**方案与结论**：`docs/RETRIEVAL_PLAN.md` 的 §2（Step 3 行）、§3②、§4 Step 3。
**改动**：仅 `src/rag/reranker.py`（+31 / −5）。

本目录是**原始日志**，不是摘要。

---

## 1. 根因：一个跨模块契约只做了一半

- `splitter.py` **有意**给含代码围栏的 chunk 加 `[考点名]` 前缀作为**语义锚点**，
  理由写在源码里：纯代码正文没有中文语义，embedding 无法把
  「用信号量写出生产者—消费者问题的伪代码」这类 query 映射到一段 C 代码上。
- `reranker.py` 的前缀剥离正则 `^(?:\[[^\]]*\]\s*(?:>\s*)*)+\n` **恰好把这个锚点剥掉**。

**改动前核实过的前提**（`scripts/anchor_stats.py` 的输出）：
当前索引 2092 chunk 中，**296 个带 `[..]` 前缀的 chunk 全部含代码围栏，非代码 chunk 一个都没有**。
⇒ 那条剥离正则**只会命中代码块**：零收益、纯有害。
（另有 **27 个**含代码围栏的 chunk 因 `heading_path` 为空而未被加锚点 —— 属**数据缺口**，
rerank 侧无从补，需在 splitter 侧另找锚点来源。）

## 2. 目录结构

| 目录 | 内容 |
|---|---|
| `gate/` | 6 条路由的门禁日志（`g1`~`g6`）+ `real/on` 的两次复跑（`rep1`/`rep2`） |
| `probe/` | `#18` 目标 chunk 的**直测分数**、以及全 4 条 probe 的逐层 A/B 追踪 |
| `scripts/` | 产生上述日志的脚本原文 |

## 3. 关键数字

| 送入 reranker 的文本 | `#18` 的 rerank 分 |
|---|---|
| 剥掉锚点（改动前） | **0.0037** |
| 保留锚点（改动后） | **0.9169** |

绝对阈值 `RERANK_ABSOLUTE_MIN_SCORE = 0.15`。同一 chunk、同一模型、同一 query，只差一个锚点。

流水线层面（`probe/ab_trace_*.log`）：`#18` 的 `dropped_by` 由 `rerank_topn`（被截断）
→ **`survived`（最终证据 rank 2）**；其余 3 条 probe（`#4` / `#9` / `#17`）名次**不变**。

## 4. 门禁：6 条全通过，且对照组逐位相同

| 路由 | `kp@k` | `kp_mrr` | `cat@1` | 重排是否执行 |
|---|---|---|---|---|
| `fake/off` | 0 | 0 | 0 | 否 |
| `fake/disabled` | 0 | 0 | 0 | 否 |
| `real/off` | 0 | −0.0037（方差内） | 0 | 否 |
| `real/disabled` | 0 | 0 | 0 | 否 |
| `fake/on` | 0 | **+0.0032** | 0 | 是 |
| **`real/on`** | 0 | **−0.0046** | **−0.0064** | 是 |

**不执行重排的 4 条路由零变化**（`fake/off` 九项指标与基线**逐位相同**）—— 强对照组，
证明改动只经重排路径生效。

## 5. ★ 代价：真实且可复现，不要当成噪声

`real/on` 上 `kp_mrr` 0.7483 → **0.7437**、`cat@1` 0.9295 → **0.9231**。

**三次独立复跑（`g5`、`rep1`、`rep2`）给出完全相同的 0.7437 / 0.9231**
⇒ 该路由是确定性的，**这个差不是方差**（对比：本仓库其他路由实测有 ≤0.007 的方差，
所以「逐位复现」不能当通用判据 —— 但对本路由成立）。

差异集中在**恰好一条** query：
「写一段 C 代码用位运算交换两个整数，并说明为什么它未必比使用临时变量更快」
（期望 `computer_organization`，实际 `operating_system`）。
机制：锚点让部分代码块被**过度提升**，挤掉了原本正确的证据。

**为什么仍然采纳**：当前生产 `.env` 是 `RERANK_ENABLED=false` ⇒ 重排不执行
⇒ **A2 对当前生产配置零影响**；收益与代价都只在**重排开启**的路由上生效。
采纳决定由用户做出（2026-09-27）。

## 6. 读日志时的两个警告

1. **`probe/ab_trace_*.log` 里有 Chroma 竞态，结论不可单独采信。**
   `candidate_trace` 跑在**生产索引**上、**没有就绪屏障**，本轮出现
   `Async Chroma query failed for operating_system: ... Nothing found on disk`
   （before 13 次 / after 9 次）。该竞态会影响召回池，因此这两份日志
   **只作旁证**；决定性证据是 `gate/`（自建临时索引 + `wait_for_index_ready`）。
   注意 `#9` 的召回池条数在两相位分别是 20 / 21，正是该竞态的表现。

2. **`scripts/why_regress.py` 的输出未归档** —— 它同样受上述竞态影响，
   无法可靠定位那条退化 query 的顶替者，故不把它的输出当证据保留。

## 7. 如何复现

```bash
# 门禁（自建临时索引，带就绪屏障）
bash scripts/gate.sh

# 直测 #18 的 rerank 分（需要 TEI 在 .env 配的地址上）
PYTHONPATH=src .venv/Scripts/python.exe scripts/inspect_target.py

# 全 4 条 probe 的 A/B（两相位必须分独立进程 —— _rerank_cache 会串味）
PYTHONPATH=src .venv/Scripts/python.exe scripts/ab_trace.py before
PYTHONPATH=src .venv/Scripts/python.exe scripts/ab_trace.py after
```

`scripts/` 下的脚本带原始绝对路径（`C:\Users\26452\AppData\Local\Temp\edu_step3\`），
复现时按需改输出目录。
