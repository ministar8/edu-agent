# EVIDENCE_CHAIN — 证据链重建方案（主张 ↔ 证据对齐）

> 一句话：**把「声称」从人写的措辞，变成机器算出来的状态。**
> **基准代码态**：`3e77e01`（2026-10-08 15:54）。本文引用的所有跟踪状态/归档读数都写成**命令**，
> 不写死数字 —— 本方案自己先遵守 R3。
> v1.2（2026-10-08）：v1.1 并入第一轮 review 的 12 条 + R5；**v1.2 并入第二轮 7 条**
> —— gold 补齐从「可选路线」升级为 **P0 前置**、R5 补**分母语义与 `required_when`**、
> 业务链二分（阻塞正式实验 / 登记 limitation）、新增 **B7 检索失败传播**、V0 加硬、**盲标规程**。
> 第二轮同时修正 v1.1 两处事实错误：`gold_review.jsonl` 并非 30 行全空（见 §4.2）；BM25 路由失败对门禁不可见。
> 背景：全仓 review 发现「系统实际表现」与「项目声称已被实验/门禁证明的表现」之间存在断层。
> 关系：**不改写任何冻结件**（`EFFECT_PLAN.md` §3.1/§4、`RETRIEVAL_POLICY.md` 等），
> 只把实现拉回冻结契约，并给契约补上「判定强度」这一维。偏离一律登记，不改原文。

---

## 0. 问题定义

断层不是「没规划」。`EFFECT_PLAN.md` 已写清因果链（§2.B.3）、五项判据（§3.1，v1.0 冻结）、
provenance 100%（§6）。断层的全部来源是这一句：

> **声称的粒度高于被锁定谓词的粒度。**

| 症状 | 实例（本轮已证实） | 机制 |
|---|---|---|
| 失败无法归因 | 15/15 `retrieval_status='ok'` 同时 15/15 `primary_failure='retrieval_miss'` | R2 因果链的机械供给 |
| 成功无法证明 | ④ 归档里 Generate「五项」三项恒 True、一项全 None、一项 ≡ judge 分。★ ⑤ 的复测里 `structure`/`answerability` 已能变红（14/15，#35 抓到 `gen-009` 正文丢失）⇒ **恒真是那份归档的事实，不是判据永远恒真**；但 `correctness ≡ fq≥4` 依旧，且 **#36 的人工手验** 证明它不够：5 道手验里 2 道客观错、1 道满分漏检，`gen-001` 被判 5.0 而 Cache 组号应为 210 写成 46 | R1-A/R1-B + 取证 |
| 语义契约不统一 | `EvidenceDoc.score` 混相似度与 Chroma 距离（top-up 因此反向排序） | R4 字段单一语义 |
| 数据不可证伪 | `rerank_used` 硬写 `True`；门禁守住「开关失真」却漏掉「降级失真」 | R1-A + 状态枚举 |
| 多套现实 | tracked 报告印 `reviewed 66`，数据集 66 条全 `draft`；`docs/README.md:40` 写「129 项」而代码声明值已两度上移（204 → 216，`3e77e01`） | R3 单一来源 |
| **降级伪装成进步** | 把两项标为未测量 ⇒ 复合主指标 0.733 → **1.000**（实测，见 §4.2） | **R5 复合 N/A** |

**非目标（YAGNI）**：不进 CI、不建测试框架、不搞属性测试、不做主张审批流程、
不调检索参数（`EFFECT_PLAN.md:380` 三次负收益先例）、不新增第二套指标实现。

---

## 1. 规则

### 1.1 两套状态，别混

**主张状态**（claim_status，由机器算出，只有三值）：

| 状态 | 判定条件（全部满足才是第一档） |
|---|---|
| **已证明** | R1-A 机械敏感 **且** R1-B 语义映射已签 **且** R2 层级够 **且** 取证时 `code_version`/`prompt_set_version`/`config_hash`/工件 hash 与所引数字一致 |
| **已测量未证明** | 有数，但上述任一缺失 |
| **未测量** | 测不到 / 判据恒真且弄不红 / gold 前提不存在 |

**工件状态**（artifact_status，历史数据用，不改写数值）：`active` / `superseded` / `invalidated`，
`superseded` 必须带 `superseded_by` + `reason`（如 `predicate_semantics_changed`）。
⇒ 回答「为什么 phase0 的 0.7333 还在仓库里」这句话，靠字段而不是靠记忆。

文档不允许出现第三种主张状态措辞。

