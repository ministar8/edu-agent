# docs/ 索引

**先读哪个**：动知识库 → `KB_MASTER_DESIGN.md`（总册）。动检索路由/策略 → `RETRIEVAL_LAYER_DESIGN.md` + `RETRIEVAL_POLICY.md`。改检索相关代码前 → `RETRIEVAL_PLAN.md` + `RETRIEVAL_ROADMAP.md`（**「不做清单」在这里，改动前必看**）。**写论文 / 快速定位代码 → `ARCHITECTURE_RETRIEVAL.md` + `EXPERIMENTS.md`。** 补效果 / 定论文效果指标 → **`EFFECT_PLAN.md`**。跑任务级评测、出效果章数字 → **`src/evaluation/task_eval`**（入口见 `CLAUDE.md`「常用命令」；三个 Memory Gate 在 `scripts/`）。核对「论文声称 ↔ 证据」的对应关系 → 方案 **`EVIDENCE_CHAIN.md`** + 执行计划 **`EVIDENCE_CHAIN_PLAN.md`** + 生成物 **`../evals/claims/ledger.md`**（★ 状态词由代码算出，本文不抄它的内容；每行自带「复现：」命令）。★ **数字的版本归属看锚点，不看记忆**：检索 = `EXPERIMENTS.md` **§18** · 效果 = **§20**；★ **有哪些锚点、各自落在哪个提交一律现查**（本行此前写死「`V-2026-10-07`，标签待打」—— 那正是会漂的声称，已作废）：复现：`git tag -l` 逐个列出，落点由 `git rev-parse` 现算。

## 现行文档

| 文件 | 作用 | 何时读 |
|---|---|---|
| **`KB_MASTER_DESIGN.md`** | **知识库总册**（L1/KP/L2/L3 + 边 + gap + ID + 现状） | **动知识库/入库前** |
| **`RETRIEVAL_LAYER_DESIGN.md`** | **检索层设计（定稿）**（task_mode / eligibility / ranking / release） | **动检索路由前** |
| **`RETRIEVAL_POLICY.md`** | **策略契约**（retrieval_policy 字段、默认表、LangGraph 落点） | 实现 Classifier/Policy 前 |
| `BASIC_DESIGN.md` | L1 细节 | 写/改 Basic |
| `ADVANCED_DESIGN.md` | L2 细节 | 写/改 Advanced |
| `EXAMS_DESIGN.md` | L3 细节（D0–D6 决策） | 写/改 Exams |
| `ARCHITECTURE.md` | 分层与调用链（L0~L3 分层、检索/生成/护栏） | 理解系统结构 |
| **`ARCHITECTURE_RETRIEVAL.md`** | **检索架构总览（as-built）+ 术语表 + 模块索引 + 已知局限** | **写论文第 3 章 / 定位代码** |
| **`RETRIEVAL_PLAN.md`** | **当前执行方案**（Step 1~6 + 实测数据 + 已否决项） | **动手改检索前** |
| `RETRIEVAL_ROADMAP.md` | 效果路线图；**含「不做清单」（同类改动有负收益先例）** | **动手改检索前** |
| **`EFFECT_PLAN.md`** | **效果完整度提升方案**（Phase 0 体检 → 任务级评测 → 闸门 → 验收；四张任务表 + rubric + 退出条件） | **补效果 / 写论文效果章前**。★ **定稿 v1.0 = 冻结件**：口径若与代码不一致，只登记偏离（见 `EXPERIMENTS.md` §20.5），**不改写本文件** |
| **`EVIDENCE_CHAIN.md`** | **证据链重建方案（主张 ↔ 证据对齐）**：R1–R5 规则、三态推导、`5.A/5.B` 业务链二分、反向取证矩阵、V0–V6 退出准则 | **引用任何「已被证明」的措辞前** —— 它定义什么算证据；★ §1.1 状态表的判据自 checkpoint 10 起与 `claims.derive_status` 对齐（口径差的收口与残留代价写在该节，不在本文复述） |
| **`EVIDENCE_CHAIN_PLAN.md`** | 上方案的**执行计划**（Task 1–10 + 逐 Task 判据编号） | 追某条判据（`5a`/`8i`/`9h`…）是哪一步、为什么存在时 |
| **`EXPERIMENTS.md`** | **实验总册 + 版本锚点**：§1–§17 检索实验 · **§18 检索锚点** · §19 最终系统决策表 · **§20 效果锚点**（§20.4 结果归属矩阵 / §20.5 已知偏离账本 / §20.7.1 Task 9 六条路由重录 / **§20.7.2 Task 10 偏离合并登记：已裁定设计选择 / 已知局限 / 尚待验证归因 三类**） | **引用任何论文数字前** —— 先查它属于哪个锚点、是否落在「已知偏离」里 |
| `L1L2L3_RETRIEVAL_REVIEW.md` | L1/L2/L3 分级设计评审（问题清单 + 五维度优劣） | 改分级/路由/阈值前 |
| `RERANK_SWITCH_ANALYSIS.md` | `RERANK_ENABLED` 三态与 `use_rerank` 双职责分析 | 改重排开关相关代码前 |
| `DOCKER.md` | 部署、健康检查、**TEI 端点契约** | 起容器 / 探活 TEI 前 |

