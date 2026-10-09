# 主张 ledger（三态状态词 = 代码算出，EVIDENCE_CHAIN.md §1.1）

> **状态词不是人写的**：`claims.derive_status` 由五个布尔量推导（falsify_passed / tier_ok / discriminating / provenance_match / signed），五个布尔量全部从归档、falsify 取证件、真实校准集与 registry 重算而来。
> 本文档不含手写百分数：§6 最低要求运行时解析自冻结文档 `docs/EFFECT_PLAN.md`，数值一律从归档经 registry predicates / metrics 重算。
> ★ `falsify_passed=True` = mutation 取证成功（判据对它声明的每个契约输入都敏感、无附带损伤、无抛异常），**不是**「主张被证伪」。
> ★ falsify_latest.json 消费三口径（Task 5 披露）：① `all_flipped=False` 且基线全 pass ⇒ 读作 **partial**（形式覆盖、语义无操作，plan-mandated），不得当 full、不得算 proven；② 冻结名 `baselines_pass=False` 属**预期**（gold 未盲标、P−1 暂停，基线本就是 missing_premise）——不是失败，也不得算 proven；③ `inputs` 多 op 重复项已去重。
> ★ missing_premise 全链原样传播（predicates → composite/rate → 本表）：缺前提的行显示 `N/A（rate=None; …）`并在注记点名缺哪个前提，绝不折成 pass/fail。
> 本表汇总：已证明 0 行 / 已测量未证明 7 行 / 未测量 4 行；provenance_match=True 0 行；signed=True 0 行。

## §6 门槛行（EFFECT_PLAN.md §6 逐条）