### 1.2 R1 拆两层：牙齿 ≠ 咬对东西

- **R1-A 机械敏感性**：注入 mutation ⇒ 判据按预期变红；且**恰好这一条变红，其余不动**。
- **R1-B 语义有效性**：每个判据声明它实现的是冻结契约里的哪个谓词，以及**该谓词点名的输入字段**：

```python
{
  "name": "gen_structure",
  "tier": 1,
  "contract_ref": "EFFECT_PLAN.md §3.1 completeness_pass",
  "contract_inputs": ["stem", "options_or_requirement", "answer_key", "analysis"],  # 契约点名的
  "fn": ...,
  "falsifier": "逐字段删除：删任一 contract_input ⇒ 必须变 False",
}
```

R1-A 的检查升级为**覆盖性检查**：`mutation 集 ⊇ contract_inputs`。
只删代码碰巧读的那个字段不算通过（`return bool(record["analysis"])` 能骗过单点 mutation，
但骗不过「四个契约输入各删一次都必须变红」）。

★ **R1-B 的诚实边界**：`contract_ref` 与覆盖性检查让映射**可审计**，不自动**证明**它语义正确——
最终仍需一次人工对着冻结定义签字（每个判据一次，不是每轮实验一次）。本方案不把它写成「已闭合」，
写成「已审待签 / 已签@版本」。这条自己也要守本文件的规矩，否则方案本身就在过度声称。

### 1.3 R2 证据分层 + 单项四态

| tier | 含义 | 例 |
|---|---|---|
| 0 | 机械事实，不经模型 | `retrieval_status`、`rerank_status`、`memory_read_status`、`tool_error`、episode 是否真落 Store |
| 1 | 可观测物证（对产物做结构/一致性检查） | 四件套齐全、答案键 ∈ 选项集、解析结论与答案键同结论 |
| 2 | judge 的观点 | `final_quality`、`answerable`、`failure_reason` |

**每个判据项返回四态，不是两态**：`pass` / `fail` / `not_applicable`（本 case 按契约就不适用）/
`missing_premise`（契约要求它，但 gold 或证据不存在）。后两者都记 `None`，但**必须带 reason**，
因为它们在 R5 里的待遇相反。

两条硬规则：
- 门槛行的质量分允许 tier 2（`EFFECT_PLAN.md:334` 的 QA 门槛本就是 `final_quality≥4`，不动它），
  但须满足两个前置：① 重复测量抖动已量化（§21 已有三次抖动数据）；② **判据边界已校准**。
  当前做不到：`calibration_30.jsonl` 的 `human_score` 分布 = **5×28 / 2×1 / 0×1**，
  而每条门槛都在 `≥4` 翻转 ⇒ 边界档（3、4）**零样本**，「judge 在门槛附近是否与人工一致」从未被测。
  缺任一前置 ⇒ 该行 = **已测量未证明**。
- **因果链每一环由更低 tier 支撑**：`retrieval_miss` 仅在 tier-0 显示检索确实返空/失败时允许写入；
  judge 给的原因一律落到 `judge_failure_reasons`（诊断位，不参与 `primary_failure`）。
  这是 `judge.py:296` 已有 `judge_memory_*` 隔离模式的推广。

### 1.4 R3 禁止的是「孤立结论」，不是结论句

规则对象是**可验证事实断言**：一个数字或一句「通过/一致/为空」若没有 `证据锚点 + 复现命令`，
即视为孤立。带来源的结论句合法，文档照常可读：

```
本次实验通过全部门禁。
证据：evals/claims/ledger.md#gate-2026-10-08
复现：PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py --check
```

检查器只对「含数字或「全绿/应为空/逐位相同/一致」且 100 字符内无 `证据：`/`复现：`/反引号命令」的行报 warning。
本轮实例：`EXPERIMENTS.md:908` 断言某 diff 为空，实测 **9 文件 +801/−8**。

### 1.5 R4 检索字段单一语义

`EvidenceDoc.score` 只能是**相似度**（越高越好）。RRF 融合分另存 `rrf_score`；
Chroma 距离在进入契约前经**唯一**换算函数转换。实现第一步先测各 collection 的 distance function
（cosine → `1-d`；l2 → `1/(1+d)`），换算只允许存在于 `src/rag/embeddings.py` 一处。

### 1.6 R5 复合指标的 N/A 语义与分母（本方案的关键新增）

每个判据项返回四态（§1.3），复合时区分**谁有权缺席**。规格表因此多一个字段：

