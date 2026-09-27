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

| query_type | 去重后候选池 | 过阈后 | **过阈率** | 有效阈值 |
|---|---|---|---|---|
| concept | 29.60 | 11.92 | 0.403 | 0.06 / 0.08 / 0.088…（混合） |
| **generate** | **115.60** | 11.88 | **0.103** | **恒 0.12**（5,484 条全是） |
| **grade** | **70.08** | 8.68 | **0.124** | **恒 0.12**（5,443 条全是） |
| code | 85.12 | 14.45 | 0.170 | 主要 0.11 |

按「是否请求重排」再切一刀：generate 0.107 / 0.102、grade 0.138 / 0.119
⇒ **过阈率几乎不变**，说明阈值层的损失是**纯 RRF 层结构性的**，与重排无关。
这把 `docs/RETRIEVAL_PLAN.md` §3⑦（RRF 阈值量纲错配）从**纯算术推断**升级为**实测**。

### ③ 入库交叉校验抓到一个真实缺口

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

### ④ `evidence_verdict` 的 hard_fail 占比不能读成「查询失败率」

实测 `pass` 47,049 / `hard_fail` 9,172（16.3%），而 **`retry_count` 全为 0**
⇒ 该字段只反映**该次**证据事件的判定，不含治理层随后是否重试成功。
报表里已把 `retry_count` 一并输出，就是为了避免这个误读。
