"""RAG 检索包：知识库 → 可溯源 Evidence Pack。

主路径（详见包内 `README.md`）：
  ① 查询理解 → ② 多路召回 → ③ 加权 RRF → ④ 过滤/可选重排
  → ⑤ evidence_policy 出包 → ⑥ 语义缓存 + 规则验证

对外入口：`rag.retrieval.retriever.aretrieve_evidence*`（Agent 经 tools 调用）。
策略真源在 `schema.task_policy.TaskPolicy`；计算预算在 `retrieval_plan`。
"""