```python
"required_when": ...   # 例：difficulty_match 仅当 query 指定难度才必需；
                       #     correctness / answerability 对任何生成题恒必需
```

**合取型复合指标**（`five_of_five` 这类「全部必需项都过才算过」）：

```
COMPOSITE = 所有 required 项都已测 ? evaluate(合取) : MISSING_PREMISE
```

而不是 `all(x is True or x is None)`。逐成分对照：

| 成分状态 | 复合结果 |
|---|---|
| 全 `pass` | `pass` |
| 任一 `fail` | `fail` |
| 任一 required 项 `missing_premise` | **`missing_premise`（不是 pass）** |
| 仅 `not_applicable` 与 `pass` 混合 | `pass`（契约不要求的项可以不参与） |

**分母语义（v1.2 明确）**——这是「10/10=100%」还是「10/15=66.7%」还是「N/A」的问题，必须有答案：

| 报告位 | 规则 |
|---|---|
| **主指标**（进 §6 门槛行的那一个数） | 任一 required 项 `missing_premise` ⇒ **整条主指标 = `missing_premise`（N/A）**，**不出百分数** |
| **辅助位**（诊断，明确标注为辅助） | 允许 `measured_n` / `missing_n` / `measured_pass_rate` 三个数并列，如 `measured_n=10, missing_n=5, measured_pass_rate=1.000（辅助）` |
| **单项率** | `not_applicable` 与 `missing_premise` 都出分母（对齐规则①②），但**必须并列 `n_a` 与 `missing_premise` 两个计数**，不得合并成一个 `n/a` |
| **族级零覆盖** | 某项在本族**全部** case 上都 `not_applicable`（如实测 `gen_difficulty` 15/15，因 query 未指定难度）⇒ 该族对这个维度**零覆盖**，必须在文档显式披露，不能只写「N/A」 |

现状 `metrics.py:440-443` 把 `None` 一律剔除，不区分后两行 —— 这正是 §4.2 事故的来源。
`not_applicable` 与 `missing_premise` 必须是不同值，否则「无 gold」会被洗成「全过」。
★ 辅助位永远不允许变成论文里的那个「正确率」——`build_claim_ledger` 只把主指标写入 §6 行。

---

## 2. 单元与接口

**先定 schema，再写判据**（第一轮 ⑨）：`predicates` 只能读 Evidence Record，缺字段是 V0 红灯，
不允许在写判据的过程中回头改 `runner.py` 补字段。

```
schema/evidence_record.py   ← P0.1 事实层唯一定义（含 provenance）
predicates/
  ├── registry.py   ← P0.2 tier 表 + 规格表 + contract_inputs（唯一注册）
  ├── common.py     ← rate / every_item_passes(R5 版) / degenerate 检查
  ├── generate.py   ← P0.3 各 predicate + falsifier
  ├── verify.py
  └── memory.py
falsify.py          ← P0.4 跑 mutation 矩阵，校验「恰好变红」+ contract_inputs 覆盖
build_claim_ledger.py → evals/claims/ledger.md（生成物）
```

`metrics.py`(672)/`report.py`(435) 改为**只读 registry**，删掉各自的本地公式副本 ——
否则拆包反而造出第二个真源。拆包同时把 12 个超 600 行文件的问题往前推一步
（`CLAUDE.md:88` 红线），目的不是好看，是「一个指标只有一处定义」。

---

## 3. 数据流与 provenance（第一轮 ⑥）

```
run → archive.jsonl（Evidence Record + provenance）
        ↓ 零 token
reanalyse（按 registry 重算：四态、R5 复合、恒真项质询）
        ↓ 零 token
falsify（每条主张弄坏一次 → 记录是否恰好变红 + 覆盖 contract_inputs）
        ↓ 零 token
ledger（三态 + artifact_status）
        ↓
docs（只嵌 ledger 锚点 + 复现命令）
```

provenance 字段（现状只有 `code_version`/`golden_sha256`/`date`，`docs/README.md:64` 已如实承认缺 `argv`）：

| 新增 | 内容 | 为什么 |
|---|---|---|
| `model_refs` | agent 与 judge 的 `<gateway>:<model_id>` | 「同代码同提示但换模型」目前不可见 |
| `sampling` | judge/agent 的 `temperature`（+ 若有 `top_p`） | judge 无 seed，温度即结论 |
| `experiment_config_hash` | 非密钥白名单字段（k/阈值/`RERANK_ENABLED`/`USE_FAKE_EMBEDDING`/缓存开关）的排序后 hash | `.env` 改了要能被看出来；**只 hash，不落原值**（对齐既有 #29「settings 泄漏」修复） |
| `dependency_lock_hash` | `uv.lock` sha256 | 依赖漂移 |
| `argv` + `script` | 与检索类归档同款 | 效果数字也能反查到命令行 |

