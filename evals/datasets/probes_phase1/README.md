# probes_phase1/ —— Phase 1 回归集（现行权威）

| 文件 | 条数 | 说明 |
|---|---|---|
| `verify_cases.jsonl` | 10 | 真题核查回归探针。与 `probes/verify_cases.jsonl` **逐字节相同**（Phase 1 建集时复制，`probes/` 为考古层） |
| `generate_cases.jsonl` | 4 | 出题回归探针（与 `demo/generate_cases.jsonl` 的 15 条**零重叠**，是独立抽样） |

引用方：`evals/results/task_eval/PHASE1_VERIFY.md`（4/4 仍出新题）、`task_eval/README.md`
（"Phase 1 探针集（10 verify + 4 generate 回归）"）。

引用时写全路径 `evals/datasets/probes_phase1/<文件名>`。
