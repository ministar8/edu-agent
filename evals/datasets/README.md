# evals/datasets/ —— 评测数据集总索引

本目录存放**全部评测输入数据**（尺子的"题"与"基准"）。所有文件均已入 git。

## 目录地图

| 目录 | 内容 | 生成方式 | 消费方 |
|---|---|---|---|
| `golden/` | 黄金集 156 条 + 检索探针 5 条 | 人工构建（KP 标注半自动） | `evaluation.gates.retrieval_gate` / `probe_gate` |
| `corrections/` | 真题答案键人工修正表 `exam_answer_corrections.json` | 人工核验（2026-10-06） | `evaluation.task_eval.assets`（只读） |

以下目录在 `datasets/README.md` 早期版本中有承诺，但对应目录/文件**不在本仓当前版本中存在**，不在此列：

- `demo/`、`probes/`、`probes_phase1/`、`ragas/`、`analysis/`

跨目录同名文件引用纪律（依赖上述不存在目录）已随之删除，如需恢复请先补全对应目录。
