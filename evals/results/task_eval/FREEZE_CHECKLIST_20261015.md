# 冻结前检查清单（FREEZE_CHECKLIST · 2026-10-15）

> **用途**：项目冻结（`EFFECT_PLAN.md §7.3` Final Freeze）前的唯一核对清单。与 `HANDOVER.md`（进度）、`PHASE0_FREEZE.md`（Phase 0B 冻结快照）配套使用。
> **协议锚点**：冻结判据 = `EFFECT_PLAN.md §7` + `docs/EVIDENCE_CHAIN.md` §8 V0~V6 + §4.4 P−1 冻结规程；门槛行 = `EFFECT_PLAN.md §3.1/§6`（v1.0 冻结，不因结果改动）。
> **状态基准日**：2026-10-15 实测（HEAD `d1ce8df`，工作树干净）。所有「状态」列为当日实测值，完成一项改一处，**不许整表重抄**。

## 0. 状态快照（2026-10-15 实测）

| 门禁/项 | 状态 | 取证命令（Windows 一律带 `PYTHONIOENCODING=utf-8`） |
|---|---|---|
| evidence_chain_gate | ✅ 81 项全绿 | `PYTHONPATH=src uv run python scripts/gates/evidence_chain_gate.py` |
| ledger `--check` 第 1 段（文档==重算） | ✅ PASS | 见 B1 命令 |
| ledger `--check` 第 2 段（R3 孤立结论） | ✅ PASS（2026-10-16 B4 清零：254+2+4 条逐条回验挂锚） | 同上 |
| ledger `--check` 第 3 段（V0 拦截） | 🟡 **① PASS / ② FAIL**（2026-10-15 A2 后定格）：① 4 组 ×15 缺键**已清零**（gold 快照注入 `ec_r2` 新归档）；② generate/`gen_answerability`+`gen_correctness` 仍全 missing_premise——**owner 已裁定走 option B（limitation 披露，§20.7.6④）：generate 两判据按现行契约缺「人工可判定性结论」输入，结构性不可机械清偿，不得把 missing_premise 当成绩** | 见 B1 命令 |
| P−1 答案键抽查 | 🟡 **已核验 59/59，结论 fail**：错键 14/59 = **23.7%**；**扩查 126 行已执行（第三方页读数，暂定 35/78/13，机械复算 126/126 一致）**；错键确认环节待**正式原卷盲读复核**（读数为第三方页值 ⇒ (e) 未触发、(d) 暂缓）；明细 `P1_KEY_AUDIT_20261015.md` + §20.7.7 | `evals/claims/p1_key_audit_sample.json` · `evals/claims/p1_expanded_audit_20261015.json` |
| R1-B 签署 | ✅ **已签（映射已审≠已测）**：`evals/claims/r1b_signatures.json` 11 判据在册 ⇒ ledger `signed=3` 行（Verify / Generate / Memory；QA / Grade 无 registry 判据照实未签） | ledger 主表「R1-B 签署」列 |
| §6 门槛全量读数 | ❌ 无：10-08 全量跑 Generate 0.733 不达；锚点⑤ generate-only 13/15=0.867（单臂） | `docs/EXPERIMENTS.md §22` |
| provenance_match | ❌ 0/66（`ec_r2` 为混合代际：gen `code_version=6610ef1`、其余 `eb8112f`，均 ≠ 当前；且归档 `golden_sha256` 为运行期值 `be98912a`，现行 dataset 已再变更——C1 重跑后转正） | ledger 逐行注记 |
| pytest / ruff / 默认检索门禁 / memory 护栏 | ✅ **26/26**（含 B2 极性回归 7 项）· ruff 0 · exit 0 · 217/217 | `uv run pytest -q` · `uv run ruff check src/ tests/` · `PYTHONPATH=src uv run python -m evaluation.gates.retrieval_gate` · `PYTHONIOENCODING=utf-8 … python scripts/mem/memory_step4fix_gate.py` |

---

## A. 人工动作（零 token，全部阻塞后续）

