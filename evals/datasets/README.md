# evals/datasets/ —— 评测数据集总索引

本目录存放**全部评测输入数据**（尺子的"题"与"基准"）。所有文件均已入 git。

## 目录地图

| 目录 | 内容 | 生成方式 | 消费方 |
|---|---|---|---|
| `golden/` | 黄金集 156 条 + 检索探针 5 条 | 人工构建（KP 标注半自动） | `evaluation.gates.retrieval_gate` / `probe_gate` |
| `demo/` | Phase 0 效果测量 66 case（五任务） | `scripts/datasets/build_demo_cases.py` 确定性生成 | `evaluation.task_eval` |
| `probes/` | Phase 0 探针 10 条 | 人工构建 | Phase 0 findings（历史考古） |
| `probes_phase1/` | Phase 1 回归集（verify 10 + generate 4） | 人工构建 | `PHASE1_VERIFY.md` / task_eval |
| `ragas/` | RAGAS 配对样本 20 条 | 人工构建（与黄金集同源） | `evaluation.ragas.cli` |
| `analysis/` | 语料换代覆盖对照 1 份 | 已删脚本生成（见该目录 README） | 无（证据工件） |
| `exam_answer_corrections.json` | 真题答案键人工修正表 | 人工核验（2026-10-06） | `evaluation.task_eval.assets`（只读） |

## ★ 引用纪律：必须带全路径

本目录存在**跨目录同名文件**，且内容不同——按裸文件名引用必定指错：

| 文件名 | 出现位置 | 区别 |
|---|---|---|
| `verify_cases.jsonl` | `demo/`（15 条）/ `probes/`（10 条）/ `probes_phase1/`（10 条） | 三份互不相同（后两份逐字节相同） |
| `generate_cases.jsonl` | `demo/`（15 条）/ `probes_phase1/`（4 条） | 两份零重叠 |

代码、文档、实验登记里引用数据集时**一律写 `evals/datasets/<目录>/<文件名>`**。

## 通用约定

- JSONL 一行一条，文件首部允许 `#` 注释行（读取方统一跳过）；
- demo case 的 `gold_status` 三态：`draft` → `reviewed` → `frozen`（口径见 `demo/README.md`）；
- **跨目录同名不同义是已知状态而非事故**：出于"探针不动主集"的隔离考虑保留至今；清理方案（合并或改名）需连带改引用方，未动前以本表为准。
