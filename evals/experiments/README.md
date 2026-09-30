# experiments — 实验配置

```
evals/
├── datasets/            实验输入
├── baselines/           固定回归基线（不动）
├── experiments/configs/ 消融开关配置
├── results/             实验结果 / 系统验证
└── reports/             论文表格/图片
```

`configs/` 是**实验快照**（可读的实验设计记录）。

> ★ **执行以脚本 `CONFIGS` 为准**（`scripts/ablation_retrieval.py` 等）。
> YAML 不驱动运行，只用于：论文附录、答辩讲解、事后追溯「这次改了什么」。
> 若两者不一致，**以脚本为准**并回来同步 YAML。
> 每次运行会把当次生效配置写进 `results/` 的归档 json。

## 配置字段约定（所有 yaml 保持同一字段）

| 字段 | 含义 | 例 |
|---|---|---|
| `name` | 配置名（与脚本 `--configs` 一致） | `no_bm25` |
| `description` | 一句话说明 | |
| `inherits` | 继承自哪个配置（缺省 `full`） | `full` |
| `components` | 组件开关（只写与 full 不同的） | `{bm25: false}` |
| `legacy_policy` | 资产池策略 | `per_mode` / `include` |
| `rerank` | 重排开关 | `false` |
| `note` | 消融结论备注 | `kp_mrr −0.088` |

## 清单

| 配置 | 含义 |
|---|---|
| `full.yaml` | 完整系统（对照基线） |
| `no_bm25.yaml` | 去 BM25 |
| `no_metadata.yaml` | 去元数据路由 |
| `vector_only.yaml` | 仅语义向量（≈ 朴素 RAG） |
| `ragas.yaml` | 生成质量（PENDING） |

```bash
uv run python scripts/ablation_retrieval.py --limit 60 --configs full,no_bm25,no_metadata,vector_only
uv run python scripts/basic_rag_ablation.py --limit 60   # full vs vector_only
```