- [x] **A1 P−1 剩余核验 + 错键处置链**（2026-10-15 人工核验完成，结论 fail；**owner 有条件采纳已登记**；扩查已执行登记、正式复核 2026-10-16 已闭环落地，见下与 §20.7.8⑭）
  - ✅ 52 题读数由用户对照原卷完成（源键列已与 items.md 机械校验一致）；工作单 `evals/results/task_eval/P1_KEY_AUDIT_20261015.md` 已重写为结果版（45 pass / 14 fail / 0 pending；错键率 23.7%；分层明细：2009·2011·2015·2019·2021·2024·2025 七层降级）。
  - ✅ **owner 裁定（有条件采纳，2026-10-15；全文登记见 `docs/EXPERIMENTS.md` §20.7.6⑤）**：(a) 已生效（停引键可靠结论）；(b) 采纳 + **carve-out**——降级只针对键可靠性结论，**不追溯已独立人工核验的 gold 值**（grade 15 条 `human_score` 10-14 已独立核验；指针 12/15 落降级层但逐键 14/15 通过，唯一 fail = grd-002/2009-Q11 已按 (d) 处置）；(c) 扩查采纳、**成本订正 ≈4–5 人时**（原 ≈1.5–2 低估约 3 倍）；(d) 采纳但**排在 (c) 之后**；(e) 扩查再现错键 ⇒ exams 链暂停作 gold 出处，**与 (c) 一起预授权**（触发即执行，不再二次请示）。
  - ❌ **扩查已执行但未闭环（2026-10-15 晚，§20.7.7）**：owner 填写版 `P1_EXPANDED_AUDIT_20261015_filled.md`（sha256 `f59bfec7977d4237…`）入仓，项目方机械复算 **126/126 行与工作单 verdict 列一致**（暂定分布 35/78/13）。⚠️ **读数来源限定（引用必须随附）**：126 个读数是**第三方公开页**值、非官方原卷盲读 ⇒ 78 条「不一致」全为**暂定**，不构成 (e) 触发条件、不追加 `correct_key`（样本 JSON 未动）、不改键。不一致集中在六个出错层（2011 15/16、2015/2019/2021/2024 各 13、2025 11），**相邻批次 10 行零不一致**；2011 非选项平移模式；13 行 `answer_key: null` 已核实（空键出处问题**不待复核即成立**）。**(c) 的「错键确认」环节待正式原卷盲读复核（优先队列：2011 十六条 + 78 条清单）**；(d) 暂缓；(e) 未触发（按工作单自述触发条件）。
  - ✅ **正式复核已完成并落地（2026-10-16，§20.7.8⑭）**：owner 组织的人工交叉复核（报告 `evals/results/task_eval/A1_REVIEW_REPORT_20261016.md`，sha256 `7aafc4dab9ad5ea8…`）——78 条差异题第三方读数×公开年度答案表逐项一致、题库旧键全部不符；13 条空键给出公开参考答案；verify 2 题（2009-Q11→C / 2011-Q5→C）与已登记值一致。机械核验 0 错误（旧键 vs items.md 78/78、缺键 13/13、双源 91/91）。按 owner「双落地」口径：`exam_answer_corrections.json` 追加 91 条（4→95，评测侧覆盖、KB 不回写）+ 台账 `evals/claims/A1_KEY_CORRECTIONS_20261016.json`（sha256 `8e18e2bac7be0b3c…`）。⚠️ 证据等级披露：公开答案表为高校存档页参考答案（非官方标准答案）、91 键仓库题干/选项与原卷同题性未逐字验证（若选项重排须重映射）。**(e) 经 owner 2026-10-16 书面裁定暂不触发**（证据等级未达触发条件原文「正式原卷复核」；实际保护已在位：(a) 停引 / (b) 降级+carve-out / (d) 91 键评测侧订正且旧值保留可回退）。
  - 通过判据：扩查完成并登记；处置链 (b)–(e) 全部执行留痕；样本量/种子/分层未被改动。

- [x] **A2 generate 15 行 gold 盲标回填**（2026-10-15 人工盲标完成 + 机械收尾完成）
  - ✅ 工作单已备：`evals/results/task_eval/GEN_GOLD_BLINDLABEL_20261015.md`（15 case，题干已从锚点⑤归档剥离出、系统标准答案不显示，`gold_answer` / `expected_difficulty`（basic/medium/hard）留空待人填）。**必须人工盲标**（禁止回头看系统答案）。
  - ✅ **盲标完成（用户执行）**：结果表入仓 `evals/results/task_eval/GEN_GOLD_BLINDLABEL_20261015_filled.md`（sha256 与 Downloads 原件一致）——**13 条 present + gen-005 `incomplete_source`（选择题选项缺失，第 1 小题已算）+ gen-009 `missing_key`（归档 `generation_ok=false`，无题干不得臆造）**。盲态披露：gen-001~005 定位 gen-009 时暴露过系统答案 ⇒ 五条挂「需第二标注者复核」；gen-001 人类独立算得组索引 210 ≠ 系统答案 46；gen-012 题面歧义 / gen-014 平手规则未指定，均入 `needs_review`/`notes`。
  - ✅ **机械收尾完成**：回填 `evals/datasets/demo/generate_cases.jsonl`（`gold_answer`/`expected_difficulty`/`gold_source_ref`/`gold_answer_status` 四件套；`gold_status` 13→reviewed，gen-005/009 保持 draft；行尾 LF 未变，diff 仅 15 数据行）⇒ `task_eval sanity` **ERROR 0**（PENDING 1 = grade 两极分布的集合级存量项，与回填前同一状态）。
  - ❗ **未达 15/15 无缺口**：gen-005 需补齐选项、gen-009 需重生成题干后才可标；修复后需复跑 sanity/backfill/ledger（见 §20.7.5 登记）。