| 维度 | 主指标（口径 = 重算） | 数值或 N/A | 状态词 | 前置（tier_ok 依据） | 证据锚点 | 复现命令 | R1-B 签署 |
|---|---|---|---|---|---|---|---|
| QA | final_quality≥4 的 case 占比（唯一公式 `metrics.quality_pass`；judge 观点 ⇒ tier 2，两个前置见「前置」列）<br>§6 最低要求：≥ 80% case `final_quality ≥ 4` | 0.933（已测 n=15, n/a=0） | **已测量未证明**<br>falsify✗ tier✗ disc✓ prov✗ sign✗ | [literal] tier 2 为字面量，锚点 §1.3-tier2；tier 2 两前置：boundary_calibrated=False（calibration_30 真实 human_score 分布算出；门槛 final_quality≥4 两侧各需 ≥3 样本）；repeat_jitter 非空=False（同 case 跨 --records 多份归档的 final_quality 极差；单份归档 ⇒ {} = 未量化） | 证据：`evals/results/task_eval/ec_r1_final_gate.jsonl`@sha256:a4f56a5d5ff1 | 复现：`PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py --records evals/results/task_eval/ec_r1_final_gate.jsonl` | 未签署（该行无 registry 支撑判据 ⇒ R1-B 无签署对象，恒 False） |
| Generate | 五项完整交付率 `gen_case_pass`（registry 逐题复合，§3.1 冻结五项；机械替身 optional 项只作诊断、永不顶替冻结名进本行）<br>§6 最低要求：≥ 75% 五项完整交付 | N/A（rate=None；已测 n=0, missing_premise=15, not_applicable=0） | **未测量**<br>falsify✗ tier✓ disc✗ prov✗ sign✗ | [registry] tier 1 派生自 registry 必需（非 optional）判据 max(tier)；tier 1（机械事实/可观测物证，不经 judge）⇒ 前置恒成立 | 证据：`evals/results/task_eval/ec_r1_final_gate.jsonl`@sha256:a4f56a5d5ff1；mutation 取证：`evals/claims/falsify_latest.json`@sha256:f58d78d1ee7b | 复现：`PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py --records evals/results/task_eval/ec_r1_final_gate.jsonl` | 未签署（0/7 判据；evals/claims/r1b_signatures.json 不存在 ⇒ 恒 False（待签）） |
| Grade | `score_tolerance@±10`（EFFECT_PLAN §3.1 头号；两极 gold ⇒ 行级判据改读 verdict_agreement 且只作辅助披露）<br>§6 最低要求：≥ 75% `score_tolerance@±10` | N/A（rate=None；已测 n=15, n/a=0） | **未测量**<br>falsify✗ tier✓ disc✗ prov✗ sign✗ | [literal] tier 1 为字面量，锚点 §1.3-tier1+G1b-revoked+§7-②；tier 1（机械事实/可观测物证，不经 judge）⇒ 前置恒成立 | 证据：`evals/results/task_eval/ec_r1_final_gate.jsonl`@sha256:a4f56a5d5ff1 | 复现：`PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py --records evals/results/task_eval/ec_r1_final_gate.jsonl` | 未签署（该行无 registry 支撑判据 ⇒ R1-B 无签署对象，恒 False） |
| Verify | 仍出题率 `ver_fabricated`（硬条件必须 0；D14 行为层把门——§6 原文 final_quality≥4 在 verify 上测的是检索覆盖，只作诊断）。值为**坏事率**<br>§6 最低要求：≥ 80% `final_quality ≥ 4` | 1.000（已测 n=15, missing_premise=0, not_applicable=0） | **已测量未证明**<br>falsify✗ tier✓ disc✓ prov✗ sign✗ | [registry] tier 1 派生自 registry 硬条件（非 optional）判据 max(tier)；tier 1（机械事实/可观测物证，不经 judge）⇒ 前置恒成立 | 证据：`evals/results/task_eval/ec_r1_final_gate.jsonl`@sha256:a4f56a5d5ff1；mutation 取证：`evals/claims/falsify_latest.json`@sha256:f58d78d1ee7b | 复现：`PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py --records evals/results/task_eval/ec_r1_final_gate.jsonl` | 未签署（0/1 判据；evals/claims/r1b_signatures.json 不存在 ⇒ 恒 False（待签）） |
| Memory | correct-use rate `memory_correct_use`（唯一公式 `metrics.memory_correct_use_from_record` 的 registry verdict 化）<br>§6 最低要求：≥ 80% correct-use rate | 0.800（已测 n=5, missing_premise=1, not_applicable=0） | **已测量未证明**<br>falsify✗ tier✓ disc✓ prov✗ sign✗ | [registry] tier 1 派生自 registry 该任务全部判据 max(tier)；tier 1（机械事实/可观测物证，不经 judge）⇒ 前置恒成立 | 证据：`evals/results/task_eval/ec_r1_final_gate.jsonl`@sha256:a4f56a5d5ff1；mutation 取证：`evals/claims/falsify_latest.json`@sha256:f58d78d1ee7b | 复现：`PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py --records evals/results/task_eval/ec_r1_final_gate.jsonl` | 未签署（0/1 判据；evals/claims/r1b_signatures.json 不存在 ⇒ 恒 False（待签）） |
| Retrieval | kp_hit 率（tier 0 机械字段，全任务池化重算；Memory 除外——非知识检索任务）。§6「不低于 V-2026-10-02」需基线归档对比，未接入本 ledger ⇒ 不下该结论<br>§6 最低要求：**不低于 V-2026-10-02** | 0.966（已测 n=29, n/a=31） | **已测量未证明**<br>falsify✗ tier✓ disc✓ prov✗ sign✗ | [literal] tier 0 为字面量，锚点 §1.3-tier0；tier 0（机械事实/可观测物证，不经 judge）⇒ 前置恒成立 | 证据：`evals/results/task_eval/ec_r1_final_gate.jsonl`@sha256:a4f56a5d5ff1 | 复现：`PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py --records evals/results/task_eval/ec_r1_final_gate.jsonl` | 未签署（该行无 registry 支撑判据 ⇒ R1-B 无签署对象，恒 False） |
| hard failure | `hard_fails` 非空的记录占比（**坏事率**，越低越好）<br>§6 最低要求：< 5% | 0.000（已测 n=66） | **已测量未证明**<br>falsify✗ tier✓ disc✓ prov✗ sign✗ | [literal] tier 0 为字面量，锚点 §1.3-tier0；tier 0（机械事实/可观测物证，不经 judge）⇒ 前置恒成立 | 证据：`evals/results/task_eval/ec_r1_final_gate.jsonl`@sha256:a4f56a5d5ff1 | 复现：`PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py --records evals/results/task_eval/ec_r1_final_gate.jsonl` | 未签署（该行无 registry 支撑判据 ⇒ R1-B 无签署对象，恒 False） |
| tool error | `failure_reason` 含 `tool_error` 的记录占比（**坏事率**；判定唯一来源 `runner.mechanical_failures`，检索返空 `empty` 属 retrieval 口径、不计入本行）<br>§6 最低要求：< 5% | 0.000（已测 n=66） | **已测量未证明**<br>falsify✗ tier✓ disc✓ prov✗ sign✗ | [literal] tier 0 为字面量，锚点 §1.3-tier0；tier 0（机械事实/可观测物证，不经 judge）⇒ 前置恒成立 | 证据：`evals/results/task_eval/ec_r1_final_gate.jsonl`@sha256:a4f56a5d5ff1 | 复现：`PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py --records evals/results/task_eval/ec_r1_final_gate.jsonl` | 未签署（该行无 registry 支撑判据 ⇒ R1-B 无签署对象，恒 False） |
| provenance | 嵌套 `provenance` 八键齐全的记录占比（§3；与当前版本是否一致另见 provenance_match 布尔量）<br>§6 最低要求：100% | 0.000（已测 n=66） | **已测量未证明**<br>falsify✗ tier✓ disc✓ prov✗ sign✗ | [literal] tier 0 为字面量，锚点 §1.3-tier0+§3；tier 0（机械事实/可观测物证，不经 judge）⇒ 前置恒成立 | 证据：`evals/results/task_eval/ec_r1_final_gate.jsonl`@sha256:a4f56a5d5ff1 | 复现：`PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py --records evals/results/task_eval/ec_r1_final_gate.jsonl` | 未签署（该行无 registry 支撑判据 ⇒ R1-B 无签署对象，恒 False） |
| Docker / TEI | 本 ledger 无该维度的归档证据源（需服务验收/演示记录接入后才可算）<br>§6 最低要求：一键启动成功 | N/A（无可算的归档证据） | **未测量**<br>falsify✗ tier✓ disc✗ prov✗ sign✗ | [literal] tier 0 为字面量，锚点 §6-no-archive；tier 0（机械事实/可观测物证，不经 judge）⇒ 前置恒成立 | 证据：无归档证据源（该维度未被 task_eval 归档覆盖 ⇒ 未测量） | 复现：`PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py --records evals/results/task_eval/ec_r1_final_gate.jsonl` | 未签署（该行无 registry 支撑判据 ⇒ R1-B 无签署对象，恒 False） |
| 四任务链 | 本 ledger 无该维度的归档证据源（需服务验收/演示记录接入后才可算）<br>§6 最低要求：全部可演示 | N/A（无可算的归档证据） | **未测量**<br>falsify✗ tier✓ disc✗ prov✗ sign✗ | [literal] tier 0 为字面量，锚点 §6-no-archive；tier 0（机械事实/可观测物证，不经 judge）⇒ 前置恒成立 | 证据：无归档证据源（该维度未被 task_eval 归档覆盖 ⇒ 未测量） | 复现：`PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py --records evals/results/task_eval/ec_r1_final_gate.jsonl` | 未签署（该行无 registry 支撑判据 ⇒ R1-B 无签署对象，恒 False） |

