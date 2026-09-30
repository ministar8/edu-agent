# Evaluation Workspace

该目录保存 EDU-Agent 的实验数据、实验配置、运行结果和验证产物。

## Directory

### datasets

实验输入数据。

- `golden/` — 检索黄金集、probe queries
- `ragas/` — 生成质量评估样本
- `analysis/` — 知识库统计分析

### baselines

固定回归基线。

用于验证：

- 检索策略变化
- policy 修改
- evidence 行为

### experiments

实验配置。

`configs/` 保存实验开关：

- `full.yaml`
- `vector_only.yaml`
- `no_bm25.yaml`
- `no_metadata.yaml`
- `ragas.yaml`

### results

实验运行产物。

#### retrieval

检索相关实验：

- `ablation/`
- `layer_policy/`
- `legacy_runtime/`

#### generation

生成质量实验：

- `ragas/`
  - `raw.jsonl` — 逐样本问答与得分
  - `metrics.json` — 汇总指标
  - `summary.md` — 实验结论

#### system_validation

系统正确性验证：

- LangGraph state
- agent behavior
- leakage

#### archive

开发期调参历史归档。

### reports

整理后的实验报告：

- `paper_tables.md`
- `figures/`