- [x] **A3 R1-B 逐判据签署**（2026-10-15 按 owner 裁定签署落盘）
  - ✅ 11 个 registry 判据（verify 3 + generate 7 + memory 1，`registry.for_task` 可枚举）已签入 `evals/claims/r1b_signatures.json`；**签署口径逐条目内嵌**：`signing_scope` = registry↔`EFFECT_PLAN.md §3.1` **映射已审、非「已测」**（owner 裁定原文：「A3 可签（注明是『映射已审』非『已测』）」，授权留痕见 §20.7.6⑦）。ledger signed 列随文件在册转真（signed=True 3 行：Verify / Generate / Memory；QA / Grade 无 registry 判据 ⇒ 恒无签署对象，照实未签）。
  - 边界不变：QA / Grade / Retrieval / hard failure / tool error / provenance 行**无 registry 判据 ⇒ 永远停在「已测量未证明」**——引用时只能带披露，不得当成绩。
  - 通过判据：ledger 主表 signed 列按签署变真 ✅；`--check` 第 1 段仍 PASS ✅。owner 如对任何条目有异议可单独划除（划除即该判据回到未签状态）。

- [ ] **A4 `gold_status` reviewed→frozen 最终裁决**（38 条审核已执行并回填；6 条 needs_fix 全部修复闭环——qa-011/ver-015 文本改写、gen-005/009/mem-001/004 修复+盲态复核签署；**全集 reviewed 66 / draft 0**。A1 正式复核 2026-10-16 已闭环——(d) 91 键评测侧订正落地（§20.7.8⑭）、(e) owner 裁诀暂不触发 ⇒ **frozen 裁决的人工前置已清空，仅剩 owner 裁决本身**）
  - ❗ **owner 裁定（2026-10-15）：「66 条 reviewed→frozen」前提不成立——实测 66 条 = reviewed 28（generate 13 + grade 15）/ draft 38（qa 15 + verify 15 + generate 2 + memory 6）** ⇒ 升格 frozen 前必须**先完成 38 条 draft 的审核**，审核工作单：`evals/results/task_eval/GOLD_REVIEW_38DRAFT_20261015.md`（逐任务口径 + verify 2 条撞错键（ver-002/ver-007，19:30 已由 5 条更正）与 A1 扩查并批 + 收口链）。
  - ✅ **审核执行完毕（2026-10-15 20:00，§20.7.8）**：filled 件 `GOLD_REVIEW_38DRAFT_20261015_reviewed.md`（sha256 `8a6cf96a6078b7a3…`）入仓，32 pass / 6 needs_fix 机械解析与聊天汇总一致；**32 条已回填 reviewed + 四件套**（verify 14 条 ref 按 expected_question_ids 机械派生），6 条 needs_fix（qa-011 / ver-015 / gen-005 / gen-009 / mem-001 / mem-004）维持 draft + notes 修正方向；回填后 **reviewed 60 / draft 6**；sanity ERROR 0 / PENDING 1（存量）；ledger 已重建（数据集 sha 刷新），`--check` 第 1 段 PASS。
  - 动作（剩余 4 条修复 + A1 闭环后）：owner 裁决 reviewed→`frozen`（2026-10-06 曾裁 `reviewed`，明示「出论文数字前需最终升为 frozen」）；gold sha256 记入新归档 provenance。
  - 通过判据：38 条审核全部留痕（人工签、脚本不代签）✅ → sanity ERROR 0 ✅ → 6 条 needs_fix 修复复核（qa-011/ver-015 ✅ 2026-10-15 20:50；gen-005/gen-009/mem-001/mem-004 ✅ 2026-10-16 补丁已拼接入仓、gold_status 按补丁维持 draft，待第二标注者盲态复核签署后升 reviewed）→ owner 书面裁决 frozen ⏳。

---

## B. 零 token 机器重算（A 全部完成后才允许开始）