## 门禁

### 检索门禁（改了检索链就跑）

| 命令 | 粒度 | 说明 |
|---|---|---|
| `python -m evaluation.retrieval_gate` | 章级 `kp_*` + 学科级，156 条黄金集 | 改动检索链后**必须**跑；任一指标跌破基线即失败。★ 按 `(embedding, rerank)` 组合登记 **6 份基线**，未登记组合直接退出码 2 |
| `python -m evaluation.probe_gate` | **小节级**：目标 chunk 在**哪一层**丢失，5 条探针 | 补上 `retrieval_gate` 的盲区（`kp_*` 只看文件名）。**拦「后退」、放行「前进」** |
| `python -m evaluation.candidate_trace` | 逐层快照（诊断） | **不是门禁** —— 跑生产索引、无就绪屏障、无退出码 |

### 效果门禁（`task_eval` · 改了批改链 / Memory 写链 / 评测器就跑）

| 命令 | 成本 | 说明 |
|---|---|---|
| `PYTHONPATH=src uv run python -m evaluation.task_eval sanity` | 零 LLM | Gold 体检（canonical / 可机械判定 / gold 泄漏 / 任务专有）。**进 0B 前必跑，有 ERROR 不得跑** |
| `PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/memory_step4fix_gate.py` | 零 LLM | **项数与红绿灯只由脚本自己报，文档不抄生成值**（本行此前写死「现 129 项」，而代码声明值已两度上移 ⇒ 属 `EVIDENCE_CHAIN.md` §7 登记的活文档勘误）：声明值现查 `grep -n "^_EXPECTED_ITEMS" scripts/memory_step4fix_gate.py`（含反向自查：脚本收尾比对「判定项数 = 声明值」且跳过数为 0，少跑即 exit 1，见 `EXPERIMENTS.md` §20.5 #30）；实跑命令 = 本行左列。覆盖：⑭ Generate 主指标改逐题「适用项全过」（含「两口径必须分叉且池化偏高」的方向性判据）/ ⑮ 死代码删净（AST 级）+ record 落 `prompt_set_version`（反向验证值必须是活的）/ ⑦ paired control 接口 / ⑧ 示例名 canonical / ⑨ 抗格式飘移 / ⑩ context-fallback（含 ⑩e 并发隔离、⑩f 显式 config 契约）/ ⑪ topic 归一 / ⑫ 词表同源（含 ⑫i 双读、⑫k 根节点双向）/ ⑬ 重判归因保全 + jsonl 尾换行 + 负样本前置条件 / ③a~③u 评测器口径（含 ③j+ 学科码全体扫描、两极 gold 不可判 + `verdict_agreement` + 分数解析遮蔽「满分」） |
| `PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/evidence_chain_gate.py` | 零 LLM | **证据链门禁**（判据四态与 R5 复合 / mutation 反向取证 / 三态推导与 ledger 一致性 / V0 拦截 / B1·B2·B7 结构与行为锁）：项数同样只看脚本自己打印的那行「全绿（N 项）」，本文不写 N。★ **它全绿只证明「当前这些检查项通过」** —— 不证明历史实验逐位复现、也不证明各层级语义债已清零（边界声明见下面「收尾陈述的边界」与 `EXPERIMENTS.md` §20.7.2）。复现：本行左列 |
| 同上 `scripts/memory_step4_gate.py` | 零 LLM | 14 项：每 case 独立 `user_id` + 跑前清理 Store（含反向验证） |
| 同上 `scripts/memory_step2_gate.py` | 2 次批改 LLM | 11 项：批改 → KP → episode → `weak_topics` → 记忆卡 全链路 |
| 同上 `scripts/memory_e5_probe.py` | 12 次批改 LLM | ★ **测量，不是门禁**（退出码恒 0）：配对对照「词表版 vs 8 示例版」的跟随率。`--reanalyse --write` 可**零成本**用新 gold 原地重析 |
| `… task_eval run --no-agent` / `reprobe` / `backfill` | 零 LLM | 只跑检索探针 / 只重算检索侧指标 / 回填机械可算字段 —— 改判据后**先走这三条**，别急着重跑 agent |

