# 遥测报表 · 首次落地（2026-09-27）

## 这是什么

`evaluation.telemetry_report` 的首次产出 —— 它给 `data/metrics/rag_metrics.jsonl`
补上**读方**（该日志此前只有写方 `rag.metrics.MetricsWriter`，全仓无任何消费方）。

**它不是门禁**：无基线、无判定，退出码只用于「读不到日志」。理由见模块文档串 ——
本日志的输入以**评测流量**为主（跑一次门禁就写入 936 条），内容随「跑了几次门禁」而变，
做成带基线的门禁会引入一个**不稳定判据**。

- 入口：`src/evaluation/telemetry_report.py`
- 复现：`PYTHONPATH=src uv run python -m evaluation.telemetry_report --output evals/results/telemetry_2026-09-27/report.json`
- 日志本体**不入库**：它在 `data/`（已 gitignore）且是评测 exhaust，不是证据。

## 读这份 report.json 时要知道的事

### ① 它不是线上统计

用 `tags.query_preview ∩ (黄金集 ∪ 配对集)` 判定流量来源，实测：

| 事件 | 总数 | 评测流量 | 其余 |
|---|---|---|---|
| `retrieve_query` | 28,657 | **28,482（99.4%）** | 175（0.6%） |
| `retrieve_evidence` | 56,221 | 56,214 | **7** |

那 175 条「其余」里 Top1 是「位示图法是怎么工作的？」×7 —— 即探针 `#19`
（它**不在**黄金集里）。⇒ **这份日志里没有真实用户流量。**

**所以它能回答**「管线各层在 156 条黄金集上的行为分布」，
**不能回答**「线上检索准不准」。

### ② 逐阶段漏斗：过阈率与是否重排无关

> ⚠️ **本节数字已修订（同日 21:15）** —— 见下面的「③ 时间窗口」。原先给的
> 「全量」过阈率（generate 0.103 / grade 0.124）是**混合口径**：日志里写着
> Step 1~10 各轮实验的运行记录，同一个指标在不同时间段是**不同代码**跑出来的。

**必须按时间切开**（`--since` / `--until`）。以 09-27 15:00（本机）为界：

| query_type | 修前（`--until 2026-09-27T15:00`） | 修后（`--since 2026-09-27T15:00`） | 变化 |
|---|---|---|---|
| concept | 0.400 | 0.411 | +0.011 |
| **generate** | **0.075** | **0.187** | **+0.112（2.5×）** |
| **grade** | **0.113** | **0.159** | **+0.046（1.4×）** |
| code | 0.156 | 0.223 | +0.067 |

- **这是 §3⑦ 修复（`_rrf_scale` 阈值量纲修正，Step 7 试、Step 10 采纳）有效的
  机制级旁证** —— 它测的正是「阈值层放行了多少」，比 `kp@k` 更直接。
- ⚠️ 但两个窗口**都不是纯单版本**：修前窗口仍含 Step 1~6 的实验，修后窗口含
  Step 8/9（关键词表）的实验，且窗口长度仅约 3.5 小时。⇒ 只能说**方向与量级明确**，
  不能把 0.187 当作「纯 `_rrf_scale` 的效果」。
- 按「是否请求重排」再切一刀（全量口径）：generate 0.107 / 0.102、grade 0.138 / 0.119
  ⇒ **过阈率几乎不变**，说明阈值层的损失是**纯 RRF 层结构性的**，与重排无关。
  这把 `docs/RETRIEVAL_PLAN.md` §3⑦ 从**纯算术推断**升级为**实测**。

### ③ 时间窗口是必需的，不是可选的

同一份日志跨越 09-23 ~ 09-27，其中 `generate` 的过阈率在 **09-27 07:00 UTC
（15:00 本机）前后从 0.075 跳到 0.187** —— 不切开就会读到一个「0.10 左右」的值，
**既不是修前也不是修后**。因此报表模块加了 `--since` / `--until`
（ISO-8601 或相对量 `6h` / `3d`，相对量的锚点是**日志最新一条事件**而不是「现在」，
否则窗口会落在日志之外、结果为空），并在 `_meta.window` 里把窗口写进产物；
未过滤时输出会**显式警告是混合口径**。

复现：

```bash
PYTHONPATH=src uv run python -m evaluation.telemetry_report --until 2026-09-27T15:00
PYTHONPATH=src uv run python -m evaluation.telemetry_report --since 2026-09-27T15:00
PYTHONPATH=src uv run python -m evaluation.telemetry_report --since 6h
```

### ④ 入库交叉校验抓到一个真实缺口

`ingest_file_summary` 同时给 `chunks`（切分产出）与 `indexed_chunks`（真正入库），
两者之差 = `vectorstore` 按**内容哈希**判重丢掉的量。

- 合计 `indexed_chunks` = **2092**，与生产索引规模**逐位一致** ⇒ 该字段可作交叉校验。
- 唯一不一致的文件：**`data_structure/07_查找.md`，106 → 82，丢 24**（4 轮入库均如此）。

**已定位根因**（复现脚本见下）：这 24 个 chunk 与 **`05_树与二叉树.md`** 的 chunk
**内容逐字节相同** —— 因为两个源文件在「二叉排序树 / 平衡二叉树（含 LL·RR·LR·RL 旋转）」
这些小节上**内容重合**；去重是「先入库者胜」，索引里归到了先入库的 `05_树与二叉树.md`。

**影响（当前为潜在、未实现）**：
`kp_hit@k` 的章标签由 `chapter_of_source(ev.source)` 从**证据文件名**算出。
黄金集里标注为「查找」的 6 条 query 实测是**哈希冲突 / B树B+树 / 折半查找**，
**不涉及** BST/AVL ⇒ 目前不产生误判。但若将来给黄金集加「BST/AVL 查找性能」类查询
并标为「查找」章，证据来自 `05_树与二叉树.md` ⇒ **必然判未命中**（标注 vs 索引归属错配）。

复现（只读，不碰索引）：

```bash
PYTHONPATH=src uv run python - <<'PY'
import hashlib
from rag.loader import load_single_file
from rag.cleaner import clean_documents
from rag.splitter import split_documents
h = lambda t: hashlib.sha256(t.encode()).hexdigest()[:16]
a = split_documents(clean_documents(load_single_file("knowledge/data_structure/07_查找.md"),
                                    dedup=True, fuzzy_dedup=False, fuzzy_threshold=0.9))
b = {h(c.page_content) for c in split_documents(clean_documents(
    load_single_file("knowledge/data_structure/05_树与二叉树.md"),
    dedup=True, fuzzy_dedup=False, fuzzy_threshold=0.9))}
print(len(a), sum(1 for c in a if h(c.page_content) in b))   # → 106 24
PY
```

### ⑤ `evidence_verdict` 的 hard_fail 占比不能读成「查询失败率」

实测 `pass` 47,049 / `hard_fail` 9,172（16.3%），而 **`retry_count` 全为 0**
⇒ 该字段只反映**该次**证据事件的判定，不含治理层随后是否重试成功。
报表里已把 `retry_count` 一并输出，就是为了避免这个误读。