- [x] **B1 新 gold 派生新归档 + ledger 重建 + 三段 check**（2026-10-15 完成；**owner 已复核维持 ec_r2**）
  - ✅ **完成**：gold 注入脚本 `scripts/lib/gold_blindlabel_apply_20261015.py`（gen 记录取自锚点⑤复测归档 anchor5 + 注入现行 dataset gold 快照，其余 51 条逐字节继承 ec_r1；判据不手写）→ `ec_r2_goldinjected_20261015.jsonl` → 官方 `task_eval backfill` → **`ec_r2_final_gate_20261015.jsonl`** → `build_claim_ledger.py` 重建 `evals/claims/ledger.md`。
  - ✅ **三段 check**：第 1 段 PASS（文档==重算）；**V0 ① 60 处缺键清零 PASS**；V0 ② generate/gen_answerability+gen_correctness 仍全 missing_premise（预期红，三条根因见 B6 与 §20.7.5④）；第 2 段孤立行号集无新增。
  - ✅ **归档代际已由 owner 复核（2026-10-15 裁定）：维持 ec_r2 混合代际**（备选「保持 ec_r1 + V0 ① 留红至 C1」未采纳）；§20.7.5② 的实测依据（同 case_id 题干不同 ⇒ 直接挂 gold = 假 gold）即为裁定留痕。登记：§20.7.6⑥。
  - Generate 行读数变化（口径连读）：`N/A（n=0, mp=15）` → `0.000（已测 n=1, mp=14）`——唯一已测条 gen-009 复合 fail；**0.000 不是「15 条里 0 条齐全」**，与 §22 的 0.733（judge 口径）不可混读。
  - 登记：`docs/EXPERIMENTS.md §20.7.5` + `evals/claims/artifact_status.json`（ec_r1→superseded；anchor5 指针订正为 ec_r2；新增 goldinjected/ec_r2）。

- [x] **B2 订正 `ver_fabricated` 分歧——owner 第三路「改 backfill 落盘口径」已执行**（2026-10-15，§20.7.6①）
  - **定性订正（owner：「过期字段」不准；实测更严重）**：同名字段**两个写入方、极性相反**——runner 直写 **metric 极性**（True=仍出题=坏事，phase1 代）vs backfill 按 registry 落 **verdict 极性**（True=pass=好事，ec 代）。ec_r2（active）从 ec_r1 逐字节继承 ⇒ 同病属实；**选项①实测修不了**（registry 重算与 ec_r1/ec_r2 存储值逐位一致，重 backfill 幂等）。
  - **已实现假红**：ec_r1/ec_r2 的 `.report.json` 边车 `ver_fabrication=1.000`（按 §6「必须 0」读即 100% 编造；实情 0/15）。ledger 不受影响（`p.fn(r)` 实时重算）。
  - ✅ **修复**：runner 改走 registry 判据 + 同写 `item_reasons` 标记（两写入方同源同极性）；`report._fabrication_flag` 凭标记无歧义解码；`cli._backfill` 覆盖已存值显式记账（WARNING）；`_runner_record` 字段注释补极性说明；ec_r2 边车按修复代码**重生**（1.000→**0.000**，归档 jsonl 一字节未动）；`tests/test_verify_fabrication_polarity.py` 7 项回归全绿。telemetry schema（`use_llm_verify` 等字段）保留不动，历史日志可解析。

- [x] **B3 订正 ledger Verify 行「值口径」注记极性**（10-15 新发现，未登记）
  - 事实：该行显示的是判据**通过率**，1.000 = 15/15 未编造（= §22 达线）；注记「rate 越高越坏（1.000 = 每条仍在编造真题）」写反，引用 ledger 时有误导风险。
  - ✅ **已完成（2026-10-15）**：修订 `scripts/lib/_ledger_rows.py` Verify 行 metric 文本与 notes（只改文本、不改判定，走 B16 路径）→ 重建 `evals/claims/ledger.md` → `--check` 第 1 段复跑 PASS；evidence_chain_gate 81 项仍全绿；ruff check/format 干净。遗留：`docs/EXPERIMENTS.md` 尚无该订正的登记行（随下一批文档收尾补 §20.5）。

- [x] **B4 清理 R3 孤立结论（`--check` 第 2 段）**（2026-10-16 ✅）
  - 动作：按第 2 段打印的行号（`docs/EXPERIMENTS.md` / `docs/README.md` / `CLAUDE.md`）逐条补来源锚点；补一条红名单消一条，不动代码。
  - 通过判据：第 2 段 FAIL 条目收敛到 owner 认可的存量（本项非阻塞，可在 §7.3 收尾前完成）。✅ **已清零**（§20.7.8⑬）：164 条挂现存归档（数值容差回验）+ 90 条 git log -S 溯源引入提交 + 4 条按被引对象挂锚。

