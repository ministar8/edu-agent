# docs/ 索引

**先读哪个**：动知识库 → `KB_MASTER_DESIGN.md`（总册）。动检索路由/策略 → `RETRIEVAL_LAYER_DESIGN.md` + `RETRIEVAL_POLICY.md`。改检索相关代码前 → `RETRIEVAL_PLAN.md` + `RETRIEVAL_ROADMAP.md`（**「不做清单」在这里，改动前必看**）。**写论文 / 快速定位代码 → `ARCHITECTURE_RETRIEVAL.md` + `EXPERIMENTS.md`。** 补效果 / 定论文效果指标 → **`EFFECT_PLAN.md`**。跑任务级评测、出效果章数字 → **`src/evaluation/task_eval`**（入口见 `CLAUDE.md`「常用命令」；三个 Memory Gate 在 `scripts/`）。★ **数字的版本归属看锚点，不看记忆**：检索 = `EXPERIMENTS.md` **§18**（`V-2026-10-02`）· 效果 = **§20**（`V-2026-10-07`，标签待打）。

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
| **`EXPERIMENTS.md`** | **实验总册 + 版本锚点**：§1–§17 检索实验 · **§18 检索锚点 `V-2026-10-02`** · §19 最终系统决策表 · **§20 效果锚点 `V-2026-10-07`**（§20.4 结果归属矩阵 / §20.5 已知偏离账本） | **引用任何论文数字前** —— 先查它属于哪个锚点、是否落在「已知偏离」里 |
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
| `PYTHONIOENCODING=utf-8 PYTHONPATH=src uv run python scripts/memory_step4fix_gate.py` | 零 LLM | **现 129 项**全绿（含 ③j+ 学科码全体扫描）：⑭ Generate 主指标改逐题「适用项全过」（含「两口径必须分叉且池化偏高」的方向性判据）/ ⑮ 死代码删净（AST 级）+ record 落 `prompt_set_version`（反向验证值必须是活的）/ ⑦ paired control 接口 / ⑧ 示例名 canonical / ⑨ 抗格式飘移 / ⑩ context-fallback（含 ⑩e 并发隔离、⑩f 显式 config 契约）/ ⑪ topic 归一 / ⑫ 词表同源（含 ⑫i 双读、⑫k 根节点双向）/ ⑬ 重判归因保全 + jsonl 尾换行 + 负样本前置条件 / ③a~③u 评测器口径（含两极 gold 不可判 + `verdict_agreement` + 分数解析遮蔽「满分」） |
| 同上 `scripts/memory_step4_gate.py` | 零 LLM | 14 项：每 case 独立 `user_id` + 跑前清理 Store（含反向验证） |
| 同上 `scripts/memory_step2_gate.py` | 2 次批改 LLM | 11 项：批改 → KP → episode → `weak_topics` → 记忆卡 全链路 |
| 同上 `scripts/memory_e5_probe.py` | 12 次批改 LLM | ★ **测量，不是门禁**（退出码恒 0）：配对对照「词表版 vs 8 示例版」的跟随率。`--reanalyse --write` 可**零成本**用新 gold 原地重析 |
| `… task_eval run --no-agent` / `reprobe` / `backfill` | 零 LLM | 只跑检索探针 / 只重算检索侧指标 / 回填机械可算字段 —— 改判据后**先走这三条**，别急着重跑 agent |

> ★ **CI 只覆盖检索门禁的默认路由**（假 embedding，比 1 份基线）。
> `task_eval` 与三个 Memory Gate **刻意不进 CI**（要真密钥、按 token 计费、模型输出有随机性）
> ⇒ **效果章的数字没有任何自动兜底**，全靠本机手动重跑；Windows 上还须带 `PYTHONIOENCODING=utf-8`
> （否则打印 ✅ 时 GBK 抛 `UnicodeEncodeError`，崩在 `print` 而退出码同为 1，会被误读成红灯）。

## 遥测报表（不是门禁）

| 命令 | 说明 |
|---|---|
| `python -m evaluation.telemetry_report` | 把 `data/metrics/rag_metrics.jsonl` 聚合成人可读报表：流量构成、逐阶段漏斗（按 `query_type`）、有效阈值分布、分层/路由分布、入库交叉校验。**只读、无基线、无判定** —— 退出码只用于「读不到日志」。★ 两条使用纪律：① 用 `query_preview ∩ 黄金集` 判定流量来源，实测 **99.4% 是评测流量** ⇒ 它回答的是「管线各层在黄金集上的行为分布」，**不是**线上统计；② 日志**混了多个代码版本**，必须用 `--since` / `--until` 把窗口钉到单一版本（实测 `generate` 过阈率在 09-27 15:00 前后 0.075 → 0.187），否则读到的是**混合口径**。`--output <path>` 可把 JSON 落盘归档（建议 `evals/results/`） |

## 评测产物（`evals/results/`）

都是**证据**，不要随意清理。★ provenance 的覆盖面**分两类，不要当成统一承诺**：

| 归档类别 | 自带的追溯字段 | 反查能力 |
|---|---|---|
| 检索 / RAGAS 类 | `code_version` / `golden_sha256` / **`script`** / **`argv`** | 可从论文数字反查到脚本与命令行 |
| **`task_eval/`（效果章）** | 只有 `code_version` / `golden_sha256` / `date` —— **无 `script` / `argv`，也无 `prompt_set_version`** | ⇒ 效果数字的版本归属**靠 `EXPERIMENTS.md` §20.4 的归属矩阵人工对账**；且 `code_version` 在工作区未提交时恒为 `<sha>-dirty`，区分不出先后 |

| 路径 | 内容 |
|---|---|
| `retrieval/ablation/` | 组件消融 · 重排对照 · Task-aware · 基础 RAG · 方差 · 阈值敏感度 · L2 归因 |
| `retrieval/layer_policy/` | L1/L2/L3 分层消融 · Task × Layer 交互矩阵 |
| `retrieval/legacy_runtime/` | legacy 三策略 |
| `generation/ragas/` | `raw.jsonl` 逐样本 · `metrics.json` 汇总 · `summary.md` 结论 |
| `system_validation/` | Agent 行为 · LangGraph State 闭环 |
| **`task_eval/`** | **效果章全部证据**：`phase0_baseline_final.jsonl`（66 条**冻结、只读**）· `PHASE0_FREEZE.md` · `phase1_baseline_v2.jsonl` · `PHASE1_VERIFY.md` · Step 5 配对 `phase1_memory_step5_store_{on,off}.jsonl` + `PHASE1_MEMORY_STEP5_FINDINGS.md` · `phase1_e5_prompt_following.jsonl` · **`HANDOVER.md`（交接活文档）**。★ 该目录**目前尚未被 git 跟踪**（`git ls-files` = 0）⇒ 「冻结」现在只是措辞，纳入版本控制前请先备份 |
| `../baselines/` | 门禁基线（`retrieval_baseline.json` 等 6 份 + `probe_baseline.json` 等），门禁运行时即时比对 |

> 目录清单与命名约定的说明见 `evals/results/README.md`；实验数字与解读见 `docs/EXPERIMENTS.md`。
> 归档脚本落在 `scripts/`，由 pre-commit 的 ruff 钩子正常检查。
> （`.pre-commit-config.yaml` 的 `exclude: ^evals/` 仍保留，服务 `baselines/` 与 `datasets/`
> 这类**输入**；`.gitignore` 的 `!evals/results/**/*.log` 例外当前已无匹配文件。）