★ 一致性要求：`已证明` 的取证记录必须与所引数字**这五项全一致**，否则状态自动降级。
★ `reprobe` 的既有缺陷顺带修掉：`cli.py:260-279` 用新检索覆盖指标却把 provenance 留在旧值
（旧输入新输出）——**覆盖任何指标字段时 provenance 必须同写，否则拒绝写入**。

---

## 4. 归因改写（含改名，第一轮 ②③ + 第二轮 1、7）

### 4.1 原则

**证据不是等价定义，就不沿用原指标名。** 冻结的 `gen_correctness` / `gen_answerability` 名字保留、
状态改为 `missing_premise`（未测量）；机械可算的部分另起名字，且明示它是**必要非充分**条件。

| 新指标（tier 1，机械） | 它证明 | 它不证明 |
|---|---|---|
| `gen_answer_key_validity` | 答案键存在 ∧ ∈ 选项集 ∧ 正确项唯一 | 这题「可被作答判定」（原 answerability） |
| `gen_analysis_agreement` | 解析结论与答案键同结论（#33 产品规则的评测化） | 答案本身对不对（原 correctness） |

**★ 与 #36 的关系（必须说清，否则像在推翻已定决策）**：#36 的处置是
「登记为判据局限、**不改判据**（§3.1 v1.0 已冻结）」。本方案**同意不改 §3.1** —— 因为 §3.1 的原文写的是
`correctness_pass = gold 判定正确`，**它要求的正是 gold**；现在的实现 `fq≥4` 不是这条冻结判据的实现，
而是它的替代读数。所以 P−1 补 gold 是**把实现拉回冻结文本**，不是改判据。
#36 顺带列出的两条低成本改进（judge 先重算再判 / 抽一批人工复核表）与 P−1 是同一件事的两个入口，
其中「人工复核表」正是 §4.2 的盲标规程。

### 4.2 已实测的后果，与「补 gold」升级为 P0 前置

把 `gen_correctness`/`gen_answerability` 标为 `missing_premise` 后，按现有 `every_item_passes`
（`None` 出合取）实测：**`gen_case_pass` 从 0.733 变成 1.000，n 仍为 15、n_a 仍为 0**。
即「诚实标记测不到」被复合逻辑翻译成「全过」。所以 §4.1 的改名**必须**和 R5 同批落地，
否则本方案自己制造一次新的断层。R5 落地后：该批 Generate 主指标 = **`missing_premise`（整族不可出数）**。

**★ ⑤ 的复测读数（`EXPERIMENTS.md` §22.1）同样不能沿用**：锚点 ⑤ 上 generate-only 复测已把主指标抬到
**13/15 = 0.867，过了 ≥0.75 的门槛**（`final_quality` 均值 3.933→4.400，回归 0 条）。
但那 13/15 依然是 `correctness ≡ fq≥4` 的合取，而 `gold_answer` 仍 0/15 未填 ⇒
**R5 一落地，这个「过线」读数会变成 `missing_premise`**（不是 fail，也不是继续 0.867）。
⇒ 处置：该归档标 `artifact_status=superseded`，`reason=composite_na_semantics_changed`；
论文里若要写 0.867，必须连着 #36 那句「judge 不重算算术，它测的是像不像一份能用的答案」一起写。
这也是 P−1 排在最前面的实证理由：**补了 gold，0.867 这类数才重新有据；不补，它只能降为 limitation。**

**★ 更正 v1.1 的一处事实错误**：我曾写「`gold_review.jsonl` 30 行全 `None`」——只看了前 3 行。
实测底数是：该表 30 行 = **generate 15 + grade 15**；`review_fields` 有三个键
（`gold_answer` / `expected_difficulty` / `human_score`）；其中
**generate 的 `gold_answer` 与 `expected_difficulty` 各 0/15 已填**，
**grade 的 `human_score` 已 15/15 填满，分布 `{100.0: 8, 0.0: 7}`**。
后一半正是 `metrics.py:450` docstring 里描述的**两极退化 gold**（独立核对吻合）。
⇒ 待补工作量比我原先估的小一半，但暴露出**第二个**前置缺口（G1b）。

