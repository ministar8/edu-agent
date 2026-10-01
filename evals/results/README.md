# results — 实验结果 vs 系统验证

**论文里两回事，不要混：**

| 目录 | 回答的问题 | 答辩场景 |
|---|---|---|
| `retrieval/` | 检索性能提升 | 「你的实验结果是什么？」 |
| `generation/` | 生成质量 | 「生成可靠吗？」 |
| `system_validation/` | 系统可靠性保证 | 「系统可靠吗？」 |

> 2026-09-30 起结果只保留**规范文件名**（无时间戳、无 `archive/`）。

## retrieval/ 检索实验

| 文件 | 内容 |
|---|---|
| `ablation/component_ablation.json` | 组件消融 |
| `ablation/rerank_compare.json` | 重排对照 |
| `ablation/task_layer_ablation.json` | Task-aware |
| `ablation/basic_rag_compare.json` | 基础 RAG |
| `layer_policy/layer_ablation.json` | L1/L2/L3 |
| `layer_policy/task_mode_x_layer_policy.json` | Task × Layer 交互 |
| `legacy_runtime/legacy_runtime.json` | legacy 三策略 |

## generation/ 生成质量

| 子目录 | 内容 |
|---|---|
| `ragas/` | `raw.jsonl` 逐样本 · `metrics.json` 汇总 · `summary.md` 结论（**已完成 2026-10-01，n=20**） |

## system_validation/ 系统验证

| 子目录 | 内容 |
|---|---|
| `langgraph_state/` | State 闭环（重启/trim/中断/Store） |
| `agent_behavior/` | Agent 输出行为质量 |
| `leakage/` | 答案泄漏门禁（结果即时输出，基线在 `../baselines/`） |

> 门禁类（retrieval_gate / leakage_gate）的基线在 `evals/baselines/`，
> 运行时即时判定，不另存结果文件。