> ★ **CI 只覆盖检索门禁的默认路由**（假 embedding，比 1 份基线）。
> `task_eval` 与三个 Memory Gate **刻意不进 CI**（要真密钥、按 token 计费、模型输出有随机性）
> ⇒ **效果章的数字没有任何自动兜底**，全靠本机手动重跑；Windows 上还须带 `PYTHONIOENCODING=utf-8`
> （否则打印 ✅ 时 GBK 抛 `UnicodeEncodeError`，崩在 `print` 而退出码同为 1，会被误读成红灯）。

## 收尾陈述的边界（引用「门禁绿灯」「零 token」这两句时必须一起引）

① **门禁全绿只证明「当前这些检查项通过」** —— 它**不**证明所有历史实验都能复现（本轮重录后六条检索基线 diff 全非零、逐条登记与归因边界见 `EXPERIMENTS.md` **§20.7.1**），也**不**证明各层级的语义债已清零（`TIER-DEBT-task3`、`9i` 这类已登记项在当前态下照绿 ⇒ 护栏通过的语义是「债名单与登记一致」，不是「债已清偿」；待处理清单见 **§20.7.2**）。复现：`PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/evidence_chain_gate.py`（项数只看它自己打印的那行）与 `PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/build_claim_ledger.py --check` 的**第 3 段**（V0 未清偿 ⇒ 那一段本来就该红）。

② **「零 LLM token」限定在那六次路由重录**，不外推到整个项目生命周期。证据：每份新基线自带的 `provenance.model_refs.agent`（假模型哨兵值 ⇒ 那六跑没打模型；TEI 是真实服务，属**非 LLM** 调用），逐份登记见 `EXPERIMENTS.md` §20.7.1；复现：`git ls-files evals/baselines` 列出现役基线后逐个读它的 `_meta` / `provenance` 键。★ 项目其余环节照常烧 token —— Step 9 真跑、step2 复跑、§6 整轮都在 `EXPERIMENTS.md` §20.8 / §22 里逐份记着调用次数，引用「零 token」时不要把它们一起抹掉。

## 遥测报表（不是门禁）

| 命令 | 说明 |
|---|---|
| `python -m evaluation.telemetry_report` | 把 `data/metrics/rag_metrics.jsonl` 聚合成人可读报表：流量构成、逐阶段漏斗（按 `query_type`）、有效阈值分布、分层/路由分布、入库交叉校验。**只读、无基线、无判定** —— 退出码只用于「读不到日志」。★ 两条使用纪律：① 用 `query_preview ∩ 黄金集` 判定流量来源，实测 **99.4% 是评测流量** ⇒ 它回答的是「管线各层在黄金集上的行为分布」，**不是**线上统计；② 日志**混了多个代码版本**，必须用 `--since` / `--until` 把窗口钉到单一版本（实测 `generate` 过阈率在 09-27 15:00 前后 0.075 → 0.187），否则读到的是**混合口径**。`--output <path>` 可把 JSON 落盘归档（建议 `evals/results/`） |

## 评测产物（`evals/results/`）

都是**证据**，不要随意清理。★ provenance 的覆盖面**分两类，不要当成统一承诺**：

| 归档类别 | 自带的追溯字段 | 反查能力 |
|---|---|---|
| 检索 / RAGAS 类 | `code_version` / `golden_sha256` / **`script`** / **`argv`** | 可从论文数字反查到脚本与命令行 |
| **`task_eval/`（效果章）** | 逐条 record 带 `code_version` / `golden_sha256` / `date` / `prompt_set_version`（`runner.py:726-736`）。★ **更正（Task 2）**：`script` / `argv` **从来就不是「没产出」** —— `build_provenance()` 一直输出这两个字段（`src/evaluation/provenance.py:141-157`），是此前的调用方只挑 `code_version` / `golden_sha256` 两个标量、把其余丢弃（原 `runner.py:725-727`）；**Task 2 起整包落进 `record.provenance`**（同一次调用的同一个 `_inner`，含 `script` / `argv` / `model_refs` / `sampling` / `experiment_config_hash` / `dependency_lock_hash`，见 `runner.py:725-730`） | ⇒ **Task 2 之前**产出的归档（含 `phase0/phase1` 冻结集）里没有 `provenance` 整包，效果数字的版本归属仍**靠 `EXPERIMENTS.md` §20.4 的归属矩阵人工对账**；且 `code_version` 在工作区未提交时恒为 `<sha>-dirty`，区分不出先后 |

