"""语义缓存的编解码与常量（从 semantic_cache.py 拆出，行为等价）。"""

from __future__ import annotations

import hashlib
from pathlib import Path

from core.settings import settings
from rag.retrieval.evidence import FusedEvidence

# ── 默认值（可被 settings 覆盖）──────────────────────────────
_COLLECTION_NAME = "semantic_cache"
_DATA_DIR = Path(settings.CHROMA_PERSIST_DIR) / "semantic_cache"
_JSONL_FILE = _DATA_DIR / "evidence.jsonl"
_TTL = 1800  # 30 分钟
_MAX_ENTRIES = 500
_SIMILARITY_THRESHOLD = 0.88


def _cache_key(
    query: str,
    collection_name: str = "",
    filter_sig: str = "",
    params_sig: str = "",
) -> str:
    """由归一化 query + collection + filter + 检索参数生成确定性 key。

    Different collections、filters 或检索参数（use_rerank / RERANK_ENABLED /
    k / score_threshold / depth / max_tokens）不得共享缓存条目，
    即使 query 语义相似也不行。

    ★★ **本 key 刻意不含 `task_mode` / `policy_version` / `cache_scope`** ★★
    （原先由 `schema/task_policy.TaskPolicy.cache_key_parts()` 声明「必含」，该方法已于
    2026-10-07 作为死代码删除，其不变量转移到此处 —— 因为它**依赖一个隐式前提**。）

    **为什么不含也不出事**：本缓存只存 **`aretrieve_evidence` 返回的「纯检索结果」**，
    而所有 **policy 相关处理都在缓存之外**执行：

        aretrieve_evidence_with_retry(...)   ← 缓存发生处（agents/tools.py）
          ├─ _with_topup(...)                ← 缓存之后（preferred_layers / eligible_layers）
          ├─ finalize_with_layer_ranking(...) ← 缓存之后（legacy 池策略 + 排序 + 截断）
          └─ apply_evidence_policy(...)       ← 缓存之后（**release 裁剪，安全出口**）

    且 `aretrieve_evidence` **不 import** `apply_evidence_policy`
    ⇒ 缓存命中**也无法绕过 release 裁剪**（每次都按当前 policy 重做）⇒ 无泄露。

    另：`task_mode` 已**间接**进 key —— 召回 filter 来自 `policy.eligibility_where()`，
    而各 mode 的 `exam_resources` 不同 ⇒ filter 不同 ⇒ `filter_sig` 不同。
    （实测仅 `explain` 的 `eligibility_where()` 返回 `None`，不存在两个 mode 同时为空。）

    ⚠️ **改动须知**：若将来把 `_with_topup` / `finalize_with_layer_ranking` /
    `apply_evidence_policy` **移进** `aretrieve_evidence`（看起来是很自然的重构），
    则本缓存会**连 policy 裁剪结果一起缓存** ⇒ 策略变更后旧缓存继续命中 ⇒ **真泄露**。
    **届时必须先把 `task_mode` / `policy_version` / `cache_scope` 加进本 key。**
    """
    normalized = query.strip().lower()
    raw = f"{normalized}|{collection_name}|{filter_sig}|{params_sig}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _serialize_evidence(fused: FusedEvidence) -> str:
    """把 FusedEvidence 序列化为 JSON 字符串，用于落盘存储。"""
    return fused.model_dump_json()


def _deserialize_evidence(data: str) -> FusedEvidence:
    """从 JSON 字符串反序列化 FusedEvidence。"""
    return FusedEvidence.model_validate_json(data)
