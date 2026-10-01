# Knowledge Point Schema

统一知识点体系（Knowledge Point, KP）数据契约。  
目录：`knowledge/knowledge_points/`。

## 文件布局

| 文件 | 内容 |
|---|---|
| `ds.jsonl` | 数据结构 KP 节点 |
| `co.jsonl` | 计算机组成原理 KP 节点 |
| `os.jsonl` | 操作系统 KP 节点 |
| `cn.jsonl` | 计算机网络 KP 节点 |
| `links.jsonl` | 内容 ↔ KP 边（全库一个） |
| `schema.md` | 本文件 |

一行一个 JSON 对象；`links.jsonl` 允许为空文件。

---

## 1. 节点（`*.jsonl`）

### 1.1 字段

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | ✓ | 全局唯一，见 §1.2 |
| `name` | string | ✓ | 中文规范名（可改名，**不改 id**） |
| `subject` | enum | ✓ | `ds` / `co` / `os` / `cn`，与 id 前缀一致 |
| `parent_id` | string \| null | ✓ | 父 KP 的 `id`；学科根为 `null` |
| `level` | int | ✓ | **分类树深度** 1–4，**不是难度** |
| `node_kind` | enum | ✓ | `subject` / `domain` / `topic` / `point` |
| `type` | enum | ✓ | `concept` / `principle` / `algorithm` / `structure` / `protocol` / `method` / `term` |
| `importance` | enum | ✓ | `core` / `major` / `minor`（**知识体系地位**，非考频） |
| `typical_question_types` | string[] | ✓ | 典型/允许考法，**非历史统计** |
| `aliases` | string[] | | 同义名、英文、俗称（**只放同义词**） |
| `tags` | string[] | | 非结构化：`易错` / `易混` / `陷阱`… |
| `status` | enum | ✓ | `active` / `deprecated` |
| `replaced_by` | string[] | deprecated 时 ✓ | 支持 1 拆 N |

### 1.2 `id` 规则

```text
^(ds|co|os|cn)(\.[a-z0-9_]+)*$
```

- 学科根 id 为 `ds` / `co` / `os` / `cn`（可无后缀）  
- 英文 slug，**一经发布冻结**  
- 中文改名只改 `name`，旧名迁入 `aliases`  
- 例：`ds`、`ds.tree.binary_search`、`co.cpu.pipeline_hazard`、`cn.network.arp`

### 1.3 `level` 与 `node_kind`

| node_kind | level | 含义 |
|---|---|---|
| `subject` | **1** | 学科根 |
| `domain` | **2** | 一级知识域 |
| `topic` | **3** | 二级域 / 主要考点 |
| `point` | **3 或 4** | 可单独考查的考点 |

约束：

- `node_kind` ↔ `level` 必须符合上表（禁止 `domain`+L4 等）  
- `point`+L3 合法（如 `co.cpu.pipeline`）  
- 检索/出题/路径默认只落在 `topic` / `point`  
- **粒度**：一个 KP = 真题可**单独考查**的语义单元  
- `aliases` **禁止**放入子节点专有词（勿把「冒险」放进 `co.cpu.pipeline`）

### 1.4 `typical_question_types` 枚举

```text
choice | fill | calculation | comprehensive | code | design
```

语义：该 KP **通常怎么考**（知识体系先验）。  
真实考次一律由 `question ──assesses──→ KP` **动态统计**，禁止混用。

### 1.5 示例

```json
{
  "id": "os.file.disk_free_space",
  "name": "磁盘空闲空间管理",
  "subject": "os",
  "parent_id": "os.file.physical",
  "level": 4,
  "node_kind": "point",
  "type": "method",
  "importance": "core",
  "typical_question_types": ["choice", "calculation", "comprehensive", "code"],
  "aliases": ["位示图", "空闲表", "空闲链表"],
  "tags": ["易错"],
  "status": "active"
}
```

废弃（含拆分）：

```json
{
  "id": "os.mem.legacy_memory",
  "status": "deprecated",
  "replaced_by": ["os.mem.virtual_memory", "os.mem.page_replacement"]
}
```

---

## 2. 边（`links.jsonl`）

```json
{
  "from": "question:2019-Q11",
  "to": "os.file.disk_free_space",
  "type": "assesses"
}
```

| 字段 | 含义 |
|---|---|
| `from` | **资产引用** `asset_type:asset_id` |
| `to` | **KP id**（必须存在于节点表） |
| `type` | `teaches` \| `assesses` \| `trains` |

### 2.1 asset_ref

```text
<asset_type>:<asset_id>
```

按**第一个** `:` 切开；`asset_type` 封闭枚举：

| asset_type | asset_id | 例 |
|---|---|---|
| `paper` | 年份 | `paper:2019` |
| `question` | `YYYY-QN` | `question:2019-Q11` |
| `basic` | `relpath#section` | `basic:os/file.md#磁盘空闲` |
| `advanced` | `relpath#section` | `advanced:os/文件大题.md#位示图` |
| `practice` | 稳定题号 | `practice:wangdao-os-023` |
| `learning_path` | 路径节点 id | `learning_path:path.l2.os.memory` |

### 2.2 边类型

| type | 语义 | 允许 from |
|---|---|---|
| `teaches` | 讲解该考点 | `basic` / `advanced` |
| `assesses` | 考查该考点 | `question` |
| `trains` | 强化/训练该考点 | `practice` |

```text
基础教材  ──teaches──→  KP
真题题   ──assesses──→ KP
王道/专项 ──trains──→   KP
```

学习路径 **不进** teaches/assesses/trains；路径用 `kp_ids[]`。

### 2.3 完整性约束

1. **`UNIQUE(from, type, to)`** — 禁止重复边  
2. **一题可多 KP** — 综合题写多条 `assesses`  
3. `to` 必须存在于 `ds/co/os/cn.jsonl`  

---

## 3. 校验清单

- [ ] id 正则 + 前缀 = `subject`  
- [ ] `parent_id` 存在（或 null）  
- [ ] `node_kind` ↔ `level` 合法  
- [ ] `status=deprecated` ⇒ `replaced_by` 非空数组  
- [ ] `aliases` 无跨节点专有词  
- [ ] links：`UNIQUE(from,type,to)`、`to` 存在、type/from 匹配  

---

## 4. 生成与维护

| 工具 | 用途 |
|---|---|
| `scripts/gen_kp_skeleton.py` | 骨架生成（可重跑覆盖） |
| `docs/KP_SKELETON.md` | 人读树（与 jsonl 同步） |
| `docs/KB_MASTER_DESIGN.md` | 知识库总册 |

**Coverage Test**：用 2009–2025 真题反向锚定；未命中记 GAP，禁止硬贴最近节点。
