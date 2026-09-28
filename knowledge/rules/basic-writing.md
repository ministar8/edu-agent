# Basic Writing Style V1.0

L1 Basic 正文写作规范。来源：`06_tree.md` 试点定稿（2026-09-28）。

---

## 1. 分层职责（总纲）

| 层 | 回答什么 | 例 |
|---|---|---|
| **Basic** | 解释 **是什么 / 为什么 / 怎么工作** | BST 有序性把查找变成一条向下的路径 |
| **Advanced** | 解释 **怎么做题** | 删除先看孩子数，分三种情况 |
| **Exams** | **具体真题 / 答案 / 题目语境** | 2019-Q5 … |
| **Knowledge Point** | **统一知识锚点** | `ds.tree.bst` |
| **Section** | **语义关系主体**（teaches/assesses/trains） | `basic-ds-tree-bst` |
| **Chunk** | **检索载体** | `basic-ds-tree-bst-001` |

```text
Basic Section ──teaches──→ KP
```

---

## 2. L1 允许 / 禁止

| 写 | 不写 |
|---|---|
| 定义、动机、性质 | 真题编号、答案 |
| 核心机制与步骤 | 王道页码、应试套路 |
| 基础公式、复杂度 | 长篇完整实现 |
| 算法 **思想 / 原理** | 解题 **技巧 / 策略** |
| 「为什么学它」 | 「选择题/计算题高频」「常考」「考点」 |

### 2.1 思想 vs 技巧

```text
L1 原理   AVL 通过局部旋转恢复平衡，并保持中序有序
L2 策略   判断 LL/RR/LR/RL，再选单旋或双旋
```

禁止口诀、「遇到××题先…」、判定步骤写入 Basic。

### 2.2 措辞

- 禁止考试导向词：`选择题` `计算题` `真题` `常考` `考点` `刷题` `王道` `应试`
- 复杂度表述区分「树高 / 平衡 / 退化」，勿混「平均」与「平衡」
- **KP id 不进叙述正文**；只进 `> kp_ids` 元数据或文末锚定表
- 「高频字符」等**领域频次**可用（≠考频）

---

## 3. 文档结构

```markdown
# <Domain 名>

> domain_kp: <domain id>
> document_id: basic-<subject>-<slug>

## 学习目标
- 理解…
- 掌握…

## <Topic/Point 名>
> section_id: basic-<subject>-<slug>-<sec>
> kp_ids: [ ... ]
> primary_kp: <可选>

**基本思想** / **机制** / **特点** / **定义** …（维度非固定字段）
```

| 项 | 规则 |
|---|---|
| Domain→Document | 默认一域一文；过大才按 Topic 拆 |
| 学习目标 | 每章要有；「理解/掌握」；禁止刷题话术 |
| 五维 | 定义/为什么/性质/机制/公式·思想是**内容维度**，非每节强制四标签 |
| 先修 | 不写正文；KP Graph V2 `requires` |
| 绪论 | 可保留；`kp_ids` 可空；**不为目录硬造 KP** |

---

## 4. 与 KP

- KP 是锚点，不是教材目录镜像  
- `domain_kp`（文档 1 个） / `kp_ids`（节） / `primary_kp`（可选 ∈ kp_ids）  
- aliases 不跨节点（「冒险」只在 `pipeline_hazard`）

---

## 5. 验收

- [ ] 无考试导向措辞  
- [ ] 无 L2 技巧 / 口诀  
- [ ] 正文无 KP id 散落  
- [ ] 每节有 `section_id` + `kp_ids`  
- [ ] KP 均存在于 `knowledge_points/*.jsonl`  
