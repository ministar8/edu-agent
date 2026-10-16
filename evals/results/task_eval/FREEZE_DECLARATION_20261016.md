# FREEZE DECLARATION · edu-agent 评测冻结宣布（2026-10-16）

> **宣布**：edu-agent 项目评测冻结链至此完成，自 2026-10-16 起进入**冻结态**。
> 前置：owner 2026-10-16 书面裁决「同意 frozen，按 `fc3ad81` 版 FREEZE_CHECKLIST 所列全部条款」；
> `FREEZE_CHECKLIST_20261015.md` 未勾项 **0**（E 段「冻结宣布判据」全部满足）。
> 版本锚点：git tag `V-2026-10-16`（annotated，指向本宣布所在提交）。

## 1. 冻结范围与状态

| 对象 | 状态 | 指纹 / 锚点 |
|---|---|---|
| demo gold 四件套（qa 15 / verify 15 / generate 15 / grade 15 / memory 6） | **frozen 66/66**（gold_status 唯一字段 reviewed→frozen） | `qa fede59a4ce8e872a` · `verify 51273aa6a3b194c3` · `generate 31a421dbe2c3c7eb` · `grade 3aa9f22a02610b99` · `memory fcd790441fe36666`（sha256 前 16；§20.0 效果集指纹已同步） |
| 任务级效果归档 | `ec_r3_freeze_20261016.jsonl` active（66 条，provenance 八键 66/66） | sha256 `ae1eca4b1333…`；artifact_status.json 在册 |
| RAGAS 冻结版 | `ragas_freeze20261016.json` active（156 条四指标） | 与 V-2026-10-02 锚点五处口径不同 ⇒ 并列披露不可比 |
| 主张 ledger | 段 1/段 2 PASS；段 3 V0② FAIL = option B 披露态 | `evals/claims/ledger.md` |
| 门禁终态 | sanity ERROR 0 / PENDING 1（存量）；ecg 81 全绿；pytest 26/26；ruff 全过 | 复现行见 §20.7.8㉒㉓ |

## 2. 证据链摘要（全部留痕可复算）

A1 键纠错链（95 条评测侧覆盖 + 台账）→ A2 盲标回填（generate 15/15 present）→ A3 R1-B 11 判据签署（口径=映射已审）→ **A4 frozen 裁决（owner 书面）** → B1/B2 归档代际与极性裁定 → C0–C4 全量重跑（66 条 + 六路由门禁 + RAGAS + Memory 三 gate）→ D1/D3 收口（表 7/8 + §22.2 + 13 条局限核对）→ Task 10 文档收尾（§1.1 口径差 + superseded 谱系复核 + E 段三门关闭）。逐条：`docs/EXPERIMENTS.md` §20.7.5–§20.7.8①–㉓。

## 3. 引用纪律（冻结态下生效）

1. 论文任何效果数字引用必须带 `evals/reports/paper_tables.md` 表 7/§22.2 的分母与口径红线；
2. **frozen 的是 gold，不是指标**：Generate V0② missing_premise、Grade 两极 gold（verdict_agreement 口径）、Memory 有效 n=2 照常披露，不得把「已测量未证明」当成绩；
3. RAGAS 新旧值仅并列披露，不得表述为改善/退化；
4. provenance_match 跨提交重算为 0 是设计特性（比对实时 HEAD），不得读成冻结质量问题；
5. 「gate 全绿」= 当前检查项通过，不外推为全部历史实验复现。

## 4. 冻结后纪律（§F）

demo gold 四件套**只读**：任何变更须走新审核链 + owner 新裁决；effect 归档不可变（历史归档内嵌 gold_status 为各自时点快照，ec_r3 = reviewed，不回写）；新跑的效果归档一律带 frozen 标记。

## 5. 冻结后开放项（不阻塞，均已备好工作单）

| # | 开放项 | 状态 / 工作单 |
|---|---|---|
| 1 | 91 键「仓库题干/选项 ↔ 原卷」逐字比对 | 工作单已生成：`evals/results/task_eval/A1_KEY_STEM_VERBATIM_WORKSHEET_20261016.md`（sha256 `067a55c24b51bc89…`，91 条基准文本机械抽取完备）——待 owner 提供原卷（仓库无 `papers-rebuild/`） |
| 2 | KP 标签质量订正（ver-002/007 裁定发现 5 条） | 裁定：`evals/results/task_eval/VER_002_007_RULING_20261016.md`；工作单：`evals/results/task_eval/KP_LABEL_CORRECTION_WORKSHEET_20261016.md`——待 owner 裁定落地口径（A 评测侧覆盖 / B KB 修订） |
| 3 | gen-005/009 第二标注者姓名补登 | 签署为 owner 转述形式（§20.7.8⑪）——待 owner 提供姓名，项目方机械回登 `GEN_MEM_BLINDREVIEW_20261016_labeler_copy.md` 签署区 |

## 6. 生效声明

本宣布落盘即生效。gold 冻结态自 `bc818ea`（owner 裁决执行）起算；宣布文档固化全部判据与纪律。论文阶段自本宣布后启动。