| 路径 | 内容 |
|---|---|
| `retrieval/ablation/` | 组件消融 · 重排对照 · Task-aware · 基础 RAG · 方差 · 阈值敏感度 · L2 归因 |
| `retrieval/layer_policy/` | L1/L2/L3 分层消融 · Task × Layer 交互矩阵 |
| `retrieval/legacy_runtime/` | legacy 三策略 |
| `generation/ragas/` | `raw.jsonl` 逐样本 · `metrics.json` 汇总 · `summary.md` 结论 |
| `system_validation/` | Agent 行为 · LangGraph State 闭环 |
| **`task_eval/`** | **效果章全部证据**：`phase0_baseline_final.jsonl`（66 条**冻结、只读**）· `PHASE0_FREEZE.md` · `phase1_baseline_v2.jsonl` · `PHASE1_VERIFY.md` · Step 5 配对 `phase1_memory_step5_store_{on,off}.jsonl` + `PHASE1_MEMORY_STEP5_FINDINGS.md` · `phase1_e5_prompt_following.jsonl` · **`HANDOVER.md`（交接活文档）** · 本轮重录 `ec_r1_final_gate.jsonl` / `.report.json`。★ 该目录的**跟踪状态看命令、不看本文**（此前写死的「`git ls-files` = 0」作废：数字会漂、命令不会）——已跟踪 = `git ls-files evals/results/task_eval \| wc -l`，未跟踪 = `git status --short -- evals/results/task_eval \| grep -c "\^??"` 的行数 ⇒ Task 10 起数值工件（`*.jsonl` / `*.report.json`）已入库，★ **逐轮 `*.log` 仍不入库**（单份可达 MB 级 ⇒ 沿用 D11 的取舍，剩余未跟踪名单现查 `git status --short -- evals/results/task_eval`），「冻结、只读」现在有版本控制兜着；旧读数与新一代的替代关系记在 `evals/claims/artifact_status.json`（标 `superseded`，**不删原文件、不改数值**） |
| **`../evals/claims/`** | **主张 ledger 与工件状态**：`ledger.md`（生成物，勿手改）· `ledger_draft.md`（Task 6/7 期间的草稿，留档）· `falsify_latest.json`（mutation 取证件）· `artifact_status.json`（旧工件的 `superseded` 标注 + `superseded_by` 指向）。★ **`ledger.md` 由脚本重算产出，本文只给索引**：生成 = `uv run python scripts/build_claim_ledger.py --records` 加归档路径、`--check` 校验「文档 == 重算」；本目录**不含手写百分数** |
| `../baselines/` | 门禁基线（`retrieval_baseline.json` 等 6 份 + `probe_baseline.json` 等），门禁运行时即时比对。★ Task 9 重录过一轮 ⇒ **两代并存**：旧一代整份留在 `evals/baselines/pre_task9_20261009/`，替代关系标在 `evals/claims/artifact_status.json`（`superseded`，原文件不删）；名单与份数现查 `git ls-files evals/baselines`，六条 diff 与归因见 `EXPERIMENTS.md` §20.7.1 |

> 目录清单与命名约定的说明见 `evals/results/README.md`；实验数字与解读见 `docs/EXPERIMENTS.md`。
> 归档脚本落在 `scripts/`，由 pre-commit 的 ruff 钩子正常检查。
> （`.pre-commit-config.yaml` 的 `exclude: ^evals/` 仍保留，服务 `baselines/` 与 `datasets/`
> 这类**输入**；`.gitignore` 的 `!evals/results/**/*.log` 例外**现在有匹配文件**（磁盘上已有逐轮
> `*.log`）⇒ 此前那句「已无匹配文件」作废，但★ 本轮按 Task 10 的清单只把 `*.jsonl` / `*.report.json` 入库、
> `*.log` 仍留不入库（沿用 D11 的体积取舍）；现查：`git status --short -- evals/results/task_eval`）