| 项 | 内容 | 状态 | 成本 |
|---|---|---|---|
| **G1a** | 填 generate 15 行的 `gold_answer` + `expected_difficulty` ⇒ `gen_correctness`、`gen_answerability`、`gen_difficulty` 三项从 `missing_premise` 变可测 | **P0 前置：不补 ⇒ Generate 五项主指标无定义域，禁止出现在正式效果章** | 零 token，15 行 × 2 字段 ≈ **2 人时** |
| **G1b** | grade gold 只有 `{0, 100}` 两极 ⇒ `score_tolerance@±10` 目前只证明「模型有没有跟着说 0 或 100」，**没有中间地带可供 ±10 判别**。补非两极的 `human_score`（按真题扣分点折算）才能让该行主张「判分能力」 | **P0 前置（若保留 Grade 门槛行）**；不补则该行必须按 R5 记 `missing_premise`，不得记「已证明」 | 零 token，15 行 ≈ **2 人时** |
| **G2** | 只披露：主指标标「未测量」并登记 §20.7，机械两项作辅助呈现 | **降级方案**（不是平行选项） | 零成本，效果章少两行能拍胸脯的数 |

规则写成一句：**只有当 §6 门槛行愿意改标「未测量」时，G1 才可以不做。** 若效果章要保留
Generate/Grade 的百分数，G1a/G1b 就是正式实验的前置条件，排在 P0 之前。

**★ 盲标规程（防止「自标自证」）**：gold 必须是外部事实，不能从模型输出反推。
`model_answer → gold → correctness` 等于自己给自己出答案。

1. 标注**只读** `demo/generate_cases.jsonl` 的题面 + 选项 + KB 依据；
   `gold_review.jsonl` 本身不含 `system_output` 列（已核实），但同 case_id 的 `calibration_30.jsonl`
   （含 `system_output`，与 gold_review 的 case_id 重合 20 个）**在标注阶段不得打开**。
2. `review_fields` 增一个**必填** `gold_source_ref`，指向 KB 的 section/kp 出处——
   无出处的 gold 视为未填（V0 检查它）。
3. 先标后比：`gold_answer` 定稿后才允许与归档的模型答案对照。
4. 一条告警（非自动失败）：若 `gold_answer` 与归档模型答案键一致率 = 100%，
   触发「疑似反推」提示，需人工说明依据。

### 4.3 其余归因行

| 主张 | 现状 | 改为 |
|---|---|---|
| `gen_structure` | schema 能解析即 True（15/15） | 按 §3.1 `completeness_pass` 查四件套**逐一非空**；`contract_inputs` = 四个组件，四个 mutation 各必须变红 |
| `gen_coverage` | 15/15 True（#27 之后） | 保留 + R1-A 质询（抹掉任一 `knowledge_points` 必须变红，否则坐实判据没吃 KP） |
| Verify 归因 | `retrieval_miss`×15 与 `retrieval_status=ok`×15 并存 | `metrics.py:47-60` 优先级不动，但 `retrieval_miss` 改由 tier-0 门供给；judge 原因落 `judge_failure_reasons` |
| Memory 三维 | 读链故障与「没有卡」同为 `""`（`teaching_graph.py:44-46`→`memory_scorer.py:164-166`） | 见 §5 B4 的四态 `memory_read_status` |
| Grade `score_tolerance` | `degenerate_gold` 已披露（做法正确） | 泛化为 R1-A 的一个实例，无新逻辑 |

---

## 5. 业务链修复清单（二分）

裁决：**B1（top-up 语义与排序）现在修并接受重录基线；BM25 IDF 与 `k=5` 语义延后。**
二分的目的很具体：防止执行的人把它读成「B1 修了 ⇒ 业务侧已经全修完」。

### 5.A P0 Runtime Correctness —— **不修就禁止正式实验**（证据链本身会失真）

