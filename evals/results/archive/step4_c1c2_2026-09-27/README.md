# Step 4（C1/C2：学科关键词修正）验证证据

**日期**：2026-09-27
**方案与结论**：`docs/RETRIEVAL_PLAN.md` 的 §2（Step 4 行）、§3④、§4 Step 4。
**改动**：仅 `src/rag/recall.py` 的 `_COLLECTION_KEYWORDS`（加词，无逻辑变更）。

本目录是**原始日志**，不是摘要。

---

## 1. 改了什么

| 项 | 改动 | 为什么 |
|---|---|---|
| **C1** | `磁盘` **加入 OS 词表**（同时保留在 CO） | CO 的「存储系统」讲磁盘容量/阵列，OS 的「文件管理」讲**磁盘空闲空间管理**（空闲表/空闲链表/位示图）。原先只收在 CO ⇒ 这类查询被**收窄到只搜 CO**，答案所在的 OS 集合根本不在范围内。按本表既有先例（`段页式` / `虚拟存储器` 同样两科都收）两边都收。 |
| **C2** | CO 词表补 `阶码` / `尾数` / `float` / `ieee754` | 原先只有 `浮点数`，而实际提问写的是「**float** 的 32 位二进制表示…读出**阶码**与**尾数**」—— 一个词都匹配不上，推断为空。 |

**影响面很小**：黄金集 156 条里，含 `磁盘` 的 2 条、含 `float`/`阶码`/`尾数` 的 2 条。

**★ 一个必须知道的前提**：`_infer_subject_collections` 返回空时，`resolve_collection_routes`
会**回退到全 4 科检索**（`recall.py:598`）。所以「推断为空」**不等于「检索不到」**——
`#17` 原先就是走回退路径、目标其实**已被召回**（只是 rank 49/336、融合分不够）。
这一点推翻了方案里「推断为空 ⇒ 该查询不可达」的隐含假设。

## 2. 目录结构

| 目录 | 内容 |
|---|---|
| `gate/` | 6 条路由的门禁日志（`s1`~`s6`） |
| `probe/` | 4 条 probe 的逐层快照：改动前（`before_c1`）/ 改动后（`after_c1c2`） |
| `scripts/` | 产生上述日志的脚本原文 |

## 3. 关键数字（probe 逐层归因）

| probe | 推断集合（前 → 后） | `dropped_by`（前 → 后） |
|---|---|---|
| `#9` 磁盘空闲空间管理 | `{CO}` → `{CO, OS}` | `not_recalled` → **`rrf_threshold`**（进池 rank 15 / 234） |
| `#17` IEEE754 float | `[]`（⇒全 4 科） → `{CO}` | `rrf_threshold` → **`survived`（最终 rank 1）** |
| `#4` 折半查找 | `{DS}`（不变） | `survived`（不变） |
| `#18` 生产者-消费者 | `{OS}`（不变） | `survived`（不变） |

## 4. 门禁：6 条全通过，且**全部为改善**

| 路由 | `kp@k` | `kp_mrr` | `cat@1` | `cat_prec` |
|---|---|---|---|---|
| `fake/off` | +0.0064 | +0.0069 | +0.0065 | +0.0093 |
| `fake/on` | +0.0193 | +0.0224 | +0.0064 | +0.0019 |
| `fake/disabled` | +0.0129 | +0.0099 | +0.0064 | +0.0079 |
| `real/off` | +0.0193 | +0.0096 | +0.0128 | +0.0075 |
| `real/on` | +0.0129 | +0.0082 | 0（见下） | +0.0042 |
| `real/disabled` | +0.0193 | +0.0150 | +0.0064 | +0.0125 |

**`real/on` 的 `cat@1` 显示 −0.0064 是 Step 3 的遗留，不是本次新增。**
逐时点：基线 → Step 3 后 → Step 4 后 = `0.9295` → `0.9231` → **`0.9231`**（**S3→S4 = +0.0000**）；
`cat_mrr` 同理（`0.9359` → `0.9327` → `0.9327`）。
而 `kp_mrr` `0.7483` → `0.7437` → **`0.7565`** —— **已反超 Step 3 之前的基线**。

## 5. ★ 判定口径修正：不要用 `candidate_trace` 的默认路径

方案原判定写「`candidate_trace` 上 `#9`/`#17` 的 `dropped_by` ……」。但：

- `candidate_trace` 默认直接查**生产 `chroma_db/`**，**没有就绪屏障**；
- 会间歇性撞 Chroma「`Nothing found on disk`」（Step 3 实测 13 次 / 9 次）；
- 表现是**召回池条数在两次运行间漂移**（如 `#9` 是 20 vs 21）⇒ **无法做 A/B 归因**。

**本目录的 `probe/` 日志改用**：`retrieval_gate.configure_for_gate` + `build_index` +
`wait_for_index_ready(repair=True)` 建**临时索引**，再用 `candidate_trace` 的追踪器。
脚本：`scripts/probe_on_temp_index.py`。命令见第 7 节。

## 6. 两项遗留（**已单列，未修**）

1. **`#9` 仍未进最终证据**：`dropped_by` 从 `not_recalled` 修到 `rrf_threshold` ——
   目标 chunk **已进召回池（rank 15 / 234）**，但练习类有效阈值 0.12，其融合分不够。
   这是**阈值标定**问题（与 §3⑥ 同域），**不是关键词路由**；
   按本仓库「不做清单」（阈值微调有 #13 / #25 负收益先例）**不在此处调参**。

2. **`位示图` 被误判为 `data_structure`**（本次**未修**）：`位示图` 是典型的 OS
   空闲空间管理术语，但 DS 词表里有**单字 `"图"`**，任何含「图」的查询都会命中 DS。
   **加词解决不了**（要收窄 DS 侧的 `"图"`），且该词表可能还有同类过宽项，须单独评估。

## 7. 如何复现

```bash
# 可信的 probe 逐层快照（临时索引 + 就绪屏障；需 TEI）
GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1 \
  PYTHONPATH=src .venv/Scripts/python.exe scripts/probe_on_temp_index.py

# 6 条门禁
bash scripts/gate.sh

# real/on 的逐时点对比（需要 Step 2/3 的日志在场）
PYTHONPATH=src .venv/Scripts/python.exe scripts/compare_s5.py
```

`scripts/` 下的脚本带原始绝对路径（`C:\Users\26452\AppData\Local\Temp\edu_step4\`），
复现时按需改输出目录。`compare_s5.py` 依赖 `Temp/edu_step1` 与 `Temp/edu_step3` 下的历史日志。