- [x] **B5 §7.1 dead code 三项裁定（2026-10-15 owner 裁定并已执行，§20.7.6②）**
  - 裁定与执行：① `asearch_episodes` = **登记**（已不在 `src/`，仅登记不存在事实）；② **verifier LLM 层已删**（`verifier.py` 的 `_arun_llm_relevance_check`/`llm_relevance` 权重分支、`retriever_retry.py` 的 `_llm_verify`/`_apply_retry_hints`、`retriever.py` 的 `_verify_with_optional_retry`/`use_llm_verify`/`max_retries` 参数链与 5 个调用点的显式 False 传参一并移除；规则层 verdict 路径不变）；③ `_sse` 回传过滤（`src/service/_sse.py`）= **带披露保留**（代码自述「没有活路径、有备无患」，登记于 §20.7.6②）。
  - 删除后回归：`pytest` 26/26 · `ruff check src/` 全绿 · 默认路由检索门禁 exit 0（假 embedding）。
  - 通过判据：三项各有「已删/已接线/带披露保留」三态之一的明确记录。✅

- [x] **B6 `gen_difficulty` 中文难度行无映射（2026-10-15 owner 裁定：选项② + 修 docstring，§20.7.6③）**
  - **裁定**：暂行登记「机械判据适用域不含中文难度行」（选项②）；**不补**中文映射——补映射属判据口径变更，且映射取法非唯一（见下），不为凑读数临时改契约。docstring 已修（`metrics.difficulty_of` 不再声称 `:664` 已映射；实际抽取到的 14/15 是「理解」（认知层次动词）、非难度档，映射表扩词才有得读，纯口径裁决）。
  - 登记（§20.7.6③）：三种取法同一份数据三种读法——「理解→3 + ±1 容差」0.714、「理解→3 + 精确匹配」1/14=0.071、「只补表不扩词」实际侧恒 None ⇒ 可测率 0.000 ⇒ 三者非唯一，正好说明选项①后果依赖映射取法。
  - 影响面不变：`gen_difficulty` 是 optional 诊断位（query 0/15 提难度），不进复合主指标；V0② 披露见 E 段。

---

## C. 全量重跑（烧 token；TEI 就绪 + 真密钥；B 全绿后才允许开始）

> 次序红线：`gold_status`/`golden_sha256` 会随 gold 变，**先重跑等于把 draft 的数字再取一遍**——A/B 未完成不得开跑（HANDOVER ⑶）。

- [x] **C0 前置**（2026-10-16 执行，三层冒烟全过；登记 §20.7.8⑮）
  - TEI 就绪：`docker start tei-embedding tei-rerank` + `PYTHONPATH=src uv run python scripts/ops/tei_ready.py`（`/health` 200 ≠ 模型就绪）。
  - 配置口径核对：agent=`deepseek:deepseek-flash` · judge=`dashscope:qwen3.8-flash` · RAG=`dashscope:qwen3.7-flash` · `STRUCTURED_OUTPUT_METHOD=function_calling`（PHASE0_FREEZE §一）；任何偏离须提前登记。
  - `task_eval sanity` ERROR 0（进 0B 级操作前必跑）。
  - **冒烟测试（owner 批 token 的前置条件）**：零 token 层 `--limit 1 --no-agent` 全任务检索链 ✓；最小 LLM 层 `--limit 1` 真跑（n=5，QA/Grade/Memory 5.0 零失败；Generate/Verify 各 1 条 n=1 单样本内容层现象）；归档层 5 条 record provenance 9 键齐备 ✓。

- [x] **C1 §7.3 全量重跑 66 条**（2026-10-16 完成，21m13s；登记 §20.7.8⑯；归档 `evals/results/task_eval/ec_r3_freeze_20261016.jsonl`，sha256 `ae1eca4b1333…`）（`PYTHONPATH=src uv run python -m evaluation.task_eval run`；参照上轮 chat ≈453 次 + TEI embeddings ≈3665）
  - 通过判据：66 条归档带齐 provenance 八键 ✅（1.000，从 0.000 转正）、`code_version`/`golden_sha256` 与运行态一致（详见⑯⑥的设计特性披露与 mixed generation 自查）；§6 每行有「实测 vs 门槛」记录，不达照实写 ✅
  - 已知预期差：Generate 行需在**全量**口径下达标（锚点⑤单臂 13/15=0.867 不作数）——**全量口径主指标 N/A(mp=15)**，V0② option B 披露态维持；Grade 行按两极 gold 用 `verdict_agreement` 辅助位并披露（0.933）。