| # | 位置 | 改法 | 数字影响 |
|---|---|---|---|
| B1 | `rag/layer_recall.py:128-131` + `evidence_policy.py:138` | R4 语义统一后排序方向自然转正 | **会变**（top-up 选中的文档变了）→ 重录受影响路由 + 差异登记 §20.7 |
| B2 | `rag/pipeline.py:593` | ★ 不再只给布尔。新增 tier-0 枚举 **`rerank_status`**：`off` / `success` / `degraded`（调用成功但无分或空结果，回落原序）/ `failed`（抛错或超时走 `default`）。`rerank_used` 降级为**派生字段**：仅 `success ⇒ True`，其余全 `False`。派生条件判 **metadata 含 `rerank_score` 键**（`reranker.py:246` 有合法写 `0.0` 的路径，用真值判断会把假重排 `on` 路由误翻成 False，等于借修诚实度换基线）。★ `rerank_status` 要**落进 record**（含 `run --no-agent` 的检索探针归档），不能只进遥测 | **不变**（`RERANK_ENABLED=false` 时走 `:565-570` 已返回 False；`on` 路由 `_fake_rerank` 确实写分）。⇒ 消融从此能区分「重排关」与「重排开但坏了」 |
| B4 | `agents/teaching_graph.py:44-46` + `memory/safe.py` | 新增 tier-0 **`memory_read_status`** 四值 + 映射：<br>`not_attempted`（`uid is None`，`:43` 那条分支就是它，今天被压成 `""`）→ 三维 `None`<br>`success` + 命中期望值 → `recalled=True`；`success` 未命中 → `recalled=False`<br>`empty`（读成功但无卡）→ `recalled=False`<br>`failed`（超时/异常）→ 三维 `None`<br>⇒ 「这个 0.5 是不是 Store 挂了」变成**有证据可答**的问题 | 只影响今后归档；已归档 Memory 数标 `superseded`，新状态待重跑 |
| B7 | `rag/bm25.py:54-59`、`rag/vectorstore.py:142,340`、`evaluation/retrieval_gate.py:1262` | **检索失败必须传播**（本轮新增）：BM25 路由取 collection 失败时 `return []` 且**不写 `_query_failures`**（向量路径 `:340` 会写），而门禁的 `unexpected_query_failures` 只看 `_query_failures` ⇒ 词法路由整条坏掉时所有指标照常「健康」。改法：① 失败计入 `_query_failures`；② tier-0 的 `retrieval_status` 区分 `ok` / `empty` / `route_error`（供 §4.3 的归因门用）；③ `_query_failures` 可清零（append-only 在长跑服务里无界增长，且一次早期失败会污染整轮判定） | 基线数字预期不变（BM25 今天跑得通）；修的是「坏消息看不见」 |

### 5.B P1 Product Correctness —— **不修可以正式实验，但必须登记 limitation**

BM25 IDF 用截断候选池（`bm25.py:84,98-99`）、`k=5` 被当未指定（`retriever.py:186`、`pipeline.py:294`）、
`_rrf_scale_needed` 硬编码复刻阈值公式（`postprocess.py:89-97`）、parent-window 文本重复
（`splitter.py:229`+`postprocess.py:685`）、`weak_topics` 清除死分支（`weak_topics.py:91-93`）、
生产/评测聚合口径不一致（`:102`）、`difficulty="mixed"` 与子项 `Literal` 冲突（`questions.py:50` vs `:17,24`）、
`score` 越界不 clamp 而抛错（`grading.py:22`+`grading_core.py:29-30`）、`is_wrong`/`score` 不一致、
B3 空召回写缓存、B5 `/api/metrics` 鉴权与阻塞、B6 SSE 断连收尾。

★ **两条要特别盯**：`difficulty=mixed` 与 `score` 越界都会让整单失败并**计入 §6 的 `tool error <5%` 门槛行**。
⇒ 若正式实验那一行因此不达，这两条**自动从 5.B 升级到 5.A**（阻塞重跑），不能只登记 limitation。

### 5.C 只欠改口（今天连产品行为都不是）

`lightweight_rerank` 零消费方、`HYDE_RERANK_SCORE_THRESHOLD`
读方条件不可达（`hyde.py:35`）、`_raw_search` 抖动修复对向量路由是死代码（`routes.py:333`，
而 `kp_hit_flip_diag.py:95` 正 patch 在这个不可达函数上）、记忆卡语义锚点（`working.py:56,82` 与
`memory_step2_gate.py:180` 断言的不是同一件事）、question↔grade 闭环（`ref_episode_id` 无写入方，
`store.db` 中 0/58 条批改带 `batch_id`）。

---

## 6. 反向取证矩阵（mutation 必须覆盖 contract_inputs）

