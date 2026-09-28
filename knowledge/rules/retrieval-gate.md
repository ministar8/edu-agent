# Retrieval Gate Rules

检索验收门禁（Basic / 知识库变更后）。

---

## 1. 何时必须跑

- 修订 KP 树 / links  
- Basic/Advanced/Exams 内容或切分变更  
- `recall` / `splitter` / `vectorstore` / 元数据契约变更  

---

## 2. 标准门禁

| 命令 | 作用 |
|---|---|
| `PYTHONPATH=src uv run python -m evaluation.retrieval_gate` | 六路由回归，对比 `evals/retrieval_baseline*.json` |
| `PYTHONPATH=src GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1 uv run python -m evaluation.probe_gate` | 小节级探针 `dropped_by` |

红线：**未过门禁不得删旧集合**；假 embedding 结论不外推到真实路由。

---

## 3. Basic 试点附加验收（`scripts/verify_basic_pilot.py`）

### 3.1 KP 回链

```text
chunk_id → section_id → document_id → KP
teaches: basic:<section_id> → kp_id
```

- chunk_id 前缀含 section_id、document_id  
- `knowledge_points` ⊆ KP 表  
- teaches 仅 Section 级、UNIQUE、to 合法  
- 无 KP 的导论节无 teaches  

### 3.2 负向检索

| 用例 | 期望 |
|---|---|
| 离题查询（如 IPv4 子网） | 不得被 basic 试点独占 top |
| L2 技巧查询（BST 删除三种情况） | L1 正文不得含解题步骤 |
| 正文扫描 | 无 `选择题/真题/常考/考点/刷题` |
| 真题要答案 | top1 不得是 basic 概念文 |

---

## 4. 生产级验收（单篇）

- [ ] `basic-writing.md` 清单通过  
- [ ] 回链 + 负向脚本通过  
- [ ] `retrieval_gate` 不低于基线  
- [ ] `probe_gate` 不差于基线  

---

## 5. 基线变更

仅在指标变化可解释时 `--update-baseline`，并在 PR/记录中写明**为何可接受**。