- [x] **C2 检索门禁六路由逐条 + probe 门禁**（2026-10-16 执行，登记 §20.7.8⑰①）
  - ✅ **预检通过（2026-10-15，非冻结跑次）**：权威路由 `GATE_USE_REAL_EMBEDDING=1 GATE_RERANK_MODE=on GATE_USE_REAL_RERANK=1` 只读比对已登记基线 ⇒「门禁通过：所有指标不低于基线」（真实 TEI 在线、索引 21s / 检索 98.6s、未更基线、零 API 费用）。
  - **冻结跑次（2026-10-16）**：六路由全部「门禁通过：所有指标不低于基线」——fake+off / fake+on / fake+disabled / real+off / real+disabled / real+on（权威）；无 diff ⇒ 未动任何基线文件；probe 门禁族随 `evidence_chain_gate` 81 项全绿。
  - 命令：默认 / `GATE_RERANK_MODE=on` / `GATE_RERANK_MODE=disabled` / `GATE_USE_REAL_EMBEDDING=1`（+`GATE_USE_REAL_RERANK=1` 权威路由）；CI 只覆盖默认路由，**权威路由必须本机手跑**。
  - 红线：指标若动，`--update-baseline` 后按 §20.7 登记（`scripts/ops/check_baseline_diff_registration.py` 两向核对），**禁止静默重录**；`check_baseline_sanity` 内建防故障态写基线。

- [x] **C3 RAGAS 冻结集**（2026-10-16 完成，1h54m；登记 §20.7.8⑱）
  - `evaluation.ragas.cli --dataset evals/datasets/golden/sample_408.jsonl --tag freeze20261016`（黄金集口径已校正：**全量 156 条**，code 32 / concept 60 / generate 32 / grade 32；真实 bge-m3 embedding、rerank 生效、judge=qwen3.8-flash）。
  - 结果（引用必须带分母）：faithfulness 0.8109（n=112/156）、context_precision 0.7454（n=113/156）、context_recall 0.5963（n=108/156）、answer_relevancy 0.7217（n=111/156）；`_meta.warnings` 无、`dropped_metrics` 无。
  - 与 `metrics.json` n=20 锚点（V-2026-10-02）的可比性判定：**五处口径全不同**（judge `qwen3.8-max-0902`→`qwen3.8-flash`、n=20 分层→156 全量、rerank 未生效→生效、golden `be98912a`→`783e78ff`、code `0479d6e`→`7220229`）⇒ **不可直接可比**，新旧读数只能并列披露、不得表述为改善/退化（已登记）。

- [x] **C4 Memory 三个 gate（条件式）**（2026-10-16 执行，触发条件成立；登记 §20.7.8⑰②–⑤）
  - 触发条件核验：上次 Memory gate 之后写链/评测器**确有变更**（`67a672b` 改 runner/metrics/_runner_record；5df3e47/2ae5291 改门禁区）⇒ 三 gate 全跑，非「未改不需重跑」。
  - `memory_step2_gate.py` ✅ 产品链完整；`memory_e5_probe.py --reanalyse --write` 零 LLM 重析（kp_raw/kp_normalized 未动、仅刷新时间戳）；`memory_step4fix_gate.py` 首跑 **217 项 3 失败（㉖f/g/h）** ⇒ 定位为 B2 第三路引入的真回归（`_no_reply` 空串守卫缺失）并修复，复跑 **217/217 全过**。
  - 若改过，必须本机手跑（Windows 带 `PYTHONIOENCODING=utf-8`）。

---

## D. 收尾一致性与登记

