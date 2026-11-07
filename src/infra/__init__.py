"""存储与遥测底座（2026-11-07，从 ``rag.common`` 迁出，见 docs/INFRA_MIGRATION_PLAN.md）。

本包不得 import ``rag`` / ``agents`` / ``memory`` / ``service`` / ``evaluation`` / ``prompts``，
只依赖 ``core`` / ``schema`` + 第三方库，保持为项目最底层的非业务基建。
"""

from infra._metadata_spec import sanitize_for_chroma
from infra._vectorstore_base import (
    _HNSW_COLLECTION_METADATA,
    _LEGACY_HNSW_KEYS,
    _READINESS_PROBE_QUERY,
    _content_hash,
    _is_http_endpoint_available,
    _RWLock,
    _VectorStoreBase,
)
from infra._vectorstore_ingest import _IngestMixin
from infra._vectorstore_query import _QueryMixin, _retry_async
from infra.embeddings import (
    HashingEmbeddings,
    OpenAICompatibleEmbeddings,
    clear_query_cache,
    get_embeddings,
    query_cache_stats,
    similarity_from_distance,
)
from infra.errors import (
    RagError,
    RagInternalError,
    RetrievalUnavailable,
    classify_retrieval_error,
)
from infra.metrics import (
    DEFAULT_METRICS_PATH,
    MetricsTimer,
    MetricsWriter,
    metrics,
)
from infra.vectorstore import VectorStoreManager, get_vector_store_manager

__all__ = [
    # vectorstore
    "VectorStoreManager",
    "get_vector_store_manager",
    # _vectorstore_base
    "_HNSW_COLLECTION_METADATA",
    "_LEGACY_HNSW_KEYS",
    "_READINESS_PROBE_QUERY",
    "_content_hash",
    "_is_http_endpoint_available",
    "_RWLock",
    "_VectorStoreBase",
    # _vectorstore_ingest
    "_IngestMixin",
    # _vectorstore_query
    "_QueryMixin",
    "_retry_async",
    # embeddings
    "OpenAICompatibleEmbeddings",
    "HashingEmbeddings",
    "get_embeddings",
    "query_cache_stats",
    "clear_query_cache",
    "similarity_from_distance",
    # errors
    "RagError",
    "RetrievalUnavailable",
    "RagInternalError",
    "classify_retrieval_error",
    # metrics
    "DEFAULT_METRICS_PATH",
    "MetricsTimer",
    "MetricsWriter",
    "metrics",
    # _metadata_spec
    "sanitize_for_chroma",
]