逐行注记（missing_premise 缺哪个前提、falsify 读数口径，全部在此点名）：

- **QA**：（无 registry 支撑判据 ⇒ 无 mutation 取证，falsify_passed 恒 False）
- **QA**：provenance_match：嵌套 provenance 齐全且与当前 code_version/golden_sha256 一致：0/15 条；归档顶层 code_version=eb8112f（当前值由 `provenance.code_version()` 运行时算出）
- **Generate**：gold 依赖判据（gen_answerability, gen_correctness, gen_coverage, gen_difficulty）的前提是盲标 gold（P−1，暂停中）；缺失时按契约记 missing_premise 并原样传播——诚实状态，不是失败，也不得折成 pass/fail
- **Generate**：缺前提明细：gen_answerability missing_premise 15/15（契约输入：gold.gold_answer, gold.gold_source_ref.gold_answer）
- **Generate**：缺前提明细：gen_correctness missing_premise 15/15（契约输入：reply#answer, gold.gold_answer, gold.gold_source_ref.gold_answer, reply#options_or_task）
- **Generate**：缺前提明细：gen_difficulty missing_premise 15/15（契约输入：gold.expected_difficulty, reply#difficulty）
- **Generate**：缺前提明细：gen_answer_key_validity missing_premise 15/15（契约输入：reply#answer, reply#options_or_task）
- **Generate**：缺前提明细：gen_analysis_agreement missing_premise 15/15（契约输入：reply#answer, reply#explanation, reply#options_or_task）
- **Generate**：gen_structure: all_flipped ∧ no_collateral ∧ no_raise ∧ baselines_pass ∧ 覆盖完整
- **Generate**：gen_answerability: all_flipped=False（基线本就 pass 不了，见 baselines_pass 注）；baselines_pass=False 属**预期**：该判据在归档上全 missing_premise（gold 前提不存在，P−1 盲标暂停中），基线本就 pass 不了——不是失败，但不得算 proven
- **Generate**：gen_coverage: all_flipped ∧ no_collateral ∧ no_raise ∧ baselines_pass ∧ 覆盖完整
- **Generate**：gen_correctness: all_flipped ∧ no_collateral ∧ no_raise ∧ baselines_pass ∧ 覆盖完整
- **Generate**：gen_difficulty: all_flipped=False（基线本就 pass 不了，见 baselines_pass 注）；baselines_pass=False 属**预期**：该判据在归档上全 missing_premise（gold 前提不存在，P−1 盲标暂停中），基线本就 pass 不了——不是失败，但不得算 proven
- **Generate**：gen_answer_key_validity: all_flipped ∧ no_collateral ∧ no_raise ∧ baselines_pass ∧ 覆盖完整
- **Generate**：gen_analysis_agreement: all_flipped=False ⇒ 读作 partial：部分声明 op 未翻转判据（形式覆盖、语义无操作，plan-mandated）——不得当 full，不得算 proven
- **Generate**：provenance_match：嵌套 provenance 齐全且与当前 code_version/golden_sha256 一致：0/15 条；归档顶层 code_version=eb8112f（当前值由 `provenance.code_version()` 运行时算出）
- **Grade**：退化 gold：human_score 仅 2 个不同取值 ⇒ ±10 容差无判别力（raw_rate=0.8667 仅诊断，不得当成绩；偏离登记 EVIDENCE_CHAIN §7 ②）
- **Grade**：行级替身（**辅助位，非门槛值**）：verdict_agreement=0.867（已测 n=15, n/a=0）
- **Grade**：（无 registry 支撑判据 ⇒ 无 mutation 取证，falsify_passed 恒 False）
- **Grade**：provenance_match：嵌套 provenance 齐全且与当前 code_version/golden_sha256 一致：0/15 条；归档顶层 code_version=eb8112f（当前值由 `provenance.code_version()` 运行时算出）
- **Verify**：值口径：rate 越高越坏（1.000 = 每条仍在编造真题）；门槛要求见 §6 原文列
- **Verify**：ver_fabricated: 无 mutation 取证行（取证矩阵未覆盖该判据）⇒ falsify_passed=False
- **Verify**：provenance_match：嵌套 provenance 齐全且与当前 code_version/golden_sha256 一致：0/15 条；归档顶层 code_version=eb8112f（当前值由 `provenance.code_version()` 运行时算出）
- **Memory**：分母摊开（D15）：正样本 3 条 ⇒ 前置成立 2 条（不可测 1 条）、证据链可查 2 条——n=1 的率不是能力率
- **Memory**：memory_correct_use: 无 mutation 取证行（取证矩阵未覆盖该判据）⇒ falsify_passed=False
- **Memory**：provenance_match：嵌套 provenance 齐全且与当前 code_version/golden_sha256 一致：0/6 条；归档顶层 code_version=eb8112f（当前值由 `provenance.code_version()` 运行时算出）
- **Retrieval**：（无 registry 支撑判据 ⇒ 无 mutation 取证，falsify_passed 恒 False）
- **Retrieval**：provenance_match：嵌套 provenance 齐全且与当前 code_version/golden_sha256 一致：0/60 条；归档顶层 code_version=eb8112f（当前值由 `provenance.code_version()` 运行时算出）
- **hard failure**：（无 registry 支撑判据 ⇒ 无 mutation 取证，falsify_passed 恒 False）
- **hard failure**：provenance_match：嵌套 provenance 齐全且与当前 code_version/golden_sha256 一致：0/66 条；归档顶层 code_version=eb8112f（当前值由 `provenance.code_version()` 运行时算出）
- **tool error**：（无 registry 支撑判据 ⇒ 无 mutation 取证，falsify_passed 恒 False）
- **tool error**：provenance_match：嵌套 provenance 齐全且与当前 code_version/golden_sha256 一致：0/66 条；归档顶层 code_version=eb8112f（当前值由 `provenance.code_version()` 运行时算出）
- **provenance**：（无 registry 支撑判据 ⇒ 无 mutation 取证，falsify_passed 恒 False）
- **provenance**：provenance_match：嵌套 provenance 齐全且与当前 code_version/golden_sha256 一致：0/66 条；归档顶层 code_version=eb8112f（当前值由 `provenance.code_version()` 运行时算出）
- **Docker / TEI**：（无 registry 支撑判据 ⇒ 无 mutation 取证，falsify_passed 恒 False）
- **Docker / TEI**：provenance_match：无归档记录可核对 ⇒ 保守判不符
- **四任务链**：（无 registry 支撑判据 ⇒ 无 mutation 取证，falsify_passed 恒 False）
- **四任务链**：provenance_match：无归档记录可核对 ⇒ 保守判不符