- [ ] **D1 §7.2 一致性**：`evals/reports/paper_tables.md`（现仍标 V-2026-10-02）、`docs/EXPERIMENTS.md §22`、`evals/claims/ledger.md` 三处数字与 C1/C2 新归档对齐；引用旧读数一律带脚注（如 §20.5 #38 的 verdict_agreement 新旧口径），**旧档不回写**。
- [x] **D2 工件登记**（ec_r2 代已完成；C1 后再登记最终代）：`evals/claims/artifact_status.json` 已登记 `ec_r2_final_gate_20261015.jsonl`（active）+ `ec_r1_final_gate.jsonl`（superseded，reason=`gold_blindlabel_backfill_gen_from_anchor5`）+ `ec_r2_goldinjected_20261015.jsonl`（superseded 中间件）；`phase1_gen_anchor5_20261008.jsonl` 的 `superseded_by` 由 ec_r1 **订正为 ec_r2**（原指针不承接 anchor5 的 gen 记录）。旧归档只标 superseded 不标 invalidated、数值未动；新归档按 A3 纳入版本控制，逐轮 `*.log` 仍不入库。
- [ ] **D3 局限披露核对**：B1（Generate 三判据 missing_premise 的最终态——**已裁 option B 按 limitation 披露**，披露文本见 §20.7.6④；writeup 不得把 `0.000（已测 n=1, mp=14）` 读成「0/15 通过」）、B2（Grade 两极 gold）、#35/#36（题目正文丢失 / judge 不重算算术）、§20.7 基线抖动带、**B6（gen_difficulty 适用域不含中文难度行，映射取法非唯一 0.000/0.071/0.714）**、**A1（键可靠性：降级层 12/15 carve-out 的两种口径分开记账；扩查 78 条暂定不一致为第三方页读数、待正式原卷复核，论文引用必须带「暂定」口径；exams 链全 674 题自声明 third_party）**、Verify `final_quality≥4=0/15` 诊断行（检索覆盖口径）——逐条确认论文中的表述与登记一致。

---

## E. 冻结宣布判据（全部满足才允许宣布冻结）

- [ ] sanity ERROR 0；evidence_chain_gate 全绿；`--check` 第 1、3 段 PASS（第 2 段按 B4 裁定的存量披露）。
  - 现状：sanity ERROR 0 ✅（A2 后复跑）；第 1 段 PASS ✅；第 3 段 **① PASS / ② FAIL**——② 的 generate 两判据全 missing_premise。**owner 已裁定（2026-10-15）：走 option B（limitation 披露）**——「P−1 批 2/3 产出人工可读判定」按现行契约（缺人工可判定性结论输入）清偿不了 V0②；Generate 行按 limitation 披露进 D3/论文，不得把 missing_premise 当成绩。§20.7.6④ 已登记披露文本。
- [x] **A1 处置链已裁定并执行完毕（(a)–(e) 有 owner 书面裁定 + 扩查结果登记）**
  - ✅ **裁定已落（2026-10-15，有条件采纳）**：(a) 已生效；(b) 采纳 + **carve-out**——grade 12/15 已独立核验的 gold 不受误伤（carve-out 口径：12 条 gold 值 10-14 已人工核验≠第 52 题核验的 12 条指针落层，两者在 §20.7.6⑤ 分开记账）；(c) 采纳但**成本订正 ≈4–5 人时**（原估 1.5–2 低估约 3 倍：七层各 ≈39–40 题，50% ≈140 条，扣已采 24 ⇒ **116 新增 + 相邻批次 10 = 126 条读数**）；(d) 采纳但**排在 (c) 之后**；(e) **现在与 (c) 一起预授权**。
  - ✅ **扩查执行完毕且已登记（§20.7.7）**：126 行读数入仓 + 机械复算 126/126 一致；(c) 的「错键确认」环节因读数为第三方页值（非原卷盲读）**未闭环**——78 条暂定不一致待正式原卷复核（优先队列：2011 十六条 + 78 清单；空键 13 条其中 10 条在 2009 已核实）。复核完成前 (d) 暂缓、(e) 未触发；复核仍现错键 ⇒ 按预授权即触发 exams 链暂停。
  - ✅ **正式复核完成并落地（2026-10-16，§20.7.8⑭）**：78+13+verify 2 共 93 项经 owner 组织的人工交叉复核出结论（78 改键 / 13 补键 / 2 与已登记值一致），机械核验 0 错误；按 owner「双落地」口径写入 `exam_answer_corrections.json`（4→95，评测侧覆盖、KB 不回写）+ 台账 `evals/claims/A1_KEY_CORRECTIONS_20261016.json`。证据等级披露随附（公开答案表非官方标准答案、同题性未逐字验证）。**(e) owner 2026-10-16 书面裁定暂不触发**（本条因此获得 (a)–(e) 全链 owner 书面裁定留痕；(e) 的「不触发」裁诀连同理由已登记于 §20.7.8⑭③）。
  - 通过判据：59/59 + 扩查 126 条全部有正式 verdict ✅（78/13 由 2026-10-16 复核出结论，35 一致 + 2 verify 既有登记）；处置链 (b)–(e) 全部执行留痕 ✅（(d) 91 键订正落地、(e) 有 owner 书面裁诀）；样本量/种子/分层未被改动 ✅（`p1_key_audit_sample.json` 一字节未动、扩查 JSON 未动）。