| 主张 | 弄坏动作（record 层） | 期望 |
|---|---|---|
| `gen_structure` | **逐个**删 `stem` / `options` / `answer_key` / `analysis` | 四次都必须变红；只删得出一次 = 判据其实只读一个字段 ⇒ R1-A 不过 |
| `gen_answer_key_validity` | 键改成 ∉ 选项集 / 制造两个正确项 | 各自变红 |
| `gen_analysis_agreement` | 解析结论改成与键相反的选项 | 变红，且 `final_quality` 不动（证明与 judge 解耦） |
| `gen_coverage` | 抹掉一条 `knowledge_points` | 变红 |
| Verify 归因 | 把 `retrieval_status` 改 `empty` | `primary_failure` 才允许 `retrieval_miss`；反向（ok 却报 miss）必须被拒 |
| Memory 三维 | 分别注入 `not_attempted` / `empty` / `failed` | 前→`None`、后两者→`False`/`None` 按 §5 B4 表；`failed` 绝不得出 `False` |
| `rerank_status` | 注入无分降级 | `status=degraded` 且派生 `rerank_used=False`；若仍 True ⇒ B2 未生效 |
| R5 复合 | 任一成分设 `missing_premise` | 复合 = `missing_premise`，**不得**为 `pass`（这就是 §4.2 事故的回归测试） |
| 三态推导 | 把取证 `config_hash` 改成旧值 | 状态从「已证明」自动降级 |

---

## 7. 文档承载

- **冻结件不动**；实现与冻结口径不一致 → 偏离登记进 `EXPERIMENTS.md` §20.7，不改原文。
  本方案新增**四处**待登记偏离：① §3.1 五项中 `correctness`/`answerability`/`difficulty` 三项在无 gold 时为
  `missing_premise`（走 G2 时）；② Grade gold 为两极 `{100:8, 0:7}`，`score_tolerance@±10` 的判别域受限；
  ③ R5 改变了复合指标的聚合语义（旧归档按新规则重算会得到不同状态词）；④ 5.B 全部延后项的 limitation 清单。
- **活文档勘误**（4 处；★ 一律**改成命令**而不是写死数字 —— 本文件自己就先被这条打过：
  写「16 份 / 27 份 / 204 项」时，`3e77e01` 已经把护栏抬到 216、把跟踪清单变成 17 份）：

  | 位置 | 过期声称 | 改成 |
  |---|---|---|
  | `docs/README.md:3` | 「标签待打」 | `git tag -l 'V-*' --format='%(refname:short) -> %(objectname:short)'` |
  | `docs/README.md:40` | 「现 129 项」 | `grep -n "^_EXPECTED_ITEMS" scripts/memory_step4fix_gate.py` 的生成值 |
  | `docs/README.md:73` | 「`git ls-files` = 0」 | `git ls-files evals/results/task_eval \| wc -l` 与 `git status --short -- evals/results/task_eval \| grep -c '^??'` 两条并列（前者已跟踪的仍是 `.md`，后者是数值工件） |
  | `CLAUDE.md:47` / `README.md:144` | `--dataset evals/sample_408.jsonl` | 实为 `evals/datasets/golden/sample_408.jsonl`（`src/evaluation/cli.py` 的默认值） |

- **数值工件纳入版本控制**：以 `git status --short -- evals/results/task_eval` 的 `??` 计数为准
  （本轮两次实测分别是 27 与 41 —— 数字会漂，命令不会）。「冻结、只读」在没有版本控制前只是措辞；
  跟踪后配合 `artifact_status`，旧数字留档而不冒充当前结论。
- `docs/README.md` 加一行指向生成的 `evals/claims/ledger.md`。

---

## 8. 验证与退出准则

| 步 | 内容 | 判据 |
|---|---|---|
| **V0** | **Evidence Record schema 完整性 + 未测量 predicate 拦截**（阻塞 P4） | ① 每条 `已证明` 主张所依赖的 tier-0/1 字段，**在归档里键真实存在**（键存在，非真值）。禁止 `.get(k, False)` / `.get(k, 0)` 掩盖缺字段（AST 检查，沿用 step4fix gate 已有的 AST 手法）；`gold_source_ref` 缺失的 gold 视为未填。② ★ **正式实验禁止依赖未测量 predicate**：`claim → required predicates → 任一 missing_premise ⇒ claim = unmeasurable ⇒ 禁止进入正式效果章的门槛行`。这条就是 §4.2 里「`gen_case_pass = 1.000` 而 correctness/answerability/difficulty 全 missing」的机械拦网，也是 G1a/G1b 排在 P0 之前的原因 |
| V1 | 按 registry 重算（`reanalyse`，零 token） | 每项带 tier + 四态 + reason；无恒真项被当门槛证据 |
| V2 | `task_eval sanity` | ERROR 0（现有护栏不变） |
| V3 | `falsify` 全矩阵 | 每条主张「恰好它变红」；且 mutation 覆盖其 `contract_inputs` 全集；红不了的自动降级并在 ledger 可见 |
| V4 | `build_claim_ledger` | §6 每行有状态词 + R1-B 签署状态；`已证明` 行数 = 论文可引用行数 |
| V5 | `retrieval_gate`（B1 后 6 条路由逐条）+ `probe_gate` | 基线重录 + 差异登记 §20.7；禁止静默 `--update-baseline` |
| V6 | `ruff check/format --check src/` + `pyrefly check` | 现状全绿（本轮实测：ruff 通过、130 文件已格式化、pyrefly 0 errors / 13 suppressed / 65 warnings） |