## 判据级三态（registry 全量重算 · 诊断附表）

> ★ `falsify=✓` 但「归档重算」n=0 有效测量（全 missing_premise，如 `gen_correctness`）时，状态词仍是「已测量未证明」——这来自**冻结公式**（brief Step 2 / `claims.derive_status`：只有 `not discriminating and not falsify_passed` 才判「未测量」），本表逐字执行、不改判。
> ★ 该格里 mutation 取证测的是**判据对契约输入的敏感性**（取证夹具自带 gold ⇒ 能翻转），**不是主张的数值**；数值一侧在真实归档上仍全 missing_premise（P−1 盲标暂停中）。§1.1 表把「gold 前提不存在」列为未测量，与 Step 2 公式在这一格上口径不一致（证据：`docs/EVIDENCE_CHAIN.md` §1.1 ↔ 本 brief Step 2 冻结公式）—— 属计划级缺口，已登记，待 Task 10 文档收口。
> ★ 债的可见性（Task 7 Step 4b）：`tier 依据` 列里的 `TIER-DEBT-task3` 是**债标记**、不是依据 —— 标着它的判据，其 tier 值与 §1.3 的证据种类**不符**（`fn` 是确定性字符串/字段比较，按定义应为 tier 0/1，却写着 2），已登记为 Task 3 遗留债、本轮只登记不改。护栏 `7g` 通过的语义是「债名单与登记一致」，**不是**「债务已清偿」；清偿（改 tier）时 `7g` 会红，必须同步删除这条登记。

