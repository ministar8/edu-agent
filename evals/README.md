# Evaluation Workspace

该目录保存 EDU-Agent 的实验数据、实验配置、运行结果和验证产物。

## Directory

### datasets

实验输入数据。

- `golden/` — 检索黄金集、探针 queries（156 条黄金 query + 5 条探针，见 `evals/datasets/golden/README.md`）
- `corrections/` — 真题答案键人工修正表 `exam_answer_corrections.json`（被 `evaluation.task_eval.assets.load_answer_corrections()` 只读消费）

以下目录在 README 早期版本中有承诺，但对应数据/产物尚未补全，**不在本仓当前版本中存在**，不在此列：

- `ragas/`、`analysis/`（`datasets/` 下，缺 RAGAS 配对样本与语料覆盖对照）
- `demo/`、`probes/`、`probes_phase1/`（引用纪律里提及的跨目录同名文件，实际目录不存在）

### baselines

固定回归基线。

存在：

- `probe_baseline.json` — `probe_gate` 小节级探针基线
- `retrieval_baseline.json` — `retrieval_gate` 默认路由基线

下列 5 条组合基线已补全（`_constants.py` 中对应路径均有文件）：

- `retrieval_baseline_rerank.json` — fake embedding + rerank on
- `retrieval_baseline_real_embed.json` — real embedding + rerank off
- `retrieval_baseline_fake_disabled.json` — fake embedding + rerank disabled
- `retrieval_baseline_real_disabled.json` — real embedding + rerank disabled
- `retrieval_baseline_real_rerank.json` — real embedding + rerank on

缺失时门禁不会崩溃：`load_baseline` 返回 `None`，运行结束打印提示、**跳过退化比对并返回退出码 0** —— 该组合此刻等于未受回归保护，需要时用 `--update-baseline` 重录。

### experiments / configs / results / reports

实验配置与运行产物目录（`configs/`、`results/`、`reports/`）：

- `experiments/configs/` — 实验开关 yaml（full / vector_only / no_bm25 / no_metadata / ragas），文件由实验补全批次填入
- `results/retrieval/{ablation,layer_policy,legacy_runtime}` — 检索相关实验产物
- `results/generation/ragas/` — 生成质量实验产物（RAGAS 读数与样本）
- `results/system_validation/` — 系统正确性验证产物（LangGraph state / agent behavior / leakage）
- `results/archive/` — 开发期调参历史归档
- `reports/` — 整理后的实验报告（`paper_tables.md`、`figures/`）

以上目录均为**运行时产出目录**：首次运行相应实验/门禁脚本时由脚本自动 `mkdir -p` 创建，**不入 git，不随仓库克隆预置**。克隆后首次跑门禁或实验前，如代码未自建目录，请先按需 `mkdir -p` 对应子目录。