★ **V0 的阻塞范围要划清**（否则方案会把自己锁死在截止日期前）：

- **阻塞**：把 `missing_premise` 的族写进 §6 门槛行；把无鉴别力的行标成 `已证明`；5.A 或 V0 未过时进 P4 正式重跑。
- **不阻塞**：把某族明确披露为「未测量 + 原因 + 补救路线」。这类行可以出现在论文里，
  但只能以 **limitation** 的身份出现，不能以**成绩**的身份出现。
- ⇒ 落地成一句可执行的话：**Generate 与 Grade 两个门槛行，要么补 gold（G1a/G1b，零 token，合计约 4 人时），
  要么整族降为 limitation。没有第三条路。**

---

## 9. 次序与工作量（含成本明示）

| 阶段 | 内容 | 估量 | token |
|---|---|---|---|
| **P−1（前置，非可选路线）** | **G1a + G1b 盲标**：generate 15 行的 `gold_answer`+`expected_difficulty`；grade 15 行的非两极 `human_score`。按 §4.2 盲标规程执行 | **约 4 人时**（2+2） | **0** |
| P0.1 | Evidence Record schema（含 `rerank_status` / `memory_read_status` / `retrieval_status` 三个枚举）+ provenance 五项扩展 | 0.5 天 | 0 |
| P0.2 | tier 表 / registry / 单项四态 / `required_when` / **R5 复合与分母语义** | 0.5 天 | 0 |
| P0.3 | `predicates/` 拆包 + generate/verify/memory 判据（改名 + `missing_premise`）+ **删掉 `metrics.py`/`report.py` 的本地公式副本** | 1 天 | 0 |
| P0.4 | `falsify.py` + 取证矩阵 + `build_claim_ledger` | 1 天 | 0 |
| P1 | **V0**（schema 完整性 + 未测量 predicate 拦截 + AST 禁 default + `gold_source_ref` 必填）+ 文档 4 处勘误 + 数值工件跟踪 | 0.5 天 | 0 |
| P2 | 归因改写落地（judge 的 tier-0 归因门、`memory_read_status`）+ step4fix gate 增故障注入项 | 0.5–1 天 | 0 |
| P3 | **5.A 全部**（B1/B2/B4/B7）+ V5 | **1.5–2 天**（B1 改变被选中文档 ⇒ 下游 evidence/generation/verify/memory 逐条复看；6 条路由需 TEI 就绪 + 索引屏障，机器时间占大头） | 0（门禁本身） |
| P3' | 5.B 择要 + limitation 登记 + 5.C 改口文案 | 0.5 天 | 0 |
| P4 | §7.3 Freeze 全量重跑 | 已有计划 | ledger 取证时间届时整体刷新 |

**合计：约 6.5–7.5 个工程日 + 4 人时人工标注，全程零 token。**
P−1 不排在 P0.3 之前的唯一后果，是 P0.3 交付时 Generate/Grade 两个判据只能写成 `missing_premise`。

**风险**：
1. §4.2 —— R5 一落地，Generate 主指标在补 gold 前**不可出数**；Grade 的 `score_tolerance@±10`
   在两极 gold 下**只证明了对齐二值标注**（`metrics.py:450` 已自陈）。都是真相，不是退步，P−1 可解。
2. B1 重录基线可能让检索指标小幅后退 → 按既有纪律登记 §20.7 并说明理由，禁止静默 `--update-baseline`。
3. 本方案会让若干行的**强度**从「已证明」降为「已测量未证明」，论文里能拍胸脯的行数净减少；
   P−1 是把它们赚回来的唯一路径。
4. 5.B 里的 `difficulty=mixed` 与 `score` 越界会抬升 §6 的 `tool error`；若越过 5% 该行即不达
   ⇒ 这两条自动升级为 5.A（阻塞重跑），届时工作量另加约 0.5 天。