| 判据 | task | tier | tier 依据（白名单锚点／债标记） | 归档重算 | falsify | tier_ok | disc | prov | sign | 状态词 |
|---|---|---|---|---|---|---|---|---|---|---|
| gen_structure | generate | 1 | §1.3-tier1 | 1.000（已测 n=15, missing_premise=0, not_applicable=0） | ✓ | ✓ | ✓ | ✗ | ✗ | 已测量未证明 |
| gen_answerability | generate | 1 | §1.3-tier1 | N/A（rate=None；已测 n=0, missing_premise=15, not_applicable=0） | ✗ | ✓ | ✗ | ✗ | ✗ | 未测量 |
| gen_coverage | generate | 1 | §1.3-tier1 | 1.000（已测 n=15, missing_premise=0, not_applicable=0） | ✓ | ✓ | ✓ | ✗ | ✗ | 已测量未证明 |
| gen_correctness | generate | 1 | §1.3-tier1 | N/A（rate=None；已测 n=0, missing_premise=15, not_applicable=0） | ✓ | ✓ | ✗ | ✗ | ✗ | 已测量未证明 |
| gen_difficulty | generate | 1 | §1.3-tier1 | N/A（rate=None；已测 n=0, missing_premise=15, not_applicable=0） | ✗ | ✓ | ✗ | ✗ | ✗ | 未测量 |
| gen_answer_key_validity | generate | 2 | TIER-DEBT-task3 | N/A（rate=None；已测 n=0, missing_premise=15, not_applicable=0） | ✓ | ✗ | ✗ | ✗ | ✗ | 已测量未证明 |
| gen_analysis_agreement | generate | 2 | TIER-DEBT-task3 | N/A（rate=None；已测 n=0, missing_premise=15, not_applicable=0） | ✗ | ✗ | ✗ | ✗ | ✗ | 未测量 |
| memory_correct_use | memory | 1 | §1.3-tier1 | 0.800（已测 n=5, missing_premise=1, not_applicable=0） | ✗ | ✓ | ✓ | ✗ | ✗ | 已测量未证明 |
| ver_fabricated | verify | 1 | §1.3-tier1 | 1.000（已测 n=15, missing_premise=0, not_applicable=0） | ✗ | ✓ | ✓ | ✗ | ✗ | 已测量未证明 |
| ver_exam_item_cited | verify | 1 | §1.3-tier1 | 0.467（已测 n=15, missing_premise=0, not_applicable=0） | ✗ | ✓ | ✓ | ✗ | ✗ | 已测量未证明 |
| ver_exam_year_only | verify | 1 | §1.3-tier1 | 0.133（已测 n=15, missing_premise=0, not_applicable=0） | ✗ | ✓ | ✓ | ✗ | ✗ | 已测量未证明 |

