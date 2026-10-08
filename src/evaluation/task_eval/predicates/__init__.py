"""四态判据与复合语义（EVIDENCE_CHAIN.md §1.3/§1.6）。

★ 本包是「一个指标只有一处定义」的落点：判据函数、四态语义、地址语法都只在
  这里出现一次，report / backfill / falsify / V0 全部从 registry 取，不再各写一份。
"""

from __future__ import annotations

from evaluation.task_eval.predicates import common, generate, memory, registry, verify

__all__ = ["common", "generate", "memory", "registry", "verify"]
