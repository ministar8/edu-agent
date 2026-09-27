# 探针门禁（补尺子）：把「小节级细节是否进了证据」变成可判定

**日期**：2026-09-27
**方案条目**：`docs/RETRIEVAL_PLAN.md` 的 §3⑦（「若要重提，先补尺子」）。
**新增**：`src/evaluation/probe_gate.py`（264 行）+ `evals/probe_baseline.json`。
**代码改动**：无（`src/rag/postprocess.py` 的临时评估改动已**逐字节回退**，见第 5 节）。

---

## 1. 补的是什么盲区

`retrieval_gate` 的 `kp_*` 是**章级**（`chapter_of_source` 只看文件名）⇒
**测不到「小节级细节是否进了证据」**。例：「磁盘空闲空间管理」的正确 chunk 在
`04_文件管理.md :: 6.2空闲表法`，只要**同文件的任意** chunk 进了证据，`kp_hit@k` 就算命中。
⇒ 这类缺陷可以长期藏在「门禁全绿」后面（§3⑦ 的实测：`#9` 在三份门禁日志里
**0 次**出现在未命中清单，而它的正确小节根本进不来）。

`candidate_trace` 看得见，但它是**诊断工具**：跑生产索引（**无就绪屏障**，会间歇性撞
Chroma「Nothing found on disk」）、没有基线、没有退出码 —— **不能当门禁用**。

## 2. 判据为什么是「管线序」而不是「是否 survived」

`dropped_by` 的取值**有序**（`candidate_trace.DROP_REASONS`）：

```
not_recalled(0) < section_dedup(1) < rrf_threshold(2) < rerank_topn(3)
                < rel_threshold(4) < window_expand(5) < survived(6)
```

门禁**拦「后退」、放行「前进」**。只断言 `survived` 会把
`#9` 从 `rrf_threshold` 前进到 `rerank_topn`（阈值层已修好、卡在下一层）这种**真实进步**
判成「没变」—— 而那正是 §3⑦ 要测的东西。

> ★ 层级序**直接复用** `candidate_trace.DROP_REASONS`，不另建一份 ——
> 两份顺序迟早漂移，漂移后门禁会**静默给出反向判定**。

## 3. 三次运行（本目录的日志）

| 日志 | 内容 | 退出码 |
|---|---|---|
| `baseline.log` | 录基线（`--update-baseline`） | 0 |
| `control.log` | **对照**：正常代码，与基线比较 | **0（绿）** |
| `reverse_verify.log` | **反向验证**：猴补丁还原「单字收窄之前」的词表 | **1（红）** ✓ |
| `with_fix.log` | 用尺子评估 §3⑦ 的量纲修法 | 0（放行「前进」） |

**反向验证**（`scripts/reverse_verify.py`，★ 关键 —— 证明它不是恒绿的门禁）：

```
[失败] 探针退化：
  - probe #19 退化：survived → not_recalled（目标在**更早**的层丢失了；query=位示图法是怎么工作的？）
[反向验证] 探针门禁退出码 = 1（期望 1 = 抓到退化）
```

其余 4 条 probe 不受影响 ⇒ 定位精确。

## 4. 用尺子复测 §3⑦ 的修法

| probe | 当前（无修法） | 带修法 | 基线 |
|---|---|---|---|
| **`#9` 磁盘空闲空间** | `rrf_threshold` | **`rerank_topn`（前进）** | `rrf_threshold` |
| `#4` / `#17` / `#18` / `#19` | `survived` | `survived` | `survived` |

⇒ 尺子**登记了这个收益**（`#9` 前进一层），门禁放行。

## 5. ★ 诚实的结论：尺子不解决 §3⑦ 的决策问题

门禁把**收益**表达成「`#9` 前进一层」，而**代价**仍由 `retrieval_gate` 的
`category_precision` 容差把守（Step 7 实测 −0.0272 / −0.0324）。
**两者的量纲仍然不同** —— 一个是管线层级进度，一个是比率。

⇒ §3⑦ 剩下的**不是工程问题，而是决策规则问题**：
**是否允许「`kp` 大涨」换「`cat_prec` 小幅下降」**。这需要人来定，不是再加一把尺子能定的。

**本次评估的临时改动已逐字节回退**，验证方式不是「看 `git status` 干净」，而是
**比对 blob 哈希**：

```
工作区 blob: 595d304a13d8b83bf1a85d9894e530efc0775cba
HEAD blob  : 595d304a13d8b83bf1a85d9894e530efc0775cba   ✓ 逐字节一致
```

## 6. 目录结构

| 路径 | 内容 |
|---|---|
| `baseline.log` / `control.log` / `reverse_verify.log` / `with_fix.log` | 四次运行 |
| `scripts/reverse_verify.py` | 反向验证脚本（猴补丁制造退化） |

## 7. 如何复现

```bash
# 录基线（权威路由）
GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1 \
  PYTHONPATH=src .venv/Scripts/python.exe -m evaluation.probe_gate --update-baseline

# 对照（应为绿）
GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1 \
  PYTHONPATH=src .venv/Scripts/python.exe -m evaluation.probe_gate

# 反向验证（应为红，退出码 1）
GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1 \
  PYTHONPATH=src .venv/Scripts/python.exe scripts/reverse_verify.py
```