falsify_passed 逐判据读数（三条口径见页首）：

- `gen_structure`：all_flipped ∧ no_collateral ∧ no_raise ∧ baselines_pass ∧ 覆盖完整
- `gen_answerability`：all_flipped=False（基线本就 pass 不了，见 baselines_pass 注）；baselines_pass=False 属**预期**：该判据在归档上全 missing_premise（gold 前提不存在，P−1 盲标暂停中），基线本就 pass 不了——不是失败，但不得算 proven
- `gen_coverage`：all_flipped ∧ no_collateral ∧ no_raise ∧ baselines_pass ∧ 覆盖完整
- `gen_correctness`：all_flipped ∧ no_collateral ∧ no_raise ∧ baselines_pass ∧ 覆盖完整
- `gen_difficulty`：all_flipped=False（基线本就 pass 不了，见 baselines_pass 注）；baselines_pass=False 属**预期**：该判据在归档上全 missing_premise（gold 前提不存在，P−1 盲标暂停中），基线本就 pass 不了——不是失败，但不得算 proven
- `gen_answer_key_validity`：all_flipped ∧ no_collateral ∧ no_raise ∧ baselines_pass ∧ 覆盖完整
- `gen_analysis_agreement`：all_flipped=False ⇒ 读作 partial：部分声明 op 未翻转判据（形式覆盖、语义无操作，plan-mandated）——不得当 full，不得算 proven
- `memory_correct_use`：无 mutation 取证行（取证矩阵未覆盖该判据）⇒ falsify_passed=False
- `ver_fabricated`：无 mutation 取证行（取证矩阵未覆盖该判据）⇒ falsify_passed=False
- `ver_exam_item_cited`：无 mutation 取证行（取证矩阵未覆盖该判据）⇒ falsify_passed=False
- `ver_exam_year_only`：无 mutation 取证行（取证矩阵未覆盖该判据）⇒ falsify_passed=False


## mutation 取证消费结果（falsify_latest.json，inputs 已按口径③去重）

| 判据 | inputs（去重） | all_flipped | no_collateral | no_raise | baselines_pass | falsify_passed |
|---|---|---|---|---|---|---|
| gen_analysis_agreement | reply#answer, reply#explanation, reply#options_or_task | ✗ | ✓ | ✓ | ✓ | ✗ |
| gen_answer_key_validity | reply#answer, reply#options_or_task | ✓ | ✓ | ✓ | ✓ | ✓ |
| gen_answerability | gold.gold_answer, gold.gold_source_ref.gold_answer | ✗ | ✓ | ✓ | ✗ | ✗ |
| gen_correctness | reply#answer, gold.gold_answer, gold.gold_source_ref.gold_answer, reply#options_or_task | ✓ | ✓ | ✓ | ✓ | ✓ |
| gen_coverage | top_items[].kp, gold.expected_kp | ✓ | ✓ | ✓ | ✓ | ✓ |
| gen_difficulty | gold.expected_difficulty, reply#difficulty | ✗ | ✓ | ✓ | ✗ | ✗ |
| gen_structure | reply#stem, reply#options_or_task, reply#answer, reply#explanation | ✓ | ✓ | ✓ | ✓ | ✓ |


## 工件状态（claims.artifact_status）

| path | status | superseded_by | reason |
|---|---|---|---|
| evals/results/task_eval/ec_r1_final_gate.jsonl | active | — | — |
| evals/claims/falsify_latest.json | active | — | — |
| evals/datasets/demo/calibration_30.jsonl | active | — | — |

> 本 ledger 当前只登记 active；历史归档的 superseded 标注由 Task 10 收尾。
