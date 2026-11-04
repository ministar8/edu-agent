"""在线检索链：查询 → 多路召回 → 融合 → 重排 → 证据。

两条显式入口（勿混）：
- `retrieve_for_task`：产品路径，返回**已裁剪**的 `EvidenceBundle`。
- `aretrieve_evidence_raw`：测量路径，返回**未裁剪**的检索包
  （检索门禁 / RAGAS / 诊断 / 消融实验用）。
"""

from rag.retrieval.api import EvidenceBundle, retrieve_for_task
from rag.retrieval.evidence import FusedEvidence
from rag.retrieval.retriever import aretrieve_evidence_raw

__all__ = [
    "EvidenceBundle",
    "FusedEvidence",
    "aretrieve_evidence_raw",
    "retrieve_for_task",
]