- [ ] A2/A3/A4 全部完成：gold 盲标回填、`r1b_signatures.json` 落盘且 ledger signed 列与签署范围一致、`gold_status=frozen` 经 owner 裁决。
  - 现状：A2 **部分完成**——13/15 present（gen-005 `incomplete_source` 待补选项、gen-009 `missing_key` 待重生成题干；gen-001~005 待第二标注者复核、gen-012/014 歧义待修订）。
  - A3 ✅ **已起草落盘**（2026-10-15，§20.7.6⑦）：`evals/claims/r1b_signatures.json` 11 判据签署，口径注明「**映射已审**」非「已测」；ledger signed 列已反映（3 行转真：Verify/Generate/Memory；QA/Grade 无 registry 判据照实未签）。
  - A4 ✅ **38 条审核执行并回填完毕**（§20.7.8）：32 pass → reviewed + 6 needs_fix 修复闭环（qa-011/ver-015 文本改写、gen-005/009/mem-001/004 修复+第二标注者盲态签署）⇒ **全集 reviewed 66 / draft 0**（§20.7.8⑪）。**frozen 裁决未做**——人工前置（6 条修复 + A1 正式复核）均已闭环（A1 见本条上与 §20.7.8⑭：(d) 91 键评测侧订正、(e) 裁诀暂不触发），现仅待 owner 书面裁决 `reviewed→frozen`（2026-10-06 曾裁 `reviewed`，明示「出论文数字前需最终升为 frozen」）；gold sha256 记入新归档 provenance。
  - A4 ⏳ **38 条 draft 审核已执行（32 pass / 6 needs_fix，§20.7.8），filled 工件待入仓核对**（owner 纠正：「66 条 reviewed→frozen」前提不成立，实测 **38 draft / 28 reviewed**：qa 15 + verify 15 + gen 2 + memory 6）：审核工作单 `evals/results/task_eval/GOLD_REVIEW_38DRAFT_20261015.md` 已生成（撞键 2 条已更正标注 ver-002/ver-007）；**审完 + A1 扩查落地后才可裁决 frozen**。
- [x] **B1 归档代际裁定已由 owner 复核（2026-10-15）：维持 ec_r2 混合代际**（备选「保持 ec_r1 + V0 ① 留红至 C1」未采纳；依据 §20.7.5② 实测：同 case_id 题干不同 ⇒ 直接挂 gold = 假 gold）。
- [x] **B2 ec_r1/ec_r2 `ver_fabricated` 分歧已修（owner 第三路：改 backfill 落盘口径）**：runner 统一走 registry 判据（两写入方同源同极性）+ report 凭 `item_reasons` 标记无歧义解码 + `cli._backfill` 覆盖已存值显式记账；ec_r2 边车重生 `ver_fabrication` 1.000→**0.000**（归档 jsonl 一字节未动，ledger 该行实时重算本就 0 假红仅边车）；`tests/test_verify_fabrication_polarity.py` 7 项回归。实测佐证「选项①修不了」：重 backfill 出的 ec_r1 v2 仍带 verdict 极性 True ⇒ 同病的是**极性**不是字段新鲜度。
- [ ] §6 门槛行在全量口径下有读数；每一行要么达线，要么已按 limitation 披露——**不允许「已测量未证明」被当作成绩引用**（V0 ② 的红就是这个意思）。
- [ ] provenance_match 与当前 `code_version`/`golden_sha256` 一致（C1 的直接目的）。
- [ ] D1/D2/D3 收口；全部工件已提交，`git status` 干净（✅ 2026-10-16 `67a672b` 已提交 45 个变更、工作树清零）；论文引用的每个数字可经 ledger「复现」列当场重算。

## F. 冻结后纪律（禁止事项）

- 基线（`phase0_baseline_final.*` / `evals/baselines/*`）只读；后续实验新建版本，命名带阶段前缀；`--update-baseline` 必须同日登记 §20.7。
- 不回写任何旧归档数值；新读数优先走「重算 + 新文件 + 登记」，引用带脚注。
- `evals/results/task_eval/` 的 `*.log` 不入库；`GOLD_REVIEW`/`GRADE_KEY_VERIFY` 式工作单结论必须人工签，**脚本不得代签**。
- 若冻结后仍需改检索链/批改链/Memory 链：按 EFFECT_PLAN §6 走「新版本 + 全量重跑 + 重录门禁 + 换论文数」，并重新过本清单 C/D 段。

## 附：本清单不覆盖的事（防止范围蔓延）

调检索阈值/参数（三次负收益先例）、换 LLM/embedding、重开 `merged_qa_meta` 路由、铺广度、恢复完整测试套件（原归档目录本机已不存在）——均在 RETRIEVAL_ROADMAP「不做清单」/CLAUDE.md 工作区边界内，冻结不收它们。

