"""检索流水线的模块级常量与类型别名（从 pipeline.py 拆出，行为等价）。"""

from __future__ import annotations

from collections.abc import Callable

from core.settings import settings

# 阶段进度回调类型：上报「即将进入某检索阶段」
StageSink = Callable[[str], None]

# 重排候选扩展系数（与门禁/实验的 coarse_k 口径一致）
_RERANK_EXPAND_FACTOR = settings.RERANK_EXPAND_FACTOR

# RRF 融合分数阈值（基于采样校准，非余弦距离）
# RRF(k=20): 排名1≈0.048, 排名5≈0.040（权重 1.0 时）
# 权重 1.5 的路由第 10 名 = 1.5/(20+10) = 0.05 → 刚好过旧阈值
# 0.06 ≈ "至少1路前7" 或 "2路前15"，过滤掉排名#8+的单路噪声
# 数值来自 `settings.RETRIEVAL_SCORE_THRESHOLD`（可经 .env 覆盖，backlog #14）。
# 保留模块级别名是为了不动下游函数签名的默认值。
SCORE_THRESHOLD = settings.RETRIEVAL_SCORE_THRESHOLD

# 对比类查询的子查询精简路由集（避免子查询把召回面摊得过宽）
_COMPACT_SUBQUERY_ROUTES = {"keyword_bm25", "concept_meta", "structured_meta", "section_meta"}

# `_safe_to_thread` 在超时/异常时**原样返回 default**；用一个可辨识哨兵当 default，
# 调用点就能区分「rerank 真的返回了列表」与「rerank 坏了走兜底」⇒ 四态里的 `failed`
# 有实测依据，而不是把降级猜成失败。（reranker 自捕 HTTP 错误会返回**不含 rerank_score**
# 的正常列表 ⇒ raised=False、无键 ⇒ degraded，与「超时/抛错走 default=failed」天然分开。）
_RERANK_UNSET = object()
