# RAGAS 生成质量评估

**状态**：PENDING — 待统一重跑（旧数据口径有问题，已删）

## 输出约定

| 文件 | 内容 |
|---|---|
| `raw.jsonl` | 逐样本：question / answer / contexts / scores |
| `metrics.json` | 汇总：samples + 四项均分 |
| `summary.md` | 人工结论（与 basic_rag 对比） |

## 结论模板

```
RAGAS evaluation on N paired samples.

Compared with basic RAG:
- faithfulness +X
- answer relevancy +X

The improvement mainly comes from evidence policy and layer-aware retrieval.
```

## 重跑注意

1. 先修标注口径（旧结果 context_precision/recall=0 是标注问题，非检索真为 0）
2. 消耗 LLM，放最后跑
3. 跑完覆盖 `metrics.json` 与本文件
