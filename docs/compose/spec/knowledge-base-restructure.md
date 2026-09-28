---
feature: knowledge-base-restructure
status: delivered
updated: 2026-09-28
branch: main
commits: cd12e52..HEAD
---

# Knowledge Base Restructure（基础→知识点→王道→真题）

## Report

**What was built** — 定稿 408 知识库逻辑模型与目录命名：内容侧 L1 `basic` → `knowledge_points`（统一考点关系层）→ L2 `advanced`（王道）→ L3 `exams`（按年）；学习侧 `learning_paths`（l1/l2/l3）独立。交付完整设计文档 `docs/KB_DESIGN.md`（目录、元数据、向量集合、L1–L3、KP 契约、迁移 M1–M5）。本期不改运行时代码与目录。

**Verification** — 设计评审（结构自洽、命名定稿、迁移可执行）；无代码变更，未跑检索门禁（P0 实现时必跑）。

**Journey log**
- 并列「四库」被否：改为学习深度链 + KP 关系层，避免第四向量库抢 RRF。
- 目录命名：放弃 `l1_basic` 前缀，采用 `basic/advanced/exams/learning_paths`（用户定稿）。
- `wangdao` 不进路径名，写在 advanced 的文档语义里，避免绑定书商品牌。

## [S1] Problem

教材/专项/真题/路径混放，检索分不清深度；知识点无法串联三层；L1/L2/L3 缺内容与路径锚点。

## [S2] Design

### 2.1 逻辑模型

```text
内容体系: L1 basic → Knowledge Point → L2 advanced(王道) → L3 exams(2009-2025)
学习体系: L1 基础路径 → L2 强化路径 → L3 真题训练路径
KP = 统一知识点体系（关系层，不进 RRF 主池）
```

### 2.2 目录（定稿）

`knowledge/{knowledge_points,basic,advanced,exams,learning_paths}/`；真题 `exams/YYYY/{paper,items,answer}.md`；KP 按四科分子目录，id 全局唯一。

### 2.3 元数据

`kb_depth` / `doc_role` / `subject` / `exam_year` / `question_id` / `credibility` / `knowledge_points`。

### 2.4 L1–L3

L1→basic；L2→advanced（+basic 背景）；L3→exams（+advanced）。learning_paths 提供阶段与 KP 集合。

完整契约见 `docs/KB_DESIGN.md`。

## [S3] Out of Scope

本期不迁移目录、不改 ingest/recall、不重录门禁；不建图数据库；不启发式补选项。

## Tasks

- [x] T1: 定稿设计并与 Compose Spec 对齐 — acceptance: `docs/KB_DESIGN.md` 与本 Spec 同为「基础→KP→王道→真题 + learning_paths」 (covers: S2)
- [x] T2: 迁移映射与门禁回归清单 — acceptance: KB_DESIGN §3.1 迁入表 + §8 M1–M5 (covers: S2.2; depends: T1)
